"""Fatia 5: PDF da proposta (gráficos, cores, anexo da fatura).

O Playwright é trocado por um PDF falso nos testes da view (como no orçamento),
para os testes rodarem sem Chromium. A mescla do anexo usa PDFs de verdade,
gerados pelo pypdf.
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from pypdf import PdfReader, PdfWriter

from propostas.views import documento
from propostas.models import Proposta
from propostas.services import graficos
from propostas.services.pdf import ler_cores, mesclar_anexo

from .test_proposta_v2 import _passo1, _passo2, _passo3

CORES = {"navy": "#123643", "gold": "#D4A429", "ink": "#1E2A30", "muted": "#6B7A80", "line": "#DCE2E4", "erro": "#B4442F"}


def _pdf_em_branco(n_paginas, largura=595, altura=842):
    escritor = PdfWriter()
    for _ in range(n_paginas):
        escritor.add_blank_page(width=largura, height=altura)
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def test_ler_cores_de_tokens_css(settings):
    from pathlib import Path

    cores = ler_cores(Path(settings.BASE_DIR) / "static" / "css" / "tokens.css")
    assert cores["navy"] == "#123643"
    assert cores["gold"] == "#D4A429"


def test_graficos_geram_svg_com_fonte_da_pagina():
    svg = graficos.grafico_geracao_consumo([7000] * 12, [6000] * 12, CORES)
    assert svg.startswith("<svg")
    assert "Poppins" in svg and "DejaVu" not in svg
    assert graficos.grafico_fluxo_acumulado(
        [{"ano": 1, "economia": 10, "acumulado": -5}, {"ano": 2, "economia": 10, "acumulado": 5}], CORES
    ).startswith("<svg")


def test_mesclar_anexo_carimba_nas_ultimas_paginas():
    proposta = _pdf_em_branco(9)
    anexo = _pdf_em_branco(2, largura=842, altura=595)  # paisagem: tem que caber reduzida
    resultado = PdfReader(io.BytesIO(mesclar_anexo(proposta, anexo)))
    assert len(resultado.pages) == 9


def test_pdf_com_fatura_anexada(base, monkeypatch, settings, tmp_path):
    """Proposta confirmada: a fatura entra como Anexo I, depois das 7 páginas fixas."""
    settings.MEDIA_ROOT = tmp_path
    html_recebido = {}

    def falso_html_para_pdf(html):
        html_recebido["html"] = html
        return _pdf_em_branco(9)  # 7 páginas fixas + 2 molduras do anexo

    monkeypatch.setattr(documento, "html_para_pdf", falso_html_para_pdf)
    navegador = Client()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base, origem_consumo="fatura", conta_informada="", numero_uc="123456",
            endereco="Rua 1", competencia="2026-09-01", fatura_kwh="620", dias_ciclo="31", valor_fatura="845,30",
            cpf_cnpj="529.982.247-25",
            arquivo_fatura=SimpleUploadedFile("fatura.pdf", _pdf_em_branco(2), content_type="application/pdf"))
    _passo3(navegador, proposta)
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    resposta = navegador.get(reverse("propostas:pdf", args=[proposta.pk]))

    assert resposta.status_code == 200
    assert resposta["Content-Type"] == "application/pdf"
    assert len(PdfReader(io.BytesIO(resposta.content)).pages) == 9
    assert "Anexo I" in html_recebido["html"]
    assert "9/9" in html_recebido["html"]
    assert "file://" in html_recebido["html"]  # CSS e fontes carregados do disco no PDF
