"""Montagem da proposta v2 (D17–D29).

Junta o que está no banco (proposta, catálogo, cotações, tarifas, configurações) e chama as
funções puras de `services/calculo.py`. Não grava nada: `montar()` devolve tudo o que as telas
e o PDF mostram; `gravar_resultado()` guarda o kit e o resumo na proposta.

Campos vazios na proposta significam "usar a sugestão do sistema".
"""

import math
import re
from dataclasses import dataclass, field
from decimal import Decimal

from clientes.models import UnidadeConsumidora
from core.models import ConfigEmpresa
from core.validacoes import formatar_reais

from .models import Cotacao, Equipamento, FioBEscalonamento, ItemKit, TaxaFinanciamento
from .services import calculo


@dataclass
class Montagem:
    mensagem: str = ""                  # o que falta para chegar ao resultado
    alertas: list = field(default_factory=list)  # [{"tipo": "erro|aviso", "texto": ..., "interno": bool}]

    # Consumo
    tarifa_kwh: float | None = None     # com tributos
    consumo: float | None = None        # kWh/mês, média
    consumo_alvo: float | None = None   # com folga
    disponibilidade: int = 0
    iluminacao: float = 0.0             # iluminação pública (R$/mês)
    iluminacao_estimada: bool = False   # True quando veio da tabela do município (D32)

    # Sistema
    municipio: object = None
    cotacao_ref: Cotacao | None = None
    modulo: Equipamento | None = None
    modulo_sugerido: bool = True
    qtd_modulos: int = 0
    qtd_modulos_sugerida: int = 0
    inversor: Equipamento | None = None
    inversor_sugerido: bool = True
    qtd_inversores: int = 0
    cabo_preto: int = 0
    cabo_vermelho: int = 0
    kwp_necessario: float = 0.0
    kwp: float = 0.0
    kw_ca: float = 0.0
    sobrecarga: float | None = None
    sobrecarga_max: float = 0.0
    estrutura: str = ""
    geracao_media: float | None = None
    area: float | None = None

    # Preço (interno)
    custo_kit: float | None = None
    custo_kit_estimado: bool = False
    mo_sugerida: float | None = None
    mao_de_obra: float | None = None
    desconto: float = 0.0
    investimento: float | None = None
    rs_por_wp: float | None = None

    # Proposta
    resultado: calculo.ResultadoCalculo | None = None
    financiamento: list = field(default_factory=list)
    prazo: int | None = None
    parcela: dict | None = None
    conta_hoje: float | None = None
    conta_com_sistema: float | None = None
    conta_com_parcela: float | None = None
    barra_max: float = 0.0  # maior das contas, para o gráfico de barras

    def alerta(self, tipo, texto, interno=True):
        self.alertas.append({"tipo": tipo, "texto": texto, "interno": interno})

    @property
    def payback_texto(self):
        if not self.resultado or self.resultado.payback_meses <= 0:
            return ""
        anos, meses = divmod(round(self.resultado.payback_meses), 12)
        if not anos:
            return f"{meses} meses"
        return f"{anos} anos" + (f" e {meses} meses" if meses else "")


def fase_do_inversor(ligacao):
    """Mono e bifásica usam inversor 220 V; trifásica, 380 V (D19)."""
    return "tri" if ligacao == "tri" else "mono"


def municipio_da_proposta(proposta):
    if proposta.uc and proposta.uc.municipio_id:
        return proposta.uc.municipio
    return proposta.cliente.municipio if proposta.cliente_id else None


# Tabela de iluminação pública usada por tipo de tarifa (D32). B2 rural não tem estimativa.
CLASSE_ILUMINACAO = {"B1": "residencial", "B1_BAIXA_RENDA": "residencial", "B3": "nao_residencial"}


def tabela_iluminacao(proposta, municipio):
    """(faixas, valor da unidade fiscal) do município para a classe da proposta, ou None."""
    classe = CLASSE_ILUMINACAO.get(proposta.tipo_tarifa.tipo if proposta.tipo_tarifa else "")
    if not classe or not municipio or not municipio.valor_unidade_fiscal:
        return None
    faixas = [(f.ate_kwh, float(f.unidades)) for f in municipio.faixas_iluminacao.filter(classe=classe)]
    return (faixas, float(municipio.valor_unidade_fiscal)) if faixas else None


