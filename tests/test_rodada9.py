"""Rodada 9: financiamento com % ao mês e ao ano, TAC e IOF (H04, D43)."""

from decimal import Decimal

import pytest
from django.test import Client as Navegador
from django.urls import reverse

from core.models import ConfigEmpresa
from propostas.models import TaxaFinanciamento
from propostas.services.calculo import iof_do_financiamento, parcela_price, tabela_financiamento, valor_financiado

PF, ADICIONAL = 0.000082, 0.0038

# ---------- Motor


def test_sem_tac_e_sem_iof_a_parcela_nao_muda():
    linha = tabela_financiamento(30000, [("BV", 60, 0.0159, 0, 0)])[0]
    assert linha["parcela"] == pytest.approx(parcela_price(30000, 0.0159, 60))
    assert linha["tac"] == 0 and linha["iof"] == pytest.approx(0)


def test_iof_de_12_meses_fica_na_faixa_dos_simuladores():
    # R$ 10.000 em 12× a 1,5% a.m., pessoa física: os simuladores dos bancos dão perto de R$ 200.
    iof = iof_do_financiamento(10000, 0.015, 12, PF, ADICIONAL)
    assert 180 < iof < 220


def test_iof_diario_para_de_crescer_depois_de_365_dias():
    curto = iof_do_financiamento(10000, 0.015, 12, PF, 0) / 10000
    longo = iof_do_financiamento(10000, 0.015, 72, PF, 0) / 10000
    assert longo < 365 * PF and curto < longo


def test_iof_e_tac_sao_financiados():
    custos = valor_financiado(30000, 0.0159, 60, tac_reais=500, tac_fracao=0.01, iof_diario=PF, iof_adicional=ADICIONAL)
    assert custos["tac"] == pytest.approx(800)
    # O IOF incide sobre o próprio valor financiado.
    assert custos["iof"] == pytest.approx(iof_do_financiamento(custos["financiado"], 0.0159, 60, PF, ADICIONAL), abs=0.01)
    assert custos["financiado"] == pytest.approx(30800 + custos["iof"])


def test_pessoa_juridica_paga_menos_iof():
    pf = valor_financiado(30000, 0.0159, 60, iof_diario=PF, iof_adicional=ADICIONAL)["iof"]
    pj = valor_financiado(30000, 0.0159, 60, iof_diario=0.000041, iof_adicional=ADICIONAL)["iof"]
    assert pj < pf


def test_melhor_banco_e_escolhido_depois_da_tac():
    taxas = [("Taxa baixa, TAC alta", 12, 0.0150, 1500, 0), ("Taxa alta, sem TAC", 12, 0.0165, 0, 0)]
    assert tabela_financiamento(20000, taxas)[0]["banco"] == "Taxa alta, sem TAC"
    assert tabela_financiamento(20000, [(b, p, t, 0, 0) for b, p, t, _, _ in taxas])[0]["banco"] == "Taxa baixa, TAC alta"


# ---------- Configurações

def _post(dados):
    return Navegador().post(reverse("core:config_financiamento"), dados)


def test_tela_mostra_ao_mes_ao_ano_tac_e_iof(base):
    html = Navegador().get(reverse("core:config_financiamento")).content.decode()
    assert "% ao mês" in html and "20,8% a.a." in html  # 1,59% a.m. → 20,8% a.a.
    assert "TAC (R$)" in html and 'name="iof_diario_pf"' in html and 'value="0,0082"' in html


def test_gestor_grava_tac_do_banco_e_iof(base):
    resposta = _post({"banco_0": "BV", "taxa_0_12": "1,39", "taxa_0_60": "1,59", "tac_reais_0": "450,00",
                      "tac_pct_0": "1", "iof_adicional": "0,38", "iof_diario_pf": "0,0082", "iof_diario_pj": "0,005"})
    assert resposta.status_code == 302
    for taxa in TaxaFinanciamento.objects.all():
        assert taxa.tac_reais == Decimal("450.00") and taxa.tac_percentual == Decimal("0.01000")
    assert ConfigEmpresa.obter().iof_diario_pj == Decimal("0.0000500")


def test_iof_vazio_mantem_o_valor_atual(base):
    _post({"banco_0": "BV", "taxa_0_12": "1,39"})
    assert ConfigEmpresa.obter().iof_adicional == Decimal("0.0038")


def test_tac_negativa_e_recusada(base):
    assert _post({"banco_0": "BV", "taxa_0_12": "1,39", "tac_reais_0": "-10,00"}).status_code == 200


# ---------- Proposta

def test_parcela_da_proposta_inclui_iof_e_vai_para_o_registro(base):
    from propostas.montagem import montar, registro_da_emissao

    from .test_proposta_v2 import _ate_passo2, _passo3
    navegador, proposta = _ate_passo2(base)
    _passo3(navegador, proposta)
    proposta.refresh_from_db()
    m = montar(proposta)
    linha = m.financiamento[0]
    assert linha["iof"] > 0 and linha["parcela"] > parcela_price(m.investimento, linha["taxa"], linha["prazo"])
    registro = registro_da_emissao(proposta, m, proposta.premissas or {})
    assert registro["entradas"]["iof"]["adicional"] == pytest.approx(ADICIONAL)
    assert registro["saidas"]["financiamento"][0]["iof"] == linha["iof"]
    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 4])).content.decode()
    assert "já com IOF e TAC" in html
