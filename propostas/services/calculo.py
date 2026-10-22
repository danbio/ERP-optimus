"""Motor de cálculo da Proposta Solar.

Funções puras, sem import de Django. Fórmulas documentadas em
docs/caso-referencia.md — qualquer mudança de número aqui é bug até
prova em contrário (ver tests/test_caso_referencia.py).
"""

import calendar
import math
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
    fator_orientacao: float = 1.0  # norte = 1,0 (D19); vem de ConfigEmpresa.fatores_orientacao


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
    # Limites do aviso de cobertura (A25). Propostas emitidas antes da rodada 3 não têm as chaves no snapshot.
    cobertura_min = premissas.get("cobertura_min", 0.80)
    cobertura_max = premissas.get("cobertura_max", 1.30)

    dias_mes = [_dias_do_mes(ano_conexao, mes) for mes in range(1, 13)]

    geracao_mensal = [
        e.kwp * irr * dias * (1 - perdas) * (1 - perda_clipping) * e.fator_orientacao
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
    # Sem economia não há retorno: 0 indica "não se paga" (a emissão é bloqueada, A02).
    payback_meses = e.investimento / economia_mensal_ano1 if economia_mensal_ano1 > 0 else 0.0
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
    if cobertura > cobertura_max:
        alertas.append(f"Cobertura de {cobertura * 100:.1f}% acima de {cobertura_max * 100:.0f}% "
                       "(possível superdimensionamento).")
    elif cobertura < cobertura_min:
        alertas.append(f"Cobertura de {cobertura * 100:.1f}% abaixo de {cobertura_min * 100:.0f}%.")

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


# ---------- Proposta v2: consumo, dimensionamento, preço e financiamento (spec v2, seção 4) ----------

DIAS_MES_ANO_COMUM = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def kwh_pela_conta(conta: float, iluminacao_publica: float, tarifa: float, adicional_bandeira: float) -> float:
    """Consumo mensal a partir do valor da conta (D19).

    `tarifa` é a tarifa final com tributos (R$/kWh); a iluminação pública não é energia.
    """
    if conta <= iluminacao_publica:
        raise ValueError("O valor da conta precisa ser maior que a iluminação pública.")
    return (conta - iluminacao_publica) / (tarifa + adicional_bandeira)


def iluminacao_pela_tabela(kwh: float, faixas: list, valor_unidade: float) -> float:
    """Iluminação pública (R$) pela tabela do município (D32).

    `faixas`: [(até quantos kWh ou None, unidades fiscais)], em ordem crescente.
    """
    consumo = round(kwh)
    for ate, unidades in faixas:
        if ate is None or consumo <= ate:
            return unidades * valor_unidade
    return 0.0


def kwh_pela_conta_com_tabela(conta: float, tarifa: float, adicional_bandeira: float,
                              faixas: list, valor_unidade: float) -> tuple[float, float]:
    """Consumo e iluminação pública a partir só do valor da conta (D32). Devolve (kWh, iluminação).

    A iluminação depende do consumo, que depende da conta menos a iluminação: testa faixa a faixa,
    de baixo para cima, e fica com a primeira em que o consumo calculado não passa do limite dela.
    Na virada de uma faixa o consumo pode sair um pouco abaixo do início dela; fica assim mesmo.
    """
    for ate, unidades in faixas:
        iluminacao = unidades * valor_unidade
        if conta <= iluminacao:
            break
        kwh = (conta - iluminacao) / (tarifa + adicional_bandeira)
        if ate is None or round(kwh) <= ate:
            return kwh, iluminacao
    raise ValueError("O valor da conta precisa ser maior que a iluminação pública.")


def geracao_necessaria(consumo_kwh: float, folga: float) -> float:
    """kWh/mês que o sistema precisa gerar: o consumo com a folga. A disponibilidade não entra (D33)."""
    return max(consumo_kwh * (1 + folga), 0.0)


def geracao_por_kwp_mes(irradiacao: list[float], perdas: float, clipping: float, fator_orientacao: float) -> float:
    """kWh/mês que 1 kWp gera, em média no ano (A25).

    Usa os 12 meses da irradiação com os dias de cada mês, a mesma conta de `calcular()`.
    """
    return sum(
        irr * dias * (1 - perdas) * (1 - clipping) * fator_orientacao
        for irr, dias in zip(irradiacao, DIAS_MES_ANO_COMUM)
    ) / 12


def kwp_necessario(consumo_kwh: float, folga: float, irradiacao: list[float],
                   perdas: float, clipping: float, fator_orientacao: float) -> float:
    """Potência (kWp) que gera, em média, a geração necessária (o sistema sugerido gera o que a proposta mostra)."""
    return geracao_necessaria(consumo_kwh, folga) / geracao_por_kwp_mes(irradiacao, perdas, clipping, fator_orientacao)


def quantidade_modulos(kwp: float, potencia_w: float) -> int:
    """Módulos para chegar ao kWp (arredonda para cima). Mínimo 1."""
    return max(math.ceil(round(kwp * 1000 / potencia_w, 6)), 1)


def escolher_modulo(modulos: list[dict]) -> dict | None:
    """O módulo de menor R$/Wp (D34). `modulos`: dicts com "w" e "preco". Empate: o de maior potência.

    Sem nenhum com preço: o de maior potência.
    """
    com_preco = [m for m in modulos if m.get("preco") and m.get("w")]
    if com_preco:
        return min(com_preco, key=lambda m: (round(m["preco"] / m["w"], 6), -m["w"]))
    com_potencia = [m for m in modulos if m.get("w")]
    return max(com_potencia, key=lambda m: m["w"]) if com_potencia else None


def sugerir_inversor(kwp: float, inversores: list[dict], fase: str,
                     sobrecarga_max: float = 1.5, sobrecarga_min: float = 0.0) -> tuple[dict | None, int]:
    """(inversor string, quantidade) para o kWp, só entre os da fase da ligação (D19, D34).

    `inversores`: dicts com "kw" (potência CA), "fase" ("mono" ou "tri") e, se houver, "preco".
    `fase` é a ligação do cliente: "mono" e "bi" usam inversor 220 V ("mono"); "tri", 380 V.
    Escolhe o mais barato com sobrecarga (kWp / kW) entre a mínima e a máxima. Sem preço nessa
    faixa, o menor com sobrecarga ≤ máxima. Se nenhum couber sozinho, o maior em quantas
    unidades forem precisas. Sem inversor da fase: (None, 0).
    """
    fase = "mono" if fase == "bi" else fase
    da_fase = sorted((i for i in inversores if i["fase"] == fase), key=lambda i: i["kw"])
    if not da_fase:
        return None, 0
    na_faixa = [i for i in da_fase if sobrecarga_min <= kwp / i["kw"] <= sobrecarga_max and i.get("preco")]
    if na_faixa:
        return min(na_faixa, key=lambda i: (i["preco"], i["kw"])), 1
    for inversor in da_fase:
        if kwp / inversor["kw"] <= sobrecarga_max:
            return inversor, 1
    maior = da_fase[-1]
    return maior, math.ceil(kwp / (maior["kw"] * sobrecarga_max))


def quantidade_micros(qtd_modulos: int, modulos_por_micro: int) -> int:
    """Microinversores para ligar todos os módulos (arredonda para cima)."""
    return math.ceil(qtd_modulos / max(modulos_por_micro, 1))


def sugerir_micro(qtd_modulos: int, potencia_modulo_w: float, micros: list[dict],
                  sobrecarga_max: float = 1.5) -> tuple[dict | None, int]:
    """(microinversor, quantidade) de menor custo total (D34).

    `micros`: dicts com "w" (potência CA), "modulos" (módulos por micro) e, se houver, "preco".
    Só entram os que aguentam os módulos ligados nele: modulos × W do módulo / W do micro ≤ sobrecarga_max.
    Sem preço, o de mais módulos por micro.
    """
    cabem = [mi for mi in micros if mi.get("w") and mi.get("modulos")
             and mi["modulos"] * potencia_modulo_w / mi["w"] <= sobrecarga_max]
    if not cabem:
        return None, 0
    com_preco = [mi for mi in cabem if mi.get("preco")]
    if com_preco:
        escolhido = min(com_preco, key=lambda mi: (quantidade_micros(qtd_modulos, mi["modulos"]) * mi["preco"], -mi["w"]))
    else:
        escolhido = max(cabem, key=lambda mi: (mi["modulos"], mi["w"]))
    return escolhido, quantidade_micros(qtd_modulos, escolhido["modulos"])


def strings_do_inversor(qtd_modulos: int, mppts: int, minimo: int, maximo: int) -> int:
    """Strings do sistema com inversor string (D34): 1 por MPPT, de `minimo` a `maximo` módulos cada.

    Usa todos os MPPT (`mppts` = MPPT de todos os inversores) se cada string tiver pelo menos o mínimo;
    passa do número de MPPT só quando os módulos não cabem no máximo por string.
    """
    precisa = math.ceil(qtd_modulos / maximo)
    cabe = min(mppts, qtd_modulos // minimo) if minimo else mppts
    return max(precisa, cabe, 1)


def dividir_em_fileiras(qtd_modulos: int, partes: int) -> list[int]:
    """Divide os módulos em `partes` fileiras quase iguais, as maiores primeiro: 11 em 2 → [6, 5]."""
    partes = max(min(partes, qtd_modulos), 1)
    base, sobra = divmod(qtd_modulos, partes)
    return [base + 1] * sobra + [base] * (partes - sobra)


def _embalagens(pecas: int, por_embalagem: int) -> int:
    return math.ceil(pecas / max(por_embalagem, 1))


# Estruturas com trilho longo apoiado no telhado; telha metálica usa mini trilho; solo leva só os grampos.
ESTRUTURAS_COM_TRILHO = ("ceramica", "fibrocimento", "laje")


def quantidades_estrutura(fileiras: list[int], estrutura: str, pecas_por_embalagem: dict) -> dict:
    """Embalagens de cada item da estrutura (D34), por papel no kit: {"trilho": 10, "grampo_final": 2, ...}.

    `fileiras`: módulos em cada fileira. `pecas_por_embalagem`: peças vendidas juntas, por papel.
    Por fileira de N módulos: 4 grampos finais, 2 grampos intermediários por emenda entre módulos
    (2 × (N − 1)), 1 aterramento. Com trilho: 1 trilho por módulo e 2 × (N + 1) apoios de fixação.
    Telha metálica: 2 × (N + 1) mini trilhos, sem trilho longo.
    """
    def emb(papel, pecas):
        return _embalagens(pecas, pecas_por_embalagem.get(papel, 1))

    apoios = sum(2 * (n + 1) for n in fileiras)
    quantidades = {
        "grampo_final": emb("grampo_final", 4 * len(fileiras)),
        "grampo_intermediario": emb("grampo_intermediario", sum(2 * (n - 1) for n in fileiras)),
        "aterramento": len(fileiras),
    }
    if estrutura in ESTRUTURAS_COM_TRILHO:
        quantidades["trilho"] = sum(fileiras)
        quantidades["fixacao"] = emb("fixacao", apoios)
    elif estrutura == "metalica":
        quantidades["mini_trilho"] = emb("mini_trilho", apoios)
    return {papel: qtd for papel, qtd in quantidades.items() if qtd > 0}


def quantidades_eletricas(strings: int, metros_por_string: float, pares_por_string: int,
                          pares_por_embalagem: int) -> dict:
    """Cabo solar (m de cada cor) e conectores (embalagens) para as strings (D34).

    Com microinversor, cada micro conta como uma string para os conectores e não leva cabo solar.
    """
    quantidades = {"conector": _embalagens(strings * pares_por_string, pares_por_embalagem)}
    metros = math.ceil(strings * metros_por_string)
    if metros:
        quantidades |= {"cabo_vermelho": metros, "cabo_preto": metros}
    return {papel: qtd for papel, qtd in quantidades.items() if qtd > 0}


def custo_do_kit(itens: list[tuple[int, float]], frete: float) -> float:
    """Soma de quantidade × preço dos itens, mais o frete (fração sobre os produtos, D34)."""
    return sum(qtd * preco for qtd, preco in itens) * (1 + frete)


def mao_de_obra_sugerida(kwp: float, solo: bool, por_kwp: float, por_kwp_solo: float, minima: float) -> float:
    """max(kWp × valor por kWp, mínimo); em solo o valor por kWp é outro (D18)."""
    return max(kwp * (por_kwp_solo if solo else por_kwp), minima)


def parcela_price(valor: float, taxa_mensal: float, meses: int) -> float:
    """Parcela fixa (tabela Price)."""
    if taxa_mensal == 0:
        return valor / meses
    return valor * taxa_mensal / (1 - (1 + taxa_mensal) ** -meses)


def tabela_financiamento(valor: float, taxas: list[tuple[str, int, float]]) -> list[dict]:
    """Para cada prazo, a menor parcela entre os bancos (D22).

    `taxas`: (banco, prazo em meses, taxa mensal). Devolve [{"prazo", "banco", "taxa", "parcela"}]
    em ordem de prazo, só os prazos que têm taxa.
    """
    melhores = {}
    for banco, prazo, taxa in taxas:
        parcela = parcela_price(valor, taxa, prazo)
        if prazo not in melhores or parcela < melhores[prazo]["parcela"]:
            melhores[prazo] = {"prazo": prazo, "banco": banco, "taxa": taxa, "parcela": parcela}
    return [melhores[prazo] for prazo in sorted(melhores)]
