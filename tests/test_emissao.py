"""Fatia v2.7: emissão e versões (D07, D31)."""

from datetime import timedelta

import pytest
from django.test import Client as Navegador
from django.urls import reverse
from django.utils import timezone

from propostas import views
from propostas.models import Proposta

from .test_fatia4_proposta_view import fatura_alesio, uc_alesio  # noqa: F401 (fixtures)
from .test_fatia5_pdf import proposta_alesio  # noqa: F401 (fixture)
from .test_proposta_v2 import _ate_passo2, _passo2, _passo3, base  # noqa: F401 (fixture)

PDF_FALSO = b"%PDF-1.4 falso"


@pytest.fixture(autouse=True)
def sem_chromium(monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(views, "html_para_pdf", lambda html: PDF_FALSO)


def _rascunho_completo(base, **passo2):
    navegador, proposta = _ate_passo2(base, **passo2)
    _passo3(navegador, proposta)
    proposta.refresh_from_db()
    return navegador, proposta


def _emitir(navegador, proposta):
    resposta = navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    proposta.refresh_from_db()
    return resposta


def test_emitir_congela_kit_preco_e_guarda_o_pdf(base):
    navegador, proposta = _rascunho_completo(base)
    assert proposta.custo_kit is None and proposta.modulo is None  # rascunho usa as sugestões
    resposta = _emitir(navegador, proposta)
    assert resposta.url == reverse("propostas:detalhe", args=[proposta.pk])
    assert proposta.status == "emitida" and proposta.emissao == timezone.localdate()
    assert proposta.modulo and proposta.qtd_modulos and proposta.inversor and proposta.custo_kit
    assert proposta.investimento == proposta.custo_kit + proposta.mao_de_obra - proposta.desconto
    assert proposta.premissas and proposta.resultados["payback_meses"] > 0
    assert proposta.pdf.name.endswith(f"{proposta.numero}_v1.pdf")
    # O PDF da emitida é o guardado, mesmo se o motor mudar depois.
    assert navegador.get(reverse("propostas:pdf", args=[proposta.pk])).content == PDF_FALSO


def test_emitida_nao_edita_e_abre_no_detalhe(base):
    navegador, proposta = _rascunho_completo(base)
    _emitir(navegador, proposta)
    assert navegador.get(reverse("propostas:editar", args=[proposta.pk])).url == reverse(
        "propostas:detalhe", args=[proposta.pk])
    assert navegador.get(reverse("propostas:passo", args=[proposta.pk, 3])).url == reverse(
        "propostas:detalhe", args=[proposta.pk])
    html = navegador.get(reverse("propostas:detalhe", args=[proposta.pk])).content.decode()
    assert "Marcar como aceita" in html and "Recebi a fatura" in html


def test_rascunho_incompleto_nao_emite(base):
    navegador, proposta = _ate_passo2(base)
    from propostas.models import TarifaVigente
    TarifaVigente.objects.update(fiob_kwh=None)
    _emitir(navegador, proposta)
    assert proposta.status == "rascunho" and not proposta.pdf
    html = navegador.get(reverse("propostas:detalhe", args=[proposta.pk])).content.decode()
    assert "Não foi possível emitir" in html


def test_pdf_que_falha_deixa_como_rascunho(base, monkeypatch):
    from core.pdf import ErroPDF

    def falha(html):
        raise ErroPDF("Chromium não encontrado")

    monkeypatch.setattr(views, "html_para_pdf", falha)
    navegador, proposta = _rascunho_completo(base)
    _emitir(navegador, proposta)
    assert proposta.status == "rascunho" and proposta.emissao is None and proposta.custo_kit is None


def test_revisar_cria_nova_versao_com_o_mesmo_numero(base):
    navegador, v1 = _rascunho_completo(base)
    _emitir(navegador, v1)
    resposta = navegador.post(reverse("propostas:revisar", args=[v1.pk]))
    v2 = Proposta.objects.get(numero=v1.numero, versao=2)
    assert resposta.url == reverse("propostas:passo", args=[v2.pk, 4])
    assert v2.status == "rascunho" and v2.origem == v1 and not v2.pdf
    assert v2.custo_kit == v1.custo_kit and v2.itens_kit.count() == v1.itens_kit.count()
    # Revisar de novo não cria outra: volta para o rascunho aberto.
    navegador.post(reverse("propostas:revisar", args=[v1.pk]))
    assert Proposta.objects.filter(numero=v1.numero).count() == 2

    _emitir(navegador, v2)
    v1.refresh_from_db()
    assert v2.status == "emitida" and v1.status == "substituida"


def test_estimativa_vira_confirmada_com_a_fatura(base):
    navegador, v1 = _rascunho_completo(base)
    _emitir(navegador, v1)
    resposta = navegador.post(reverse("propostas:revisar", args=[v1.pk]), {"para": "fatura"})
    v2 = Proposta.objects.get(numero=v1.numero, versao=2)
    assert resposta.url == reverse("propostas:passo", args=[v2.pk, 2])
    _passo2(navegador, v2, base, origem_consumo="fatura", conta_informada="", numero_uc="123456",
            endereco="Rua 1", competencia="2026-09-01", fatura_kwh="620", dias_ciclo="31", valor_fatura="845,30",
            cpf_cnpj="529.982.247-25")
    v2.refresh_from_db()
    assert v2.nivel == "confirmada" and v2.numero == v1.numero


def test_aceite_grava_a_data_e_substitui_as_outras_versoes(base):
    navegador, v1 = _rascunho_completo(base)
    _emitir(navegador, v1)
    navegador.post(reverse("propostas:revisar", args=[v1.pk]))
    v2 = Proposta.objects.get(numero=v1.numero, versao=2)
    _emitir(navegador, v2)
    navegador.post(reverse("propostas:aceitar", args=[v2.pk]), {"data_aceite": "2026-10-20"})
    v1.refresh_from_db()
    v2.refresh_from_db()
    assert v2.status == "aceita" and v2.data_aceite.isoformat() == "2026-10-20"
    assert v1.status == "substituida"
    # Aceita não volta a ser revisada nem perdida.
    navegador.post(reverse("propostas:perdida", args=[v2.pk]), {"motivo_perda": "preco"})
    navegador.post(reverse("propostas:revisar", args=[v2.pk]))
    v2.refresh_from_db()
    assert v2.status == "aceita" and Proposta.objects.filter(numero=v1.numero).count() == 2


def test_perdida_grava_o_motivo(base):
    navegador, proposta = _rascunho_completo(base)
    _emitir(navegador, proposta)
    navegador.post(reverse("propostas:perdida", args=[proposta.pk]), {"motivo_perda": "xyz"})
    proposta.refresh_from_db()
    assert proposta.status == "emitida"  # motivo inválido é recusado
    navegador.post(reverse("propostas:perdida", args=[proposta.pk]),
                   {"motivo_perda": "concorrente", "obs_perda": "Fechou com a Solar X por R$ 2 mil a menos"})
    proposta.refresh_from_db()
    assert proposta.status == "perdida" and proposta.get_motivo_perda_display() == "Fechou com concorrente"
    assert "Solar X" in proposta.obs_perda


def test_vencida_e_calculada_e_filtrada_na_lista(base):
    navegador, proposta = _rascunho_completo(base)
    _emitir(navegador, proposta)
    assert not proposta.vencida
    Proposta.objects.filter(pk=proposta.pk).update(emissao=timezone.localdate() - timedelta(days=30))
    proposta.refresh_from_db()
    assert proposta.vencida and proposta.situacao_display == "Vencida"
    html = navegador.get(reverse("propostas:lista") + "?status=vencida").content.decode()
    assert proposta.numero in html and "Vencida" in html
    assert proposta.numero not in navegador.get(reverse("propostas:lista") + "?status=emitida").content.decode()
    navegador.post(reverse("propostas:aceitar", args=[proposta.pk]), {"data_aceite": "2026-10-21"})
    proposta.refresh_from_db()
    assert proposta.status == "aceita"  # vencida ainda pode ser aceita


def test_get_nas_acoes_nao_altera_nada(base):
    navegador, proposta = _rascunho_completo(base)
    navegador.get(reverse("propostas:emitir", args=[proposta.pk]))
    proposta.refresh_from_db()
    assert proposta.status == "rascunho"


def test_proposta_antiga_emite_e_revisa_no_formulario_antigo(proposta_alesio):
    navegador = Navegador()
    navegador.post(reverse("propostas:emitir", args=[proposta_alesio.pk]))
    proposta_alesio.refresh_from_db()
    assert proposta_alesio.status == "emitida" and proposta_alesio.pdf
    resposta = navegador.post(reverse("propostas:revisar", args=[proposta_alesio.pk]))
    nova = Proposta.objects.get(numero=proposta_alesio.numero, versao=2)
    assert resposta.url == reverse("propostas:legado_editar", args=[nova.pk])
