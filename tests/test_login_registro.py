"""Rodada 2 do plano de correções: login, registro da emissão e número definitivo (D36)."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client as Navegador
from django.urls import reverse
from django.utils import timezone

from core.models import ConfigEmpresa
from propostas import views
from propostas.models import Proposta
from propostas.montagem import premissas_da_proposta

from .test_proposta_v2 import _ate_passo2, _passo3


@pytest.fixture(autouse=True)
def sem_chromium(monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(views, "html_para_pdf", lambda html: b"%PDF-1.4 falso")


def _vendedor():
    navegador = Navegador()
    navegador.force_login(User.objects.create(username="vendedor"))
    return navegador


def _rascunho(base):
    navegador, proposta = _ate_passo2(base)
    _passo3(navegador, proposta)
    proposta.refresh_from_db()
    return navegador, proposta


# A05: login e gestor

@pytest.mark.parametrize("rota", ["/", "/propostas/", "/clientes/", "/orcamentos/", "/media/qualquer.pdf"])
def test_sem_login_vai_para_a_tela_de_entrar(db, rota):
    navegador = Navegador()
    navegador.logout()
    resposta = navegador.get(rota)
    assert resposta.status_code == 302 and resposta.url.startswith(reverse("login"))


def test_entrar_com_usuario_e_senha(db):
    User.objects.create_user("maria", password="Senha-forte-123")
    navegador = Navegador()
    navegador.logout()
    assert "Usuário" in navegador.get(reverse("login")).content.decode()
    resposta = navegador.post(reverse("login"), {"username": "maria", "password": "errada"})
    assert "não conferem" in resposta.content.decode()
    resposta = navegador.post(reverse("login"), {"username": "maria", "password": "Senha-forte-123"})
    assert resposta.status_code == 302
    assert navegador.get("/propostas/").status_code == 200


@pytest.mark.parametrize("rota", ["core:config_empresa", "core:config_premissas", "core:config_tarifas",
                                  "core:config_financiamento", "propostas:solar_equipamento_novo",
                                  "orcamentos:importar"])
def test_vendedor_nao_abre_telas_do_gestor(db, rota):
    resposta = _vendedor().get(reverse(rota))
    assert resposta.status_code == 403 and "Só o gestor" in resposta.content.decode()


def test_vendedor_usa_propostas_e_cotacoes_e_nao_ve_configuracoes_no_menu(db):
    navegador = _vendedor()
    html = navegador.get(reverse("propostas:lista")).content.decode()
    assert reverse("core:config_empresa") not in html
    assert navegador.get(reverse("propostas:solar_cotacoes")).status_code == 200
    assert navegador.get(reverse("propostas:solar_equipamentos")).status_code == 200


def test_grupo_gestor_abre_configuracoes(db):
    usuario = User.objects.create(username="chefe")
    usuario.groups.add(Group.objects.get(name="gestor"))
    navegador = Navegador()
    navegador.force_login(usuario)
    assert navegador.get(reverse("core:config_empresa")).status_code == 200


# A13: número só na primeira emissão; descartar rascunho

def test_numero_so_na_primeira_emissao(base):
    navegador, proposta = _rascunho(base)
    assert proposta.numero is None and str(proposta) == f"Rascunho {proposta.pk}"
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    proposta.refresh_from_db()
    assert proposta.status == "emitida" and proposta.numero.startswith("OPT-")
    navegador.post(reverse("propostas:revisar", args=[proposta.pk]))
    v2 = Proposta.objects.get(versao=2)
    assert v2.numero == proposta.numero


def test_dois_rascunhos_sem_numero_nao_se_misturam(base):
    _, primeiro = _rascunho(base)
    navegador, segundo = _rascunho(base)
    navegador.post(reverse("propostas:emitir", args=[segundo.pk]))
    primeiro.refresh_from_db()
    segundo.refresh_from_db()
    assert primeiro.status == "rascunho" and primeiro.numero is None
    assert segundo.status == "emitida"


def test_descartar_rascunho(base):
    navegador, proposta = _rascunho(base)
    assert "Descartar este rascunho" in navegador.get(reverse("propostas:passo", args=[proposta.pk, 4])).content.decode()
    resposta = navegador.post(reverse("propostas:descartar", args=[proposta.pk]))
    assert resposta.url == reverse("propostas:lista")
    assert not Proposta.objects.filter(pk=proposta.pk).exists()


def test_emitida_nao_e_descartada(base):
    navegador, proposta = _rascunho(base)
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    navegador.post(reverse("propostas:descartar", args=[proposta.pk]))
    assert Proposta.objects.filter(pk=proposta.pk).exists()


# A10: registro da emissão

def test_emissao_registra_entradas_saidas_e_quem_emitiu(base):
    navegador, proposta = _rascunho(base)
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    proposta.refresh_from_db()
    registro = proposta.registro
    assert proposta.emitida_por.username == "gestor_teste"
    assert registro["entradas"]["tarifa"]["aliquota_tributos"] == pytest.approx(0.25)
    assert registro["entradas"]["conta_informada"] == pytest.approx(500)
    assert registro["entradas"]["municipio"]["nome"] == "Gurupi"
    assert registro["saidas"]["investimento"] == pytest.approx(float(proposta.investimento), abs=0.01)
    assert registro["saidas"]["modulo"]["codigo"]
    assert registro["saidas"]["resultado"]["economia_mensal_ano1"] > 0

    navegador.post(reverse("propostas:aceitar", args=[proposta.pk]), {"data_aceite": "2026-10-20"})
    navegador.post(reverse("propostas:desfazer_aceite", args=[proposta.pk]), {"motivo": "Desistiu"})
    navegador.post(reverse("propostas:perdida", args=[proposta.pk]), {"motivo_perda": "preco"})
    proposta.refresh_from_db()
    assert proposta.aceita_por and proposta.aceite_desfeito_por and proposta.perdida_por
    html = navegador.get(reverse("propostas:detalhe", args=[proposta.pk])).content.decode()
    assert "por gestor_teste" in html


def test_revisao_comeca_sem_registro(base):
    navegador, proposta = _rascunho(base)
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    navegador.post(reverse("propostas:revisar", args=[proposta.pk]))
    v2 = Proposta.objects.get(versao=2)
    assert v2.registro == {} and v2.emitida_por is None


# A17: ano de conexão

def test_ano_de_conexao_pelo_prazo_de_homologacao(base):
    _, proposta = _rascunho(base)
    config = ConfigEmpresa.obter()
    config.prazo_homologacao_dias = 400
    config.save()
    esperado = (timezone.localdate() + timedelta(days=400)).year
    assert premissas_da_proposta(proposta, config)["ano_conexao"] == esperado


# A12: SQLite em WAL

def test_sqlite_em_wal(settings):
    opcoes = settings.DATABASES["default"]["OPTIONS"]
    assert "journal_mode=WAL" in opcoes["init_command"] and opcoes["timeout"] >= 20