def premissas_da_proposta(proposta, config):
    """Rascunho usa as configurações de hoje; proposta emitida usa o snapshot gravado."""
    if proposta.status != proposta.Status.RASCUNHO and proposta.premissas:
        return dict(proposta.premissas)
    premissas = dict(config.premissas_padrao)
    perfil = next((p for p in config.perfis_simultaneidade if p["nome"] == proposta.perfil_simultaneidade), None)
    if perfil:
        premissas["simultaneidade"] = perfil["simultaneidade"]
    premissas["fator_orientacao"] = config.fatores_orientacao.get(proposta.orientacao or "norte", 1.0)
    return premissas


def referencia_do_distribuidor(distribuidor):
    for cotacao in Cotacao.referencias():
        if cotacao.distribuidor.lower() == distribuidor.lower():
            return cotacao
    return None


def sugerir_modulo():
    """Módulo da cotação de referência de menor R$/Wp; sem cotação, o módulo ativo de maior potência."""
    for cotacao in Cotacao.referencias():
        item = cotacao.itens.filter(equipamento__tipo="modulo", equipamento__ativo=True).first()
        if item:
            return item.equipamento
    return Equipamento.objects.filter(tipo="modulo", ativo=True, potencia_w__isnull=False).order_by("-potencia_w").first()


def inversores_candidatos(fase, distribuidor):
    """Inversores ativos da fase, do mesmo distribuidor do módulo; se não houver, de qualquer um."""
    todos = Equipamento.objects.filter(tipo="inversor", ativo=True, fase=fase, potencia_w__isnull=False)
    do_distribuidor = todos.filter(distribuidor__iexact=distribuidor) if distribuidor else todos.none()
    return list(do_distribuidor) or list(todos)


def _metros_de_cabo(cotacao, cor):
    if not cotacao:
        return 0
    for item in cotacao.itens.all():
        texto = item.descricao.lower()
        if "cabo" in texto and cor in texto and item.unidade == "m":
            return int(item.quantidade)
    return 0


def _consumo(proposta, m):
    """Consumo médio mensal (kWh) pela origem escolhida. Devolve (kwh_fatura, dias) para o motor."""
    origem = proposta.origem_consumo
    if origem == proposta.OrigemConsumo.FATURA:
        fatura = proposta.fatura  # pode ser uma fatura ainda não gravada (prévia do passo 2)
        if not fatura or not fatura.kwh or not fatura.dias_ciclo:
            m.mensagem = "Informe os dados da fatura (passo 2)."
            return None
        m.consumo = fatura.kwh / fatura.dias_ciclo * 30
        return fatura.kwh, fatura.dias_ciclo
    if origem == proposta.OrigemConsumo.KWH:
        if not proposta.kwh_informado:
            m.mensagem = "Informe o consumo em kWh (passo 2)."
            return None
        m.consumo = float(proposta.kwh_informado)
        return m.consumo, 30
    if origem == proposta.OrigemConsumo.CONTA:
        if not proposta.conta_informada:
            m.mensagem = "Informe o valor da conta (passo 2)."
            return None
        if m.tarifa_kwh is None:
            return None
        adicional = float(proposta.bandeira.adicional_kwh) if proposta.bandeira_id else 0.0
        tabela = tabela_iluminacao(proposta, m.municipio) if proposta.iluminacao_publica is None else None
        try:
            if tabela:
                m.consumo, m.iluminacao = calculo.kwh_pela_conta_com_tabela(
                    float(proposta.conta_informada), m.tarifa_kwh, adicional, *tabela
                )
                m.iluminacao_estimada = True
            else:
                m.iluminacao = float(proposta.iluminacao_publica or 0)
                m.consumo = calculo.kwh_pela_conta(float(proposta.conta_informada), m.iluminacao, m.tarifa_kwh, adicional)
        except ValueError as erro:
            m.mensagem = str(erro)
            return None
        return m.consumo, 30
    m.mensagem = "Escolha como informar o consumo (passo 2)."
    return None


