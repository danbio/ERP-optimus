"""Caso de referência — Alesio Matte (55,35 kWp).

Reproduz os números de docs/caso-referencia.md. Tolerâncias conforme o
documento: ±0,5% para valores em R$ e kWh, ±0,2 mês para o payback.
Se algum número mudar, é bug até prova em contrário.
"""

import pytest

from propostas.services.calculo import EntradaCalculo, calcular, fiob_fallback

TOL = 0.005  # ±0,5%


@pytest.fixture
def resultado():
    fiob = fiob_fallback(
        valor_distribuicao=2458.63,
        kwh=5560,
        valor_total=7762.74,
        impostos=2128.86,
    )

    entrada = EntradaCalculo(
        kwp=90 * 615 / 1000,
        kw_ca=2 * 20_000 / 1000,
        irradiacao=[4.95, 5.05, 4.95, 5.15, 5.35, 5.40, 5.65, 6.05, 5.90, 5.45, 5.10, 4.85],
        kwh_fatura=5560,
        dias_ciclo=28,
        tarifa=1.372680,
        fiob_kwh=fiob,
        disponibilidade_kwh=100,
        investimento=92_502.81,
        fiob_pct_por_ano={2023: 0.15, 2024: 0.30, 2025: 0.45, 2026: 0.60, 2027: 0.75, 2028: 0.90, 2029: 1.00},
        premissas={
            "perdas": 0.18,
            "perda_clipping": 0.015,
            "ano_conexao": 2027,
            "simultaneidade": 0.50,
            "reajuste_anual": 0.04,
            "degradacao_ano1": 0.01,
            "degradacao_anual": 0.004,
            "cobrar_disponibilidade": True,
            "horizonte_anos": 25,
            "razao_cc_ca_max": 1.30,
        },
        classe="B1",
        cliente_pessoa_juridica=True,
        fiob_informado=False,
    )
    return fiob, calcular(entrada)


def test_fiob_fallback(resultado):
    fiob, _ = resultado
    assert fiob == pytest.approx(0.6093, rel=TOL)


def test_geracao_e_consumo_anual(resultado):
    _, r = resultado
    assert r.geracao_anual == pytest.approx(86_848, rel=TOL)
    assert r.geracao_anual / 12 == pytest.approx(7_237, rel=TOL)
    assert r.consumo_anual == pytest.approx(72_479, rel=TOL)
    assert r.consumo_anual / 12 == pytest.approx(6_040, rel=TOL)


def test_geracao_mensal(resultado):
    _, r = resultado
    esperado = [6860, 6321, 6860, 6907, 7415, 7242, 7830, 8385, 7913, 7553, 6840, 6722]
    for calculado, exp in zip(r.geracao_mensal, esperado):
        assert calculado == pytest.approx(exp, rel=TOL)


def test_consumo_mensal(resultado):
    _, r = resultado
    esperado = [6156, 5560, 6156, 5957, 6156, 5957, 6156, 6156, 5957, 6156, 5957, 6156]
    for calculado, exp in zip(r.consumo_mensal, esperado):
        assert calculado == pytest.approx(exp, rel=TOL)


def test_cobertura_e_produtividade(resultado):
    _, r = resultado
    assert r.cobertura * 100 == pytest.approx(119.8, rel=TOL)
    assert r.produtividade == pytest.approx(130.8, rel=TOL)


def test_custos_e_economia(resultado):
    _, r = resultado
    assert r.custo_mensal_atual == pytest.approx(8_290.82, rel=TOL)
    assert r.custo_mensal_com_sistema == pytest.approx(1_517.29, rel=TOL)
    assert r.economia_mensal_ano1 == pytest.approx(6_773.54, rel=TOL)


def test_payback(resultado):
    _, r = resultado
    assert r.payback_meses == pytest.approx(13.7, abs=0.2)


def test_rs_por_wp(resultado):
    _, r = resultado
    assert r.rs_por_wp == pytest.approx(1.67, rel=TOL)


def test_fluxo_de_caixa(resultado):
    _, r = resultado
    esperado = {
        1: (81_282.43, -11_220.38),
        2: (81_089.19, 69_868.81),
        3: (81_944.55, 151_813.36),
        5: (88_631.23, 325_666.92),
        10: (107_833.44, 824_924.45),
        15: (131_195.87, 1_432_347.57),
        20: (159_619.83, 2_171_370.67),
        25: (194_201.93, 3_070_505.27),
    }
    por_ano = {item["ano"]: item for item in r.fluxo}
    for ano, (economia_esp, acumulado_esp) in esperado.items():
        item = por_ano[ano]
        assert item["economia"] == pytest.approx(economia_esp, rel=TOL)
        assert item["acumulado"] == pytest.approx(acumulado_esp, rel=TOL)


def test_economia_acumulada_e_saldo_liquido_25_anos(resultado):
    _, r = resultado
    economia_acumulada = sum(item["economia"] for item in r.fluxo)
    saldo_liquido = r.fluxo[-1]["acumulado"]
    assert economia_acumulada == pytest.approx(3_163_008.08, rel=TOL)
    assert saldo_liquido == pytest.approx(3_070_505.27, rel=TOL)


def test_alertas(resultado):
    _, r = resultado
    texto_alertas = " ".join(r.alertas)
    assert "B1" in texto_alertas
    assert "CC/CA" in texto_alertas
    razao_cc_ca = 55.35 / 40
    assert razao_cc_ca == pytest.approx(1.38, rel=TOL)
