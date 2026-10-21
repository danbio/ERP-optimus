"""HTML → PDF com Chromium headless via Playwright (D04/D15).

O HTML é gravado num arquivo temporário e aberto como file://, assim o CSS,
as fontes e as imagens são carregados de static/ por caminho absoluto
(o template recebe `base_estatico` = static/ como URI file://).

Instalação no Windows (uma vez):
    pip install playwright
    python -m playwright install chromium
"""

import tempfile
from pathlib import Path


class ErroPDF(Exception):
    """Falha ao gerar o PDF (Playwright/Chromium ausente ou erro de renderização)."""


def html_para_pdf(html: str, rodape_html: str = "") -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as erro:
        raise ErroPDF(
            "Playwright não instalado. No PowerShell, com o .venv ativo: "
            "pip install playwright  e depois  python -m playwright install chromium"
        ) from erro

    opcoes = {
        "format": "A4",
        "print_background": True,
        "prefer_css_page_size": True,
    }
    if rodape_html:
        # O rodapé do Chromium não herda o CSS da página: estilos inline são obrigatórios aqui.
        opcoes.update(
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=rodape_html,
        )

    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "documento.html"
        arquivo.write_text(html, encoding="utf-8")
        try:
            with sync_playwright() as p:
                navegador = p.chromium.launch()
                pagina = navegador.new_page()
                pagina.goto(arquivo.as_uri(), wait_until="load")
                pagina.evaluate("document.fonts.ready")
                pdf = pagina.pdf(**opcoes)
                navegador.close()
        except Exception as erro:
            raise ErroPDF(f"Falha ao gerar o PDF: {erro}") from erro
    return pdf