def montar(proposta, config=None):
    config = config or ConfigEmpresa.obter()
    m = Montagem()
    premissas = premissas_da_proposta(proposta, config)

    # ---- Tarifa
    tarifa = proposta.tipo_tarifa
    falta_tarifa = ""
    if not tarifa:
        m.mensagem = "Escolha o tipo de tarifa (passo 1)."
        return m
    if not tarifa.aliquota_tributos or tarifa.fiob_kwh is None:
        falta_tarifa = (f"A tarifa {tarifa.get_tipo_display()} está sem tributos ou sem Fio B. "
                        "O gestor preenche em Configurações → Tarifas.")
    if tarifa.aliquota_tributos:
        m.tarifa_kwh = float(tarifa.tarifa_com_tributos)

    # ---- Consumo
    m.disponibilidade = UnidadeConsumidora.DISPONIBILIDADE_KWH.get(proposta.ligacao, 0)
    m.municipio = municipio_da_proposta(proposta)
    consumo_motor = _consumo(proposta, m)
    if consumo_motor is None:
        if not m.mensagem:
            m.mensagem = falta_tarifa
        return m
    if proposta.origem_consumo != proposta.OrigemConsumo.CONTA:
        tabela = tabela_iluminacao(proposta, m.municipio) if proposta.iluminacao_publica is None else None
        if tabela:
            m.iluminacao, m.iluminacao_estimada = calculo.iluminacao_pela_tabela(m.consumo, *tabela), True
        else:
            m.iluminacao = float(proposta.iluminacao_publica or 0)
    folga = float(proposta.folga or 0)
    m.consumo_alvo = m.consumo * (1 + folga)

    # ---- Dimensionamento
    if not m.municipio or not m.municipio.irradiacao:
        m.mensagem = "O município do cliente está sem irradiação. Atualize em Configurações → Municípios."
        return m
    irradiacao = m.municipio.irradiacao
    fator = premissas["fator_orientacao"] if "fator_orientacao" in premissas else 1.0
    perdas, clipping = premissas["perdas"], premissas["perda_clipping"]
    m.kwp_necessario = calculo.kwp_necessario(
        m.consumo, folga, m.disponibilidade, irradiacao, perdas, clipping, fator,
    )

    m.modulo = proposta.modulo or sugerir_modulo()
    m.modulo_sugerido = proposta.modulo_id is None
    if not m.modulo:
        m.mensagem = "Nenhum módulo no catálogo. Cadastre em Catálogo solar."
        return m
    m.cotacao_ref = referencia_do_distribuidor(m.modulo.distribuidor)
    m.qtd_modulos_sugerida = calculo.quantidade_modulos(m.kwp_necessario, m.modulo.potencia_w)
    m.qtd_modulos = proposta.qtd_modulos or m.qtd_modulos_sugerida
    m.kwp = m.qtd_modulos * m.modulo.potencia_w / 1000

    sobrecarga_max = m.sobrecarga_max = premissas["razao_cc_ca_max"]
    m.estrutura = dict(Equipamento.TipoEstrutura.choices).get(proposta.tipo_estrutura, "")
    fase = fase_do_inversor(proposta.ligacao)
    m.inversor_sugerido = proposta.inversor_id is None
    if proposta.inversor_id:
        m.inversor = proposta.inversor
        m.qtd_inversores = proposta.qtd_inversores or max(
            1, math.ceil(m.kwp / (m.inversor.potencia_w / 1000 * sobrecarga_max)))
    else:
        candidatos = inversores_candidatos(fase, m.modulo.distribuidor)
        escolhido, m.qtd_inversores = calculo.sugerir_inversor(
            m.kwp, [{"kw": e.potencia_w / 1000, "fase": e.fase, "equipamento": e} for e in candidatos],
            fase, sobrecarga_max,
        )
        m.inversor = escolhido["equipamento"] if escolhido else None
        if proposta.qtd_inversores and m.inversor:
            m.qtd_inversores = proposta.qtd_inversores
    if not m.inversor:
        m.mensagem = "Nenhum inversor da fase da ligação no catálogo. Cadastre em Catálogo solar."
        return m
    m.kw_ca = m.inversor.potencia_w / 1000 * m.qtd_inversores
    m.sobrecarga = m.kwp / m.kw_ca

    referencia_cabos = proposta.cotacao or m.cotacao_ref
    m.cabo_preto = proposta.cabo_preto_m if proposta.cabo_preto_m is not None else _metros_de_cabo(referencia_cabos, "preto")
    m.cabo_vermelho = (proposta.cabo_vermelho_m if proposta.cabo_vermelho_m is not None
                       else _metros_de_cabo(referencia_cabos, "vermelho"))

    gera_por_kwp_mes = sum(
        irr * dias * (1 - perdas) * (1 - clipping) * fator
        for irr, dias in zip(irradiacao, calculo.DIAS_MES_ANO_COMUM)
    ) / 12
    m.geracao_media = m.kwp * gera_por_kwp_mes
    if m.modulo.area_m2:
        m.area = m.qtd_modulos * float(m.modulo.area_m2)

    if m.sobrecarga > sobrecarga_max:
        m.alerta("erro", f"Sobrecarga de {m.sobrecarga:.2f} acima de {sobrecarga_max:.2f}. Escolha um inversor maior.")
    elif m.sobrecarga < 0.8:
        m.alerta("aviso", f"Sobrecarga de {m.sobrecarga:.2f}: inversor grande para o sistema. Há modelo menor?")
    if m.inversor.fase and m.inversor.fase != fase:
        m.alerta("erro", f"Ligação {proposta.get_ligacao_display().lower()} com inversor {m.inversor.get_fase_display().lower()}.")

    # ---- Preço
    if proposta.custo_kit is not None:
        m.custo_kit = float(proposta.custo_kit)
    elif proposta.cotacao_id:
        m.custo_kit = float(proposta.cotacao.total)
    elif m.cotacao_ref:
        m.custo_kit = m.kwp * 1000 * float(m.cotacao_ref.rs_por_wp)
        m.custo_kit_estimado = True
        m.alerta("aviso", f"Custo do kit estimado pela cotação {m.cotacao_ref.distribuidor} de "
                          f"{m.cotacao_ref.data:%d/%m/%Y}. Cote o kit e informe o valor real.")
    else:
        m.mensagem = f"Sem cotação de referência da {m.modulo.distribuidor}. Informe o custo do kit."
    referencia_preco = proposta.cotacao or m.cotacao_ref
    if referencia_preco and referencia_preco.idade_dias > config.dias_preco_velho:
        m.alerta("aviso", f"Preço do kit com {referencia_preco.idade_dias} dias. Peça cotação nova.")

    solo = proposta.tipo_estrutura == "solo"
    m.mo_sugerida = calculo.mao_de_obra_sugerida(
        m.kwp, solo, float(config.mo_por_kwp), float(config.mo_por_kwp_solo), float(config.mo_minima),
    )
    m.mao_de_obra = float(proposta.mao_de_obra) if proposta.mao_de_obra is not None else m.mo_sugerida
    if proposta.desconto_pct is not None:
        m.desconto = m.mao_de_obra * float(proposta.desconto_pct)
    else:
        m.desconto = float(proposta.desconto or 0)
    if m.desconto > m.mao_de_obra:
        m.alerta("erro", "O desconto é maior que a mão de obra. O desconto vale só na mão de obra.")
        m.desconto = m.mao_de_obra
    if m.mao_de_obra - m.desconto < float(config.mo_minima):
        m.alerta("aviso", f"Mão de obra com desconto abaixo do mínimo de R$ {formatar_reais(config.mo_minima)}.")
    if m.custo_kit is None:
        return m
    m.investimento = m.custo_kit + m.mao_de_obra - m.desconto
    m.rs_por_wp = m.investimento / (m.kwp * 1000)

    if proposta.nivel == proposta.Nivel.ESTIMATIVA:
        m.alerta("aviso", "Proposta de estimativa: vai com o aviso de dados não confirmados.", interno=False)

    # ---- Resultado financeiro
    if falta_tarifa:
        m.mensagem = falta_tarifa
        m.alerta("erro", falta_tarifa)
        return m
    kwh_fatura, dias = consumo_motor
    digitos = re.sub(r"\D", "", proposta.cliente.cpf_cnpj or "")
    entrada = calculo.EntradaCalculo(
        kwp=m.kwp, kw_ca=m.kw_ca, irradiacao=irradiacao, kwh_fatura=float(kwh_fatura), dias_ciclo=dias,
        tarifa=m.tarifa_kwh, fiob_kwh=float(tarifa.fiob_kwh), disponibilidade_kwh=m.disponibilidade,
        investimento=m.investimento,
        fiob_pct_por_ano={f.ano: float(f.percentual) / 100 for f in FioBEscalonamento.objects.all()},
        premissas=premissas, classe=tarifa.tipo[:2], cliente_pessoa_juridica=len(digitos) > 11,
        fator_orientacao=fator,
    )
    try:
        m.resultado = calculo.calcular(entrada)
    except ZeroDivisionError:
        m.mensagem = "Com estes dados o sistema não gera economia. Confira consumo e quantidade de módulos."
        return m
    for texto in m.resultado.alertas:
        if not texto.startswith("Razão CC/CA"):  # a sobrecarga já tem alerta próprio
            m.alerta("aviso", texto)

    if proposta.origem_consumo == proposta.OrigemConsumo.CONTA:
        m.conta_hoje = float(proposta.conta_informada)  # o valor que o cliente paga, com bandeira e iluminação
    else:
        m.conta_hoje = m.consumo * m.tarifa_kwh + m.iluminacao
    m.conta_com_sistema = max(m.conta_hoje - m.resultado.economia_mensal_ano1, 0)

    taxas = [(t.banco, t.prazo_meses, float(t.taxa_mensal)) for t in TaxaFinanciamento.objects.all()]
    m.financiamento = [
        linha | {"taxa_pct": linha["taxa"] * 100} for linha in calculo.tabela_financiamento(m.investimento, taxas)
    ]
    prazos = [linha["prazo"] for linha in m.financiamento]
    if prazos:
        m.prazo = proposta.prazo_comparacao if proposta.prazo_comparacao in prazos else prazos[-1]
        m.parcela = next(linha for linha in m.financiamento if linha["prazo"] == m.prazo)
        m.conta_com_parcela = m.conta_com_sistema + m.parcela["parcela"]
    m.barra_max = max(m.conta_hoje, m.conta_com_parcela or 0)
    return m


