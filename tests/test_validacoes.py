"""Fatia v2.1: validação e limpeza dos campos digitados (core/validacoes.py, D24)."""

from decimal import Decimal

import pytest

from core.validacoes import (
    formatar_cpf_cnpj,
    formatar_telefone,
    limpar_cpf_cnpj,
    limpar_nome,
    limpar_reais,
    limpar_telefone,
)


@pytest.mark.parametrize("digitado, esperado", [
    ("529.982.247-25", "52998224725"),
    ("52998224725", "52998224725"),
    (" 529 982 247 25 ", "52998224725"),
    ("11.222.333/0001-81", "11222333000181"),
    ("", ""),
])
def test_cpf_cnpj_aceitos(digitado, esperado):
    assert limpar_cpf_cnpj(digitado) == esperado


@pytest.mark.parametrize("digitado", [
    "123abc",
    "529.982.247-26",       # dígito errado
    "111.111.111-11",       # todos iguais
    "11.222.333/0001-80",   # dígito errado
    "1234567",              # tamanho
])
def test_cpf_cnpj_recusados(digitado):
    with pytest.raises(ValueError):
        limpar_cpf_cnpj(digitado)


@pytest.mark.parametrize("digitado, esperado", [
    ("(63) 99999-1234", "63999991234"),
    ("63999991234", "63999991234"),
    ("+55 63 99999-1234", "63999991234"),
    ("063 99999-1234", "63999991234"),
    ("(63) 3312-4567", "6333124567"),
])
def test_telefone_aceito(digitado, esperado):
    assert limpar_telefone(digitado) == esperado


@pytest.mark.parametrize("digitado", [
    "",
    "99999-1234",         # sem DDD
    "(20) 99999-1234",    # DDD inexistente
    "(63) 89999-1234",    # 11 dígitos sem 9 na frente
    "63 9999a1234",
])
def test_telefone_recusado(digitado):
    with pytest.raises(ValueError):
        limpar_telefone(digitado)


@pytest.mark.parametrize("digitado, esperado", [
    ("1.234,56", Decimal("1234.56")),
    ("R$ 500", Decimal("500.00")),
    ("500,5", Decimal("500.50")),
    ("1234", Decimal("1234.00")),
    ("12.345.678,90", Decimal("12345678.90")),
])
def test_reais_aceitos(digitado, esperado):
    assert limpar_reais(digitado) == esperado


@pytest.mark.parametrize("digitado", ["", "abc", "1,234.56", "12,345", "1.23,00", "R$"])
def test_reais_recusados(digitado):
    with pytest.raises(ValueError):
        limpar_reais(digitado)


def test_nome_sem_espacos_sobrando():
    assert limpar_nome("  João   da  Silva ") == "João da Silva"
    with pytest.raises(ValueError):
        limpar_nome("   ")


def test_formatacao():
    assert formatar_cpf_cnpj("52998224725") == "529.982.247-25"
    assert formatar_cpf_cnpj("11222333000181") == "11.222.333/0001-81"
    assert formatar_telefone("63999991234") == "(63) 99999-1234"
    assert formatar_telefone("6333124567") == "(63) 3312-4567"
