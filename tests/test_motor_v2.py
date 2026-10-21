"""Fatia v2.3: funções puras do motor para a proposta v2 (spec v2, seção 4)."""

import pytest

from propostas.services.calculo import (
    geracao_necessaria,
    kwh_pela_conta,
    kwp_necessario,
    mao_de_obra_sugerida,
    parcela_price,
    quantidade_modulos,
    sugerir_inversor,
    tabela_financiamento,
)

GURUPI = [5.39, 5.31, 5.18, 5.24, 5.21, 5.32, 5.62, 6.07, 6.09, 5.72, 5.5, 5.46]

INVERSORES = [
    {"nome": "Mono 3 kW", "kw": 3.0, "fase": "mono"},
    {"nome": "Mono 5 kW", "kw": 5.0, "fase": "mono"},
    {"nome": "Mono 10 kW", "kw": 10.0, "fase": "mono"},
    {"nome": "Tri 12 kW", "kw": 12.0, "fase": "tri"},
]


def test_kwh_pela_conta_desconta_iluminacao_e_soma_bandeira():
    # Conta de R$ 500 com R$ 30 de iluminação, tarifa R$ 1,00 e bandeira amarela (0,01885)
    assert kwh_pela_conta(500, 30, 1.0, 0.01885) == pytest.approx(461.30, abs=0.01)
    assert kwh_pela_conta(500, 0, 1.0, 0) == pytest.approx(500)


def test_kwh_pela_conta_recusa_conta_menor_que_iluminacao():
    with pytest.raises(ValueError):
        kwh_pela_conta(20, 30, 1.0, 0)


def test_geracao_necessaria():
    assert geracao_necessaria(800, 0.10, 50) == pytest.approx(830)
    assert geracao_necessaria(40, 0, 50) == 0  # consome menos que a disponibilidade


def test_kwp_necessario_bate_com_a_geracao():
    kwp = kwp_necessario(800, 0.0, 50, GURUPI, 0.14, 0.01, 1.0)
    gerado_ano = sum(kwp * irr * dias * 0.86 * 0.99 for irr, dias in zip(GURUPI, [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]))
    assert gerado_ano / 12 == pytest.approx(750)
    assert kwp == pytest.approx(5.26, abs=0.01)


def test_kwp_necessario_cresce_com_orientacao_pior():
    norte = kwp_necessario(800, 0.1, 50, GURUPI, 0.14, 0.01, 1.0)
    leste = kwp_necessario(800, 0.1, 50, GURUPI, 0.14, 0.01, 0.9)
    assert leste == pytest.approx(norte / 0.9)


@pytest.mark.parametrize("kwp, potencia, esperado", [(5.47, 610, 9), (6.1, 610, 10), (12.81, 610, 21), (0.1, 610, 1)])
def test_quantidade_modulos(kwp, potencia, esperado):
    assert quantidade_modulos(kwp, potencia) == esperado


@pytest.mark.parametrize("kwp, fase, nome, quantidade", [
    (4.0, "mono", "Mono 3 kW", 1),     # 4/3 = 1,33
    (5.49, "mono", "Mono 5 kW", 1),    # 5,49/3 = 1,83 > 1,5
    (12.81, "mono", "Mono 10 kW", 1),  # caso Belenus: Deye 10 kW, 1,28
    (16.12, "tri", "Tri 12 kW", 1),    # caso Intelbras: 1,34
    (20.0, "mono", "Mono 10 kW", 2),   # nenhum sozinho: 2 × 10 kW
    (5.49, "bi", "Mono 5 kW", 1),      # bifásica usa inversor 220 V
])
def test_sugerir_inversor(kwp, fase, nome, quantidade):
    inversor, qtd = sugerir_inversor(kwp, INVERSORES, fase)
    assert (inversor["nome"], qtd) == (nome, quantidade)


def test_sugerir_inversor_sem_inversor_da_fase():
    assert sugerir_inversor(5, [i for i in INVERSORES if i["fase"] == "mono"], "tri") == (None, 0)


def test_mao_de_obra_sugerida():
    assert mao_de_obra_sugerida(5.0, False, 500, 700, 4500) == 4500  # mínimo
    assert mao_de_obra_sugerida(12.81, False, 500, 700, 4500) == pytest.approx(6405)
    assert mao_de_obra_sugerida(16.12, True, 500, 700, 4500) == pytest.approx(11284)  # solo, caso Intelbras


def test_parcela_price():
    assert parcela_price(30000, 0.0159, 60) == pytest.approx(779.54, abs=0.01)
    assert parcela_price(1200, 0, 12) == 100


def test_tabela_financiamento_escolhe_o_melhor_banco_por_prazo():
    taxas = [("BV", 12, 0.0159), ("Sicredi", 12, 0.0149), ("BV", 60, 0.0189), ("Sicredi", 72, 0.021)]
    tabela = tabela_financiamento(30000, taxas)
    assert [(t["prazo"], t["banco"]) for t in tabela] == [(12, "Sicredi"), (60, "BV"), (72, "Sicredi")]
    assert tabela[0]["parcela"] == pytest.approx(parcela_price(30000, 0.0149, 12))
