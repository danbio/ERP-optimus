"""Rodada 10: orçamento Intelbras com preço oculto e parcelamento no PDF (H09, H10, D44)."""

from decimal import Decimal as D

import pytest
from django.test import Client as Navegador
from django.urls import reverse

from clientes.models import Cliente
from orcamentos.models import ItemOrcamento, Orcamento, ParametrosOrcamento
from orcamentos.services.calculo import parcelamento


def test_parcelamento_sem_juros_e_com_acrescimo():
    linhas = parcelamento(D("1000.00"), [{"parcelas": 12, "acrescimo": 0.1}, {"parcelas": 3, "acrescimo": 0}])
    assert [l["parcelas"] for l in linhas] == [3, 12]
    assert linhas[0]["parcela"] == D("333.33") and linhas[0]["total"] == D("1000.00")
    assert linhas[1]["parcela"] == D("91.67") and linhas[1]["total"] == D("1100.00")


def test_prazo_sem_acrescimo_informado_fica_de_fora():
    assert parcelamento(D("1000"), [{"parcelas": 21, "acrescimo": None}]) == []
    assert parcelamento(D("0"), [{"parcelas": 3, "acrescimo": 0}]) == []


@pytest.fixture
def orcamento(db):
    cliente = Cliente.objects.create(nome="Posto Gurupi", telefone="63999991234")
    orcamento = Orcamento.objects.create(numero="ORC-2026-0001", cliente=cliente, titulo="CFTV")
    ItemOrcamento.objects.create(orcamento=orcamento, tipo="intelbras", descricao="Câmera", quantidade=D("4"),
                                 custo_unitario=D("200"), preco_unitario=D("287.65"), ordem=1)
    ItemOrcamento.objects.create(orcamento=orcamento, tipo="servico", descricao="Instalação", quantidade=D("1"),
                                 custo_unitario=D("0"), preco_unitario=D("1000"), ordem=2)
    return orcamento


def _previa(orcamento):
    return Navegador().get(reverse("orcamentos:preview", args=[orcamento.pk])).content.decode()


def test_pdf_esconde_preco_dos_itens_e_mantem_subtotal(orcamento):
    assert "287,65" in _previa(orcamento)
    orcamento.mostrar_precos = False
    orcamento.save()
    html = _previa(orcamento)
    assert "287,65" not in html and "Unitário" not in html
    assert 'doc-tabela__qtd">4 ' in html  # a quantidade continua
    assert "1.150,60" in html and "1.000,00" in html  # subtotais de equipamentos e serviços
    assert "2.150,60" in html  # total


def test_pdf_mostra_parcelamento_configurado_e_vendedor_esconde(orcamento):
    assert "Parcelamento" not in _previa(orcamento)  # padrão: o gestor ainda não informou acréscimos
    parametros = ParametrosOrcamento.obter()
    parametros.parcelamento = [{"parcelas": 3, "acrescimo": 0}, {"parcelas": 21, "acrescimo": 0.2}]
    parametros.save()
    html = _previa(orcamento)
    assert "716,87" in html and "sem juros" in html  # 2.150,60 / 3
    assert "122,89" in html and "2.580,72" in html  # 2.150,60 × 1,2 / 21
    orcamento.mostrar_parcelamento = False
    orcamento.save()
    assert "716,87" not in _previa(orcamento)


def test_vendedor_marca_as_opcoes_no_orcamento(orcamento):
    dados = {"cliente": orcamento.cliente.pk, "titulo": "CFTV", "validade_dias": "7", "mostrar_parcelamento": "on"}
    Navegador().post(reverse("orcamentos:editor", args=[orcamento.pk]), dados)
    orcamento.refresh_from_db()
    assert orcamento.mostrar_precos is False and orcamento.mostrar_parcelamento is True


def test_gestor_cadastra_prazos(db):
    navegador = Navegador()
    assert "Parcelamento (Intelbras)" in navegador.get(reverse("core:config_empresa")).content.decode()
    resposta = navegador.post(reverse("orcamentos:config_parcelamento"), {
        "parcelas_0": "12", "acrescimo_0": "8,5", "parcelas_1": "3", "acrescimo_1": "0", "parcelas_2": "6"})
    assert resposta.status_code == 302
    assert ParametrosOrcamento.obter().parcelamento == [
        {"parcelas": 3, "acrescimo": 0.0}, {"parcelas": 6, "acrescimo": None}, {"parcelas": 12, "acrescimo": 0.085}]


@pytest.mark.parametrize("dados", [
    {"parcelas_0": "3", "parcelas_1": "3"},  # repetido
    {"parcelas_0": "", "acrescimo_0": "5"},  # acréscimo sem prazo
    {"parcelas_0": "1"},  # à vista não é parcelamento
    {"parcelas_0": "12", "acrescimo_0": "abc"},
])
def test_prazos_malformados_sao_recusados(db, dados):
    assert Navegador().post(reverse("orcamentos:config_parcelamento"), dados).status_code == 200
