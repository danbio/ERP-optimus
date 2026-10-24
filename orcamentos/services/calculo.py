"""Formação de preço e totais do orçamento (D14).

Funções puras, sem import de Django. Dinheiro em Decimal, arredondado a
centavos só na saída de cada função.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTAVO = Decimal("0.01")
CEM = Decimal("100")


def _centavos(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _brl(valor: Decimal) -> str:
    texto = f"{_centavos(valor):,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


def ler_decimal(texto, padrao=None):
    """Aceita "1234.56", "1234,56", "1.234,56" e "R$ 1.234,56"."""
    if texto is None:
        return padrao
    limpo = str(texto).replace("R$", "").replace("%", "").replace(" ", "").strip()
    if not limpo:
        return padrao
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo)
    except InvalidOperation:
        return padrao


def preco_por_markup(custo: Decimal, markup_pct: Decimal) -> Decimal:
    """Preço de venda (R$) = custo × (1 + markup em %)."""
    return _centavos(custo * (1 + markup_pct / CEM))


def markup_por_preco(custo: Decimal, preco: Decimal):
    """Markup (%) que leva do custo ao preço. None quando não há custo."""
    if not custo:
        return None
    return _centavos((preco / custo - 1) * CEM)


def markup_para(segmento: str, markups: dict[str, Decimal], padrao: Decimal) -> Decimal:
    """Markup (%) do segmento, ou o padrão se o segmento não tem um próprio (D14)."""
    return markups.get(segmento, padrao)


@dataclass
class Linha:
    tipo: str  # "intelbras" | "material" | "servico"
    descricao: str
    quantidade: Decimal
    custo_unitario: Decimal
    preco_unitario: Decimal
    pscf_unitario: Decimal | None = None
    ativo_na_tabela: bool = True
    em_encerramento: bool = False
    substituto: str = ""


@dataclass
class Resumo:
    total_intelbras: Decimal
    total_materiais: Decimal
    total_servicos: Decimal
    subtotal: Decimal
    desconto_pct: Decimal
    desconto_valor: Decimal
    total: Decimal
    custo_total: Decimal
    margem_valor: Decimal  # bruta, antes de impostos
    margem_pct: Decimal  # sobre o total de venda
    alertas_por_linha: list[list[str]] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)


def alertas_da_linha(linha: Linha) -> list[str]:
    """Avisos de um item: sem custo, abaixo do custo, acima do PSCF, fora da tabela, em encerramento."""
    alertas = []
    if linha.tipo == "intelbras" and not linha.custo_unitario:
        alertas.append("Sem custo na tabela (PSD zerado): informe o preço manualmente.")
    if linha.custo_unitario and linha.preco_unitario < linha.custo_unitario:
        alertas.append("Preço abaixo do custo.")
    if linha.pscf_unitario and linha.preco_unitario > linha.pscf_unitario:
        alertas.append(f"Acima do PSCF ({_brl(linha.pscf_unitario)}).")
    if not linha.ativo_na_tabela:
        alertas.append("Fora da tabela atual: confirme a disponibilidade.")
    if linha.em_encerramento:
        texto = "Produto em encerramento"
        substituto = linha.substituto if len(linha.substituto) <= 60 else linha.substituto[:57] + "..."
        alertas.append(f"{texto}: substituto {substituto}" if substituto else f"{texto}.")
    return alertas


def resumir(linhas: list[Linha], desconto_pct: Decimal = Decimal("0")) -> Resumo:
    """Totais por grupo, desconto (% do subtotal), custo e margem bruta, com os alertas de cada linha (D14)."""
    totais = {"intelbras": Decimal("0"), "material": Decimal("0"), "servico": Decimal("0")}
    custo_total = Decimal("0")
    for linha in linhas:
        totais[linha.tipo] += _centavos(linha.quantidade * linha.preco_unitario)
        custo_total += linha.quantidade * linha.custo_unitario

    subtotal = sum(totais.values(), Decimal("0"))
    desconto_valor = _centavos(subtotal * desconto_pct / CEM)
    total = subtotal - desconto_valor
    custo_total = _centavos(custo_total)
    margem_valor = total - custo_total
    margem_pct = _centavos(margem_valor / total * CEM) if total else Decimal("0")

    alertas_por_linha = [alertas_da_linha(linha) for linha in linhas]
    alertas = []
    if desconto_valor and total < custo_total:
        alertas.append("O desconto deixa o total abaixo do custo.")
    com_alerta = sum(1 for a in alertas_por_linha if a)
    if com_alerta:
        alertas.append(f"{com_alerta} item(ns) com alerta: veja na tabela.")

    return Resumo(
        total_intelbras=totais["intelbras"],
        total_materiais=totais["material"],
        total_servicos=totais["servico"],
        subtotal=subtotal,
        desconto_pct=desconto_pct,
        desconto_valor=desconto_valor,
        total=total,
        custo_total=custo_total,
        margem_valor=margem_valor,
        margem_pct=margem_pct,
        alertas_por_linha=alertas_por_linha,
        alertas=alertas,
    )


def parcelamento(total: Decimal, opcoes: list[dict]) -> list[dict]:
    """Parcelas do PDF (H10, D44). `opcoes`: [{"parcelas": 3, "acrescimo": 0.05 ou None}].

    Acréscimo em fração sobre o total; None = o gestor não informou, o prazo fica de fora.
    Devolve [{"parcelas", "acrescimo", "parcela", "total"}] em ordem de prazo.
    """
    linhas = []
    for opcao in sorted(opcoes, key=lambda o: o["parcelas"]):
        if opcao.get("acrescimo") is None or not total:
            continue
        acrescimo = Decimal(str(opcao["acrescimo"]))
        com_acrescimo = _centavos(total * (1 + acrescimo))
        linhas.append({"parcelas": opcao["parcelas"], "acrescimo": acrescimo,
                       "parcela": _centavos(com_acrescimo / opcao["parcelas"]), "total": com_acrescimo})
    return linhas
