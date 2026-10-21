"""Fatia 5: PDF da proposta.

O Playwright é trocado por um PDF falso nos testes da view (como no orçamento),
para os testes rodarem sem Chromium. A mescla do anexo usa PDFs de verdade,
gerados pelo pypdf.
"""

import io
from datetime import date

import pytest
from django.core.files.base import ContentFile
from django.test import Client
from django.urls import reverse
from pypdf import PdfReader, PdfWriter

from core.models import ConfigEmpresa
from propostas import views
from propostas.models import ItemKit, Proposta
from propostas.services import graficos
from propostas.services.pdf import ler_cores, mesclar_anexo

from .test_fatia4_proposta_view import fatura_alesio, uc_alesio  # noqa: F401 (fixtures)

CORES = {"navy": "#123643", "gold": "#D4A429", "ink": "#1E2A30", "muted": "#6B7A80", "line": "#DCE2E4", "erro": "#B4442F"}


def _pdf_em_branco(n_paginas, largura=595, altura=842):
    escritor = PdfWriter()
    for _ in range(n_paginas):
        escritor.add_blank_page(width=largura, height=altura)
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def proposta_alesio(uc_alesio, fatura_alesio):  # noqa: F811
    config = ConfigEmpresa.obter()
    proposta = Proposta.objects.create(
        numero="OPT-2026-0001", cliente=uc_alesio.cliente, uc=uc_alesio, fatura=fatura_alesio, investimento="92502.81",
        forma_pagamento="A combinar", validade_dias=15, beneficios=config.beneficios_padrao,
        escopo=config.escopo_padrao, texto_sobre=config.texto_sobre, premissas=config.premissas_padrao,
        emissao=date(2026, 10, 15),
    )
    ItemKit.objects.create(proposta=proposta, tipo="modulo", descricao="Módulo Huansheng 615 W",
                           quantidade=90, potencia_w=615, ordem=0)
    ItemKit.objects.create(proposta=proposta, tipo="inversor", descricao="Inversor Deye SUN-20K-G05",
                           quantidade=2, potencia_w=20000, ordem=1)
    return proposta


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


@pytest.mark.django_db
def test_preview_mostra_numeros_do_caso_alesio(proposta_alesio):
    resposta = Client().get(reverse("propostas:preview", args=[proposta_alesio.pk]))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "On-grid 55,35 kWp" in html
    assert "7.237 kWh" in html  # geração média mensal
    assert "R$ 6.774" in html  # economia mensal (1º ano)
    assert "≈ 14 meses" in html  # payback
    assert "R$ 1,67 por Wp" in html
    assert "R$ 3.070.505" in html  # saldo acumulado ano 25
    assert "75% (2027), 90% (2028) e 100% (2029 em diante)" in html
    assert "/7</span>" in html  # sem fatura anexada: 7 páginas
    assert "<svg" in html


@pytest.mark.django_db
def test_pdf_com_fatura_anexada(proposta_alesio, monkeypatch):
    fatura = proposta_alesio.fatura
    fatura.arquivo.save("fatura.pdf", ContentFile(_pdf_em_branco(2)), save=True)

    html_recebido = {}

    def falso_html_para_pdf(html):
        html_recebido["html"] = html
        return _pdf_em_branco(9)  # 7 páginas fixas + 2 molduras do anexo

    monkeypatch.setattr(views, "html_para_pdf", falso_html_para_pdf)
    resposta = Client().get(reverse("propostas:pdf", args=[proposta_alesio.pk]))

    assert resposta.status_code == 200
    assert resposta["Content-Type"] == "application/pdf"
    assert len(PdfReader(io.BytesIO(resposta.content)).pages) == 9
    assert "Anexo I" in html_recebido["html"]
    assert "9/9" in html_recebido["html"]
    assert "file://" in html_recebido["html"]  # CSS e fontes carregados do disco no PDF
