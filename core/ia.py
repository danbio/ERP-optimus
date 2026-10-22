"""Leitura de PDF por IA (D37): Gemini, chamado por HTTP com a biblioteca padrão (sem dependência nova).

`ler_pdf()` manda o PDF e a instrução e devolve o JSON no formato do esquema pedido.
O que pedir em cada documento fica em `propostas/services/leitura_ia.py`.
"""

import base64
import json
import urllib.error
import urllib.request

from django.conf import settings

ENDERECO = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
LIMITE_PDF = 15 * 1024 * 1024  # o Gemini aceita até 20 MB por chamada, com o base64 junto
ESPERA_SEGUNDOS = 90


class ErroLeitura(Exception):
    """A leitura não foi feita. A mensagem é para o vendedor ler."""


def configurada():
    return bool(settings.GEMINI_API_KEY)


def ler_pdf(conteudo, instrucao, esquema):
    """PDF (bytes) + instrução + esquema (formato `responseSchema` do Gemini) → dict lido pela IA."""
    if not configurada():
        raise ErroLeitura("A leitura por IA não está configurada: falta GEMINI_API_KEY no arquivo .env.")
    if not conteudo.startswith(b"%PDF"):
        raise ErroLeitura("O arquivo não é um PDF.")
    if len(conteudo) > LIMITE_PDF:
        raise ErroLeitura("PDF grande demais para a leitura por IA (máximo 15 MB).")
    corpo = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(conteudo).decode()}},
            {"text": instrucao},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": esquema, "temperature": 0},
    }
    pedido = urllib.request.Request(
        ENDERECO.format(modelo=settings.GEMINI_MODELO), data=json.dumps(corpo).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": settings.GEMINI_API_KEY},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=ESPERA_SEGUNDOS) as resposta:
            dados = json.loads(resposta.read())
    except urllib.error.HTTPError as erro:
        raise ErroLeitura(_mensagem_do_erro(erro.code)) from erro
    except (urllib.error.URLError, TimeoutError) as erro:
        raise ErroLeitura("Sem resposta do serviço de IA. Confira a internet e tente de novo.") from erro
    try:
        texto = dados["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(texto)
    except (KeyError, IndexError, ValueError) as erro:
        raise ErroLeitura("A IA não conseguiu ler este PDF. Preencha os campos à mão.") from erro


def _mensagem_do_erro(codigo):
    if codigo in (401, 403):
        return "A chave da IA (GEMINI_API_KEY) foi recusada. Confira a chave no arquivo .env."
    if codigo == 429:
        return "Limite de uso da IA atingido. Espere um minuto e tente de novo."
    if codigo == 404:
        return "Modelo de IA não encontrado. Confira GEMINI_MODELO no arquivo .env."
    return f"O serviço de IA respondeu com erro ({codigo}). Tente de novo ou preencha à mão."
