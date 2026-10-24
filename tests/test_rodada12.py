"""Rodada 12: vendedor responsável, próximo contato, painel da página inicial e celular (A18–A20, H16, D46)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client as Navegador
from django.urls import reverse

from clientes.models import Cliente
from core.models import ConfigEmpresa
from core.painel import montar_painel
from orcamentos.models import Orcamento
from propostas.models import Proposta

HOJE = date.today()


@pytest.fixture
def pessoas(db):
    ana = User.objects.create(username="ana", first_name="Ana")
    beto = User.objects.create(username="beto", first_name="Beto")
    chefe = User.objects.create(username="chefe")
    chefe.groups.add(Group.objects.get(name="gestor"))
    return ana, beto, chefe


def _proposta(vendedor, numero, versao=1, **extra):
    cliente = Cliente.objects.create(nome=f"Cliente {numero}", telefone=f"6399{abs(hash(numero)) % 10**7:07d}")
    return Proposta.objects.create(**{
        "cliente": cliente, "numero": numero, "versao": versao, "vendedor": vendedor, "status": "emitida",
        "emissao": HOJE, "validade_dias": 15, "kwp": Decimal("5"), "investimento": Decimal("20000"),
    } | extra)


def _painel(usuario, gestor=False):
    return montar_painel(usuario, gestor, HOJE, ConfigEmpresa.obter())


def test_numeros_do_mes_contam_cada_proposta_uma_vez(pessoas):
    ana, beto, _ = pessoas
    _proposta(ana, "OPT-1", status="substituida")
    _proposta(ana, "OPT-1", versao=2, status="aceita", data_aceite=HOJE)
    _proposta(ana, "OPT-2", status="perdida", perdida_em=HOJE, motivo_perda="preco")
    _proposta(beto, "OPT-3")
    painel = _painel(ana)
    assert (painel["emitidas"], painel["aceitas"], painel["perdidas"]) == (2, 1, 1)
    assert painel["conversao"] == 50 and painel["valor_aceito"] == Decimal("20000")
    assert painel["motivos"] == [("Preço", 1)]
    assert "por_vendedor" not in painel  # vendedor vê só os dele


def test_gestor_ve_todos_e_a_tabela_por_vendedor(pessoas):
    ana, beto, chefe = pessoas
    _proposta(ana, "OPT-1", status="aceita", data_aceite=HOJE)
    _proposta(beto, "OPT-2")
    painel = _painel(chefe, gestor=True)
    assert painel["emitidas"] == 2
    assert dict(painel["por_vendedor"]) == {"Ana": {"emitidas": 1, "aceitas": 1, "valor": Decimal("20000")},
                                            "Beto": {"emitidas": 1, "aceitas": 0, "valor": 0}}


def test_vencendo_e_paradas(pessoas):
    ana, _, _ = pessoas
    vence = _proposta(ana, "OPT-1", emissao=HOJE - timedelta(days=13))  # vence em 2 dias
    parada = _proposta(ana, "OPT-2", emissao=HOJE - timedelta(days=8))
    _proposta(ana, "OPT-3", emissao=HOJE - timedelta(days=8), proximo_contato=HOJE + timedelta(days=1))
    painel = _painel(ana)
    assert painel["vencendo"] == [vence]
    assert parada in painel["paradas"] and len(painel["paradas"]) == 2  # a que vence também está parada


def test_ligar_hoje_com_proposta_e_orcamento_atrasado_primeiro(pessoas):
    ana, beto, _ = pessoas
    _proposta(ana, "OPT-1", proximo_contato=HOJE)
    _proposta(ana, "OPT-2", proximo_contato=HOJE + timedelta(days=2))  # ainda não
    _proposta(ana, "OPT-4", proximo_contato=HOJE, status="aceita")  # fechada: não liga
    _proposta(beto, "OPT-3", proximo_contato=HOJE)  # de outro vendedor
    cliente = Cliente.objects.create(nome="Posto", telefone="63999990000")
    Orcamento.objects.create(numero="ORC-1", cliente=cliente, titulo="CFTV", vendedor=ana,
                             proximo_contato=HOJE - timedelta(days=1))
    linhas = _painel(ana)["ligar_hoje"]
    assert [(l["titulo"], l["atrasado"]) for l in linhas] == [("ORC-1 v1", True), ("OPT-1 v1", False)]


def test_pagina_inicial_mostra_o_painel(pessoas):
    ana, _, chefe = pessoas
    _proposta(ana, "OPT-1", proximo_contato=HOJE)
    navegador = Navegador()
    navegador.force_login(ana)
    html = navegador.get("/").content.decode()
    assert "Ligar hoje" in html and "OPT-1 v1" in html and "Por vendedor" not in html
    navegador.force_login(chefe)
    assert "Por vendedor" in navegador.get("/").content.decode()


# ---------- A20 · acompanhamento

def test_quem_cria_vira_o_vendedor(base):
    from .test_proposta_v2 import _ate_passo2
    _, proposta = _ate_passo2(base)
    assert proposta.vendedor is not None and proposta.vendedor.username


def test_vendedor_marca_proximo_contato_e_nao_troca_o_responsavel(pessoas):
    ana, beto, _ = pessoas
    proposta = _proposta(ana, "OPT-1")
    navegador = Navegador()
    navegador.force_login(ana)
    url = reverse("propostas:acompanhamento", args=[proposta.pk])
    resposta = navegador.post(url, {"proximo_contato": (HOJE + timedelta(days=2)).isoformat(), "vendedor": beto.pk,
                                    "voltar": "https://fora.com/"})
    assert resposta.url == reverse("propostas:detalhe", args=[proposta.pk])  # não segue link de fora
    proposta.refresh_from_db()
    assert proposta.proximo_contato == HOJE + timedelta(days=2) and proposta.vendedor == ana


def test_gestor_troca_o_responsavel_do_orcamento(pessoas):
    ana, beto, chefe = pessoas
    cliente = Cliente.objects.create(nome="Posto", telefone="63999990000")
    orcamento = Orcamento.objects.create(numero="ORC-1", cliente=cliente, titulo="CFTV", vendedor=ana)
    navegador = Navegador()
    navegador.force_login(chefe)
    editor = reverse("orcamentos:editor", args=[orcamento.pk])
    assert "Vendedor responsável" in navegador.get(editor).content.decode()
    navegador.post(reverse("orcamentos:acompanhamento", args=[orcamento.pk]),
                   {"proximo_contato": "", "vendedor": beto.pk, "voltar": editor})
    orcamento.refresh_from_db()
    assert orcamento.vendedor == beto and orcamento.proximo_contato is None


def test_proximo_contato_no_passado_e_recusado(pessoas):
    ana, _, _ = pessoas
    proposta = _proposta(ana, "OPT-1")
    navegador = Navegador()
    navegador.force_login(ana)
    navegador.post(reverse("propostas:acompanhamento", args=[proposta.pk]),
                   {"proximo_contato": (HOJE - timedelta(days=1)).isoformat()})
    proposta.refresh_from_db()
    assert proposta.proximo_contato is None


def test_perda_grava_a_data_e_nova_versao_mantem_o_acompanhamento(pessoas):
    from propostas import emissao
    ana, _, _ = pessoas
    proposta = _proposta(ana, "OPT-1", proximo_contato=HOJE)
    nova = emissao.revisar(proposta)
    assert nova.vendedor == ana and nova.proximo_contato == HOJE
    emissao.marcar_perdida(proposta, "preco")
    assert proposta.perdida_em == HOJE


# ---------- A18 · celular

def test_menu_recolhivel_e_barra_fixa_nos_passos(base):
    from .test_proposta_v2 import _ate_passo2
    navegador, proposta = _ate_passo2(base)
    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 3])).content.decode()
    assert 'class="sidebar__menu"' in html and 'aria-controls="menu-links"' in html
    assert 'class="resumo__barra"' in html
