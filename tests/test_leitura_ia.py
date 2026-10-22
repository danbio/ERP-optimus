"""Rodada 5: leitura de fatura e cotação por IA, com o Gemini simulado (D35, D37)."""

import io
import json
import urllib.error
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as Navegador
from django.urls import reverse

from core import ia
from propostas.models import Cotacao
from propostas.services import leitura_ia

from .test_proposta_v2 import _ate_passo2

PDF = b"%PDF-1.4 fatura de teste"

FATURA_LIDA = {
    "titular": "MARIA SOUZA", "cpf_cnpj": "529.982.247-25", "numero_uc": "10/123456-7",
    "endereco": "Rua 7, 120, Centro, Gurupi-TO", "mes_referencia": "2026-09", "consumo_kwh": 612.0,
    "dias_ciclo": 31, "valor_total": 845.3,
}

COTACAO_LIDA = {
    "distribuidor": "Belenus", "numero": "WEB-007005988", "data": "2026-10-21", "validade": "2026-10-28",
    "kwp": 12.81, "total_produtos": 25683.58, "frete": 1982.86, "total": 27666.44,
    "itens": [
        {"codigo": "MFTF-0.4-BF-132-610W", "descricao": "Módulo Huansheng 610 W", "quantidade": 21, "unidade": "un"},
        {"codigo": "", "descricao": "Cabo solar 4 mm preto", "quantidade": 100, "unidade": "M"},
        {"codigo": "", "descricao": "", "quantidade": 1, "unidade": "un"},
    ],
}


def _pdf(nome="arquivo.pdf"):
    return SimpleUploadedFile(nome, PDF, content_type="application/pdf")


# ---------- Conversão da resposta (funções puras) ----------

def test_campos_da_fatura():
    campos = leitura_ia.campos_da_fatura(FATURA_LIDA)
    assert campos == {
        "numero_uc": "10/123456-7", "endereco": "Rua 7, 120, Centro, Gurupi-TO", "competencia": "2026-09-01",
        "fatura_kwh": "612", "dias_ciclo": "31", "valor_fatura": "845,30", "cpf_cnpj": "529.982.247-25",
        "titular": "MARIA SOUZA",
    }


def test_fatura_com_cpf_mascarado_e_mes_invalido_fica_em_branco():
    campos = leitura_ia.campos_da_fatura(FATURA_LIDA | {"cpf_cnpj": "***.982.247-**", "mes_referencia": "2026-13",
                                                         "consumo_kwh": 0, "valor_total": "abc"})
    assert (campos["cpf_cnpj"], campos["competencia"], campos["fatura_kwh"], campos["valor_fatura"]) == ("", "", "", "")


def test_campos_da_cotacao():
    cabecalho, itens = leitura_ia.campos_da_cotacao(COTACAO_LIDA)
    assert cabecalho == {
        "distribuidor": "Belenus", "numero": "WEB-007005988", "data": "2026-10-21", "validade": "2026-10-28",
        "kwp": "12,81", "total_produtos": "25.683,58", "frete": "1.982,86", "total": "27.666,44",
    }
    assert itens == [  # o item sem descrição é descartado
        {"codigo": "MFTF-0.4-BF-132-610W", "descricao": "Módulo Huansheng 610 W", "quantidade": "21", "unidade": "un"},
        {"codigo": "", "descricao": "Cabo solar 4 mm preto", "quantidade": "100", "unidade": "m"},
    ]


# ---------- Chamada ao Gemini (HTTP simulado) ----------

class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_ler_pdf_sem_chave(settings):
    settings.GEMINI_API_KEY = ""
    with pytest.raises(ia.ErroLeitura, match="GEMINI_API_KEY"):
        ia.ler_pdf(PDF, "x", {})


def test_ler_pdf_recusa_arquivo_que_nao_e_pdf(settings):
    settings.GEMINI_API_KEY = "chave-de-teste"
    with pytest.raises(ia.ErroLeitura, match="não é um PDF"):
        ia.ler_pdf(b"GIF89a", "x", {})


