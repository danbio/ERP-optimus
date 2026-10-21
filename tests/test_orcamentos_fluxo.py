"""Fluxo do orçamento Intelbras pelas views: importação → orçamento → emissão → revisão."""

import os
from decimal import Decimal as D
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse

from clientes.models import Cliente
from orcamentos import views
from orcamentos.importacao import aplicar_importacao
from orcamentos.models import ItemOrcamento, MarkupSegmento, Orcamento, Produto, TabelaPreco
from orcamentos.services.tabela_intelbras import LeituraTabela, ler_tabela


def _produto(codigo, psd, pscf, **extra):
    base = {
        "codigo": codigo, "descricao": f"Produto {codigo}", "resumo": f"Produto {codigo}",
        "bu": "PRECISO DE INSTALACAO", "segmento": "CFTV IP", "familia": "Cameras IP",
        "uf_origem": "SC", "ipi": D("0"), "icms": D("0.07"), "psd": D(psd), "pscf": D(pscf),
        "qtd_multipla": 1, "preco_referencia": "PSD", "observacoes": "", "ncm": "",
    }
    return base | extra


@pytest.fixture
def tabela(db):
    return TabelaPreco.objects.create(referencia="OUTUBRO/2026", arquivo="tabelas/x.xlsb", uf_destino="TO")


def test_importacao_cria_atualiza_e_desativa(tabela):
    leitura = LeituraTabela("OUTUBRO", [_produto("1", "100", "130"), _produto("2", "50", "65")], {"2": "3 - Novo"})
    resumo = aplicar_importacao(leitura, tabela)
    assert resumo["novos"] == 2
    assert Produto.objects.get(codigo="2").em_encerramento is True

    leitura2 = LeituraTabela("NOVEMBRO", [_produto("1", "110", "143")], {})
    resumo2 = aplicar_importacao(leitura2, tabela)
    assert resumo2["precos_alterados"] == 1
    assert resumo2["maiores_variacoes"][0]["variacao_pct"] == pytest.approx(10.0)
    assert resumo2["sairam"] == 1
    assert Produto.objects.get(codigo="2").ativo is False
    assert Produto.objects.get(codigo="1").psd == D("110.00")


@pytest.mark.django_db
def test_fluxo_completo(tabela, monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    aplicar_importacao(LeituraTabela("OUTUBRO", [
        _produto("4565330", "200", "260"),
        _produto("4000270", "1000", "1300", segmento="Cabos Metalicos", qtd_multipla=5),
        _produto("9101247", "0", "65", segmento="Comunicacao em Nuvem"),
    ], {}), tabela)
    MarkupSegmento.objects.create(segmento="CFTV IP", markup=D("40"))
    cliente = Cliente.objects.create(nome="Posto Gurupi", cpf_cnpj="12.345.678/0001-90")
    http = Client()

    r = http.post(reverse("orcamentos:novo"), {"cliente": cliente.pk, "titulo": "CFTV 4 câmeras"})
    orcamento = Orcamento.objects.get()
    assert r.url == reverse("orcamentos:editor", args=[orcamento.pk])
    assert orcamento.numero.startswith("ORC-")
    assert orcamento.tabela_referencia == "OUTUBRO/2026"
    assert "Intelbras" in orcamento.garantia  # padrão da carga inicial

    busca = http.get(reverse("orcamentos:buscar_produtos", args=[orcamento.pk]), {"q": "4565"})
    assert b"4565330" in busca.content

    for codigo in ["4565330", "4000270", "9101247"]:
        produto = Produto.objects.get(codigo=codigo)
        assert http.post(reverse("orcamentos:adicionar_produto", args=[orcamento.pk, produto.pk])).status_code == 200
    http.post(reverse("orcamentos:adicionar_avulso", args=[orcamento.pk]), {"tipo": "servico"})

    camera, cabo, licenca, servico = orcamento.itens.order_by("ordem")
    assert camera.preco_unitario == D("280.00")  # markup do segmento (40%)
    assert cabo.preco_unitario == D("1300.00")  # markup padrão (30%)
    assert licenca.preco_unitario == D("65.00")  # sem PSD: usa o PSCF

    url_item = lambda item: reverse("orcamentos:item_atualizar", args=[item.pk])
    http.post(url_item(camera), {"campo": "quantidade", "valor": "4"})
    http.post(url_item(camera), {"campo": "markup", "valor": "35"})
    http.post(url_item(servico), {"campo": "descricao", "valor": "Instalação e configuração"})
    resposta = http.post(url_item(servico), {"campo": "preco", "valor": "1.200,00"})
    assert "múltiplos de 5" in resposta.content.decode()

    camera.refresh_from_db(); servico.refresh_from_db()
    assert camera.quantidade == D("4") and camera.preco_unitario == D("270.00")
    assert servico.preco_unitario == D("1200.00")

    http.post(reverse("orcamentos:desconto", args=[orcamento.pk]), {"desconto_pct": "5"})
    orcamento.refresh_from_db()
    # (4×270 + 1300 + 65 + 1200) × 0,95
    assert orcamento.total == D("3462.75")

    preview = http.get(reverse("orcamentos:preview", args=[orcamento.pk]))
    assert "Equipamentos Intelbras" in preview.content.decode()
    assert "3.462,75" in preview.content.decode()

    monkeypatch.setattr(views, "html_para_pdf", lambda html, rodape: b"%PDF-1.4 teste")
    http.post(reverse("orcamentos:emitir", args=[orcamento.pk]))
    orcamento.refresh_from_db()
    assert orcamento.status == Orcamento.Status.EMITIDO
    assert orcamento.emissao is not None
    assert orcamento.pdf.read() == b"%PDF-1.4 teste"

    # emitido é imutável
    assert http.post(url_item(camera), {"campo": "quantidade", "valor": "9"}).status_code == 404

    http.post(reverse("orcamentos:revisar", args=[orcamento.pk]))
    v2 = Orcamento.objects.get(numero=orcamento.numero, versao=2)
    assert v2.status == Orcamento.Status.RASCUNHO
    assert v2.itens.count() == 4
    assert v2.origem == orcamento
    assert v2.total == orcamento.total


@pytest.mark.skipif(not os.environ.get("INTELBRAS_XLSB"), reason="defina INTELBRAS_XLSB com o caminho da tabela real")
def test_leitura_tabela_real():
    leitura = ler_tabela(Path(os.environ["INTELBRAS_XLSB"]), "TO")
    assert len(leitura.produtos) > 1000
    assert leitura.referencia
    assert all(p["pscf"] >= 0 for p in leitura.produtos)
