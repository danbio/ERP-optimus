"""Gráficos da proposta: matplotlib → SVG (string), inserido inline no template do PDF.

Funções puras, sem import de Django. As cores vêm por parâmetro (valores de
tokens.css), para não repetir cor literal aqui. O texto do SVG fica como texto
(svg.fonttype = "none"): o matplotlib mede com a DejaVu Sans, que vem com ele,
e no SVG o nome da fonte é trocado por Poppins, que a página já carrega.
"""

import io

import matplotlib

matplotlib.use("Agg")  # sem janela: só gera arquivo

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _milhar(valor):
    """1234567 → '1.234.567' (separador brasileiro)."""
    return f"{valor:,.0f}".replace(",", ".")


def _para_svg(figura):
    buffer = io.StringIO()
    figura.savefig(buffer, format="svg", bbox_inches="tight", transparent=True)
    plt.close(figura)
    svg = buffer.getvalue()
    # Remove o cabeçalho XML/DOCTYPE: o SVG vai inline dentro do HTML.
    return svg[svg.index("<svg"):].replace("'DejaVu Sans'", "Poppins, sans-serif")


def _preparar(largura_cm, altura_cm, cores):
    plt.rcParams.update({
        "svg.fonttype": "none",
        "font.family": "DejaVu Sans",
        "font.size": 7,
        "text.color": cores["muted"],
        "axes.labelcolor": cores["muted"],
        "xtick.color": cores["muted"],
        "ytick.color": cores["muted"],
    })
    figura, eixo = plt.subplots(figsize=(largura_cm / 2.54, altura_cm / 2.54))
    for lado in ("top", "right", "left"):
        eixo.spines[lado].set_visible(False)
    eixo.spines["bottom"].set_color(cores["line"])
    eixo.tick_params(length=0)
    eixo.grid(axis="y", color=cores["line"], linewidth=0.5)
    eixo.set_axisbelow(True)
    return figura, eixo


def grafico_geracao_consumo(geracao_mensal, consumo_mensal, cores, largura_cm=18, altura_cm=7.5):
    """Barras (geração) + linha (consumo), 12 meses."""
    figura, eixo = _preparar(largura_cm, altura_cm, cores)
    posicoes = range(12)
    barras = eixo.bar(posicoes, geracao_mensal, color=cores["gold"], width=0.62, label="Geração estimada")
    for barra, valor in zip(barras, geracao_mensal):
        eixo.annotate(_milhar(valor), (barra.get_x() + barra.get_width() / 2, valor),
                      xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=5.5)
    eixo.plot(posicoes, consumo_mensal, color=cores["navy"], marker="o", markersize=3, linewidth=1.4,
              label="Consumo (média diária da fatura × dias do mês)")
    eixo.set_xticks(list(posicoes), MESES)
    eixo.set_ylabel("kWh")
    eixo.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _milhar(v)))
    eixo.set_ylim(0, max(max(geracao_mensal), max(consumo_mensal)) * 1.15)
    eixo.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)
    return _para_svg(figura)


def grafico_fluxo_acumulado(fluxo, cores, largura_cm=18, altura_cm=7):
    """Barras do saldo acumulado por ano (negativo em vermelho, positivo em dourado)."""
    figura, eixo = _preparar(largura_cm, altura_cm, cores)
    anos = [linha["ano"] for linha in fluxo]
    acumulados = [linha["acumulado"] for linha in fluxo]
    cores_barras = [cores["erro"] if valor < 0 else cores["gold"] for valor in acumulados]
    eixo.bar(anos, acumulados, color=cores_barras, width=0.66)
    eixo.axhline(0, color=cores["ink"], linewidth=0.6)
    eixo.set_xticks(anos[::2] if len(anos) > 15 else anos)
    eixo.set_xlabel("Ano")
    eixo.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"R$ {_milhar(v / 1000)} mil"))
    return _para_svg(figura)
