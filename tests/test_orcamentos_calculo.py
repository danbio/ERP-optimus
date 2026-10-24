"""Motor de preço do orçamento Intelbras (D14): funções puras."""

from decimal import Decimal as D

from orcamentos.services.calculo import (
    Linha, ler_decimal, markup_para, markup_por_preco, preco_por_markup, resumir,
)


def test_ler_decimal_formatos_brasileiros():
    assert ler_decimal("1.234,56") == D("1234.56")
    assert ler_decimal("R$ 1.234,56") == D("1234.56")
    assert ler_decimal("1234.56") == D("1234.56")
    assert ler_decimal("30%") == D("30")
    assert ler_decimal("") is None
    assert ler_decimal("abc", D("0")) == D("0")


def test_markup_ida_e_volta():
    # Automatizador basculante 4661402 (out/2026): PSD 359,65 · PSCF 468,20
    assert preco_por_markup(D("359.65"), D("30")) == D("467.55")
    assert markup_por_preco(D("359.65"), D("468.20")) == D("30.18")
    assert markup_por_preco(D("0"), D("10")) is None


def test_markup_por_segmento_com_padrao():
    markups = {"CFTV IP": D("40")}
    assert markup_para("CFTV IP", markups, D("30")) == D("40")
    assert markup_para("Alarmes", markups, D("30")) == D("30")


def test_resumo_totais_margem_e_desconto():
    linhas = [
        Linha("intelbras", "Câmera", D("4"), D("100"), D("130"), pscf_unitario=D("130")),
        Linha("material", "Cabo", D("2"), D("50"), D("80")),
        Linha("servico", "Instalação", D("1"), D("0"), D("400")),
    ]
    r = resumir(linhas, D("10"))
    assert r.total_intelbras == D("520.00")
    assert r.total_materiais == D("160.00")
    assert r.total_servicos == D("400.00")
    assert r.subtotal == D("1080.00")
    assert r.desconto_valor == D("108.00")
    assert r.total == D("972.00")
    assert r.custo_total == D("500.00")
    assert r.margem_valor == D("472.00")
    assert r.margem_pct == D("48.56")
    assert r.alertas == []


def test_alertas_de_item():
    linhas = [
        Linha("intelbras", "Licença", D("1"), D("0"), D("65")),
        Linha("intelbras", "Câmera", D("1"), D("100"), D("90"), pscf_unitario=D("130")),
        Linha("intelbras", "Câmera cara", D("1"), D("100"), D("150"), pscf_unitario=D("130")),
        Linha("intelbras", "Cabo", D("3"), D("10"), D("13")),
        Linha("intelbras", "Antigo", D("1"), D("10"), D("13"), em_encerramento=True, substituto="4301419 - FS 1000"),
    ]
    r = resumir(linhas)
    assert "PSD zerado" in r.alertas_por_linha[0][0]
    assert r.alertas_por_linha[1] == ["Preço abaixo do custo."]
    assert "Acima do PSCF" in r.alertas_por_linha[2][0]
    assert r.alertas_por_linha[3] == []  # múltiplos não valem para a Optimus (D39)
    assert "4301419" in r.alertas_por_linha[4][0]
    assert "4 item(ns) com alerta" in r.alertas[0]


def test_desconto_abaixo_do_custo_alerta():
    r = resumir([Linha("intelbras", "X", D("1"), D("100"), D("110"))], D("20"))
    assert r.total == D("88.00")
    assert "abaixo do custo" in r.alertas[0]
