"""PDF da proposta: cores para os gráficos e mescla da fatura (Anexo I) com pypdf.

Funções puras, sem import de Django. A renderização HTML → PDF fica em
core/pdf.py (Playwright, D15); aqui só se lida com o PDF já gerado.

Como o anexo funciona: o HTML da proposta já traz, no fim, uma página
"moldura" (cabeçalho, título e rodapé com n/total) para cada página da fatura.
Depois de gerado o PDF, cada página da fatura é reduzida e carimbada dentro
da área livre da sua moldura. Assim a numeração n/total sai certa sem
segunda renderização.
"""

import io
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation

MM = 72 / 25.4  # pontos PDF por milímetro

# Área livre da moldura do anexo, em mm a partir do canto superior esquerdo da
# página A4. Tem que bater com .pagina--anexo em static/css/proposta.css.
AREA_ANEXO_MM = {"esquerda": 14, "topo": 38, "largura": 182, "altura": 239}


class ErroAnexo(Exception):
    """O arquivo da fatura não pôde ser lido como PDF."""


def ler_cores(caminho_tokens: Path) -> dict[str, str]:
    """Lê as cores (--nome: #hex;) de tokens.css, a única fonte das cores do sistema."""
    texto = Path(caminho_tokens).read_text(encoding="utf-8")
    return {nome: valor for nome, valor in re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{3,8})\s*;", texto)}


def contar_paginas(pdf: bytes) -> int:
    try:
        return len(PdfReader(io.BytesIO(pdf)).pages)
    except Exception as erro:
        raise ErroAnexo(f"O arquivo da fatura não é um PDF válido: {erro}") from erro


def mesclar_anexo(pdf_proposta: bytes, pdf_anexo: bytes, area_mm: dict = AREA_ANEXO_MM) -> bytes:
    """Carimba cada página do anexo nas últimas páginas (molduras) da proposta."""
    proposta = PdfReader(io.BytesIO(pdf_proposta))
    try:
        anexo = PdfReader(io.BytesIO(pdf_anexo))
    except Exception as erro:
        raise ErroAnexo(f"O arquivo da fatura não é um PDF válido: {erro}") from erro

    n_anexo = len(anexo.pages)
    primeira_moldura = len(proposta.pages) - n_anexo
    if primeira_moldura < 0:
        raise ErroAnexo("A proposta tem menos páginas que o anexo: faltam as molduras.")

    saida = PdfWriter()
    saida.append(proposta)

    area_larg = area_mm["largura"] * MM
    area_alt = area_mm["altura"] * MM
    for indice, pagina_anexo in enumerate(anexo.pages):
        pagina_anexo.transfer_rotation_to_content()
        caixa = pagina_anexo.mediabox
        larg, alt = float(caixa.width), float(caixa.height)
        escala = min(area_larg / larg, area_alt / alt)

        moldura = saida.pages[primeira_moldura + indice]
        altura_moldura = float(moldura.mediabox.height)
        x = area_mm["esquerda"] * MM + (area_larg - larg * escala) / 2
        y = altura_moldura - area_mm["topo"] * MM - alt * escala

        transformacao = (
            Transformation()
            .translate(-float(caixa.left), -float(caixa.bottom))
            .scale(escala)
            .translate(x, y)
        )
        moldura.merge_transformed_page(pagina_anexo, transformacao)

    buffer = io.BytesIO()
    saida.write(buffer)
    return buffer.getvalue()
