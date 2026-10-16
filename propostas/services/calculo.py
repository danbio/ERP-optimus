"""Motor de cálculo da Proposta Solar.

Funções puras, sem import de Django. Fórmulas documentadas em
docs/caso-referencia.md — qualquer mudança de número aqui é bug até
prova em contrário (ver tests/test_caso_referencia.py).
"""

import calendar
from dataclasses import dataclass, field


@dataclass
class EntradaCalculo:
    kwp: float
    kw_ca: float
    irradiacao: list[float]  # 12 valores, kWh/m²·dia
    kwh_fatura: float
    dias_ciclo: int
    tarifa: float
    fiob_kwh: float  # já resolvido (informado ou fallback)
    disponibilidade_kwh: int  # 30/50/100
    investimento: float
    fiob_pct_por_ano: dict[int, float]
    premissas: dict

    # Flags de contexto para os alertas de negócio (opcionais: a UC/Cliente
    # só existem a partir da fatia 3 — até lá o motor roda sem eles).
    classe: str = ""
    cliente_pessoa_juridica: bool = False
    fiob_informado: bool = True


@dataclass
class ResultadoCalculo:
    geracao_mensal: list[float]
    consumo_mensal: list[float]
    geracao_anual: float
    consumo_anual: float
    cobertura: float
    produtividade: float  # kWh/kWp·mês
    custo_mensal_atual: float
    custo_mensal_com_sistema: float
    economia_mensal_ano1: float
    payback_meses: float
    rs_por_wp: float
    fluxo: list[dict]  # [{"ano": 1, "economia": ..., "acumulado": ...}, ...]
    alertas: list[str] = field(default_factory=list)


def fiob_fallback(valor_distribuicao: float, kwh: float, valor_total: float, impostos: float) -> float:
    """Estimativa conservadora da TUSD Fio B (R$/kWh, com tributos) a partir da fatura."""
    return valor_distribuicao / kwh * valor_total / (valor_total - impostos)


def _dias_do_mes(ano: int, mes: int) -> int:
    return calendar.monthrange(ano, mes)[1]


def _percentual_fiob(ano_civil: int, tabela: dict[int, float]) -> float:
    if ano_civil in tabela:
        return tabela[ano_civil]
    ultimo_ano = max(tabela)
    if ano_civil > ultimo_ano:
        return tabela[ultimo_ano]
    primeiro_ano = min(tabela)
    if ano_civil < primeiro_ano:
        return 0.0
    return tabela[ultimo_ano]


def calcular(e: EntradaCalculo) -> ResultadoCalculo:
    premissas = e.premissas
    perdas = premissas["perdas"]
    perda_clipping = premissas["perda_clipping"]
    ano_conexao = premissas["ano_conexao"]
    simultaneidade = premissas["simultaneidade"]
    reajuste_anual = premissas["reajuste_anual"]
    degradacao_ano1 = premissas["degradacao_ano1"]
    degradacao_anual = premissas["degradacao_anual"]
    cobrar_disponibilidade = premissas["cobrar_disponibilidade"]
    horizonte_anos = premissas["horizonte_anos"]
    razao_cc_ca_max = premissas["razao_cc_ca_max"]

    dias_mes = [_dias_do_mes(ano_conexao, mes) for mes in range(1, 13)]

    geracao_mensal = [
        e.kwp * irr * dias * (1 - perdas) * (1 - perda_clipping)
        for irr, dias in zip(e.irradiacao, dias_mes)
    ]
    consumo_mensal = [e.kwh_fatura / e.dias_ciclo * dias for dias in dias_mes]

    geracao_anual = sum(geracao_mensal)
    consumo_anual = sum(consumo_mensal)
    cobertura = geracao_anual / consumo_anual
    produtividade = (geracao_anual / 12) / e.kwp

    disponibilidade_anual = e.disponibilidade_kwh * 12 if cobrar_disponibilidade else 0.0

    fluxo = []
    acumulado = -e.investimento
    for ano_idx in range(horizonte_anos):
        ano_civil = ano_conexao + ano_idx
        tarifa_y = e.tarifa * (1 + reajuste_anual) ** ano_idx
        fiob_y = e.fiob_kwh * (1 + reajuste_anual) ** ano_idx
        geracao_y = geracao_anual * (1 - degradacao_ano1) * (1 - degradacao_anual) ** ano_idx
        compensado = min(geracao_y, consumo_anual)
        pct_fiob = _percentual_fiob(ano_civil, e.fiob_pct_por_ano)

        economia_y = (
            compensado * tarifa_y
            - disponibilidade_anual * tarifa_y
            - pct_fiob * fiob_y * compensado * (1 - simultaneidade)
        )
        acumulado += economia_y
        fluxo.append({"ano": ano_idx + 1, "economia": economia_y, "acumulado": acumulado})

    economia_mensal_ano1 = fluxo[0]["economia"] / 12
    custo_mensal_atual = consumo_anual * e.tarifa / 12
    custo_mensal_com_sistema = custo_mensal_atual - economia_mensal_ano1
    payback_meses = e.investimento / economia_mensal_ano1
    rs_por_wp = e.investimento / (e.kwp * 1000)

    alertas = []
    razao_cc_ca = e.kwp / e.kw_ca
    if razao_cc_ca > razao_cc_ca_max:
        alertas.append(
            f"Razão CC/CA de {razao_cc_ca:.2f} acima do limite de {razao_cc_ca_max:.2f}."
        )
    if e.classe == "B1" and e.cliente_pessoa_juridica:
        alertas.append("Classe B1 residencial em cliente comercial (CNPJ).")
    if not e.fiob_informado:
        alertas.append("Fio B estimado pela fatura (TUSD Fio B não informada).")
    if cobertura > 1.30:
        alertas.append(f"Cobertura de {cobertura * 100:.1f}% acima de 130% (possível superdimensionamento).")
    elif cobertura < 0.80:
        alertas.append(f"Cobertura de {cobertura * 100:.1f}% abaixo de 80%.")

    return ResultadoCalculo(
        geracao_mensal=geracao_mensal,
        consumo_mensal=consumo_mensal,
        geracao_anual=geracao_anual,
        consumo_anual=consumo_anual,
        cobertura=cobertura,
        produtividade=produtividade,
        custo_mensal_atual=custo_mensal_atual,
        custo_mensal_com_sistema=custo_mensal_com_sistema,
        economia_mensal_ano1=economia_mensal_ano1,
        payback_meses=payback_meses,
        rs_por_wp=rs_por_wp,
        fluxo=fluxo,
        alertas=alertas,
    )