def test_ler_pdf_monta_o_pedido_e_le_o_json(settings, monkeypatch):
    settings.GEMINI_API_KEY, settings.GEMINI_MODELO = "chave-de-teste", "gemini-teste"
    pedidos = []

    def urlopen_falso(pedido, timeout):
        pedidos.append(pedido)
        corpo = {"candidates": [{"content": {"parts": [{"text": json.dumps({"numero_uc": "123"})}]}}]}
        return RespostaFalsa(json.dumps(corpo).encode())

    monkeypatch.setattr(ia.urllib.request, "urlopen", urlopen_falso)
    assert ia.ler_pdf(PDF, "leia", {"type": "OBJECT"}) == {"numero_uc": "123"}
    pedido = pedidos[0]
    assert pedido.full_url.endswith("/models/gemini-teste:generateContent")
    assert pedido.get_header("X-goog-api-key") == "chave-de-teste"
    corpo = json.loads(pedido.data)
    assert corpo["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "application/pdf"
    assert corpo["generationConfig"]["responseMimeType"] == "application/json"


@pytest.mark.parametrize("codigo, trecho", [(403, "recusada"), (429, "Limite"), (500, "respondeu com erro")])
def test_ler_pdf_traduz_os_erros(settings, monkeypatch, codigo, trecho):
    settings.GEMINI_API_KEY = "chave-de-teste"

    def urlopen_falso(pedido, timeout):
        raise urllib.error.HTTPError(pedido.full_url, codigo, "erro", {}, None)

    monkeypatch.setattr(ia.urllib.request, "urlopen", urlopen_falso)
    with pytest.raises(ia.ErroLeitura, match=trecho):
        ia.ler_pdf(PDF, "x", {})


# ---------- Telas ----------

def test_fatura_lida_preenche_o_passo2_sem_gravar(base, monkeypatch):
    monkeypatch.setattr(ia, "ler_pdf", lambda conteudo, instrucao, esquema: FATURA_LIDA | {"titular": "João Lima"})
    navegador, proposta = _ate_passo2(base)
    resposta = navegador.post(reverse("propostas:ler_fatura", args=[proposta.pk]),
                              {"arquivo_fatura": _pdf(), "numero_uc": ""})
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert 'value="10/123456-7"' in html and 'value="845,30"' in html and 'value="2026-09-01"' in html
    assert "Confira cada campo" in html
    assert "no nome de João Lima" in html  # titular diferente do cliente
    proposta.refresh_from_db()
    assert proposta.fatura is None and proposta.nivel == "estimativa"


def test_fatura_sem_arquivo_ou_sem_chave_avisa(base, settings):
    settings.GEMINI_API_KEY = ""
    navegador, proposta = _ate_passo2(base)
    url = reverse("propostas:ler_fatura", args=[proposta.pk])
    assert "Escolha o PDF" in navegador.post(url, {"numero_uc": "999"}).content.decode()
    html = navegador.post(url, {"arquivo_fatura": _pdf(), "numero_uc": "999"}).content.decode()
    assert "GEMINI_API_KEY" in html and 'value="999"' in html  # mantém o que o vendedor digitou


def test_cotacao_lida_preenche_dados_e_itens_e_salva(db, monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(ia, "ler_pdf", lambda conteudo, instrucao, esquema: COTACAO_LIDA)
    navegador = Navegador()
    html = navegador.post(reverse("propostas:ler_cotacao"), {"arquivo": _pdf()}).content.decode()
    assert 'value="WEB-007005988"' in html and 'value="27.666,44"' in html
    assert 'value="MFTF-0.4-BF-132-610W"' in html and 'name="item-TOTAL_FORMS" value="4"' in html
    # O vendedor confere e salva com o formulário normal.
    dados = {"distribuidor": "Belenus", "numero": "WEB-007005988", "data": "2026-10-21", "validade": "2026-10-28",
             "kwp": "12,81", "total_produtos": "25.683,58", "frete": "1.982,86", "total": "27.666,44",
             "observacao": "", "arquivo": _pdf("cotacao.pdf"),
             "item-TOTAL_FORMS": "2", "item-INITIAL_FORMS": "0", "item-MIN_NUM_FORMS": "0", "item-MAX_NUM_FORMS": "1000",
             "item-0-codigo": "MFTF-0.4-BF-132-610W", "item-0-descricao": "Módulo Huansheng 610 W",
             "item-0-quantidade": "21", "item-0-unidade": "un",
             "item-1-codigo": "", "item-1-descricao": "Cabo solar 4 mm preto", "item-1-quantidade": "100",
             "item-1-unidade": "m"}
    assert navegador.post(reverse("propostas:solar_cotacao_nova"), dados).status_code == 302
    cotacao = Cotacao.objects.filter(numero="WEB-007005988").latest("pk")
    assert cotacao.total == Decimal("27666.44") and cotacao.itens.count() == 2
    assert cotacao.itens.get(codigo="MFTF-0.4-BF-132-610W").equipamento is not None  # ligado ao catálogo


def test_cotacao_com_erro_de_leitura_mantem_o_digitado(db, monkeypatch):
    def falha(conteudo, instrucao, esquema):
        raise ia.ErroLeitura("A IA não conseguiu ler este PDF. Preencha os campos à mão.")

    monkeypatch.setattr(ia, "ler_pdf", falha)
    html = Navegador().post(reverse("propostas:ler_cotacao"), {
        "arquivo": _pdf(), "numero": "123", "item-TOTAL_FORMS": "1", "item-INITIAL_FORMS": "0",
        "item-MIN_NUM_FORMS": "0", "item-MAX_NUM_FORMS": "1000", "item-0-descricao": "Inversor X",
        "item-0-quantidade": "1", "item-0-unidade": "un", "item-0-codigo": ""}).content.decode()
    assert "não conseguiu ler" in html and 'value="123"' in html and 'value="Inversor X"' in html