def gravar_resultado(proposta, m):
    """Guarda o kit montado, o investimento e o resumo na proposta (rascunho)."""
    config = ConfigEmpresa.obter()
    proposta.premissas = premissas_da_proposta(proposta, config)
    proposta.investimento = Decimal(f"{m.investimento:.2f}") if m.investimento is not None else None
    proposta.resultados = {}
    if m.resultado:
        proposta.resultados = {
            "geracao_anual": m.resultado.geracao_anual,
            "consumo_anual": m.resultado.consumo_anual,
            "cobertura": m.resultado.cobertura,
            "economia_mensal_ano1": m.resultado.economia_mensal_ano1,
            "payback_meses": m.resultado.payback_meses,
            "rs_por_wp": m.resultado.rs_por_wp,
            "alertas": [a["texto"] for a in m.alertas],
        }
    proposta.save()

    proposta.itens_kit.all().delete()
    if not (m.modulo and m.inversor):
        return
    itens = [
        (ItemKit.Tipo.MODULO, m.modulo, m.modulo.descricao, m.qtd_modulos, m.modulo.potencia_w),
        (ItemKit.Tipo.INVERSOR, m.inversor, m.inversor.descricao, m.qtd_inversores, m.inversor.potencia_w),
    ]
    if m.estrutura:
        itens.append((ItemKit.Tipo.ESTRUTURA, None, f"Estrutura para {m.estrutura.lower()}", 1, None))
    if m.cabo_preto:
        itens.append((ItemKit.Tipo.CABEAMENTO, None, "Cabo solar 4 mm preto (m)", m.cabo_preto, None))
    if m.cabo_vermelho:
        itens.append((ItemKit.Tipo.CABEAMENTO, None, "Cabo solar 4 mm vermelho (m)", m.cabo_vermelho, None))
    for ordem, (tipo, equipamento, descricao, quantidade, potencia) in enumerate(itens):
        ItemKit.objects.create(
            proposta=proposta, tipo=tipo, equipamento=equipamento, descricao=descricao,
            modelo=equipamento.codigo if equipamento else "", quantidade=quantidade, potencia_w=potencia, ordem=ordem,
        )
