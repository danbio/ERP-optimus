"""Montagem da proposta v2 (D17–D29).

Junta o que está no banco (proposta, catálogo, cotações, tarifas, configurações) e chama as
funções puras de `services/calculo.py`. Não grava nada: `montar()` devolve tudo o que as telas
e o PDF mostram; `gravar_resultado()` guarda o kit e o resumo na proposta.

Campos vazios na proposta significam "usar a sugestão do sistema".
"""

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from clientes.models import UnidadeConsumidora
from core.models import ConfigEmpresa
from core.validacoes import formatar_reais

from .models import Equipamento, FioBEscalonamento, ItemKit, TaxaFinanciamento
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
    modulo: Equipamento | None = None
    modulo_sugerido: bool = True
    qtd_modulos: int = 0
    qtd_modulos_sugerida: int = 0
    inversor: Equipamento | None = None
    inversor_sugerido: bool = True
    qtd_inversores: int = 0
    micro: bool = False                 # chave String × Microinversor (D34)
    strings: int = 0                    # com microinversor: um por micro
    fileiras: list = field(default_factory=list)  # módulos em cada fileira
    fileiras_sugeridas: bool = True
    kit: list = field(default_factory=list)       # [LinhaKit], na ordem do PDF
    kit_da_cotacao: bool = False        # cotação vinculada substitui o catálogo (D35)
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
    produtos_kit: float | None = None   # soma dos itens do catálogo, sem frete
    frete_kit: float = 0.0
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

    @property
    def fileiras_texto(self):
        """Módulos por fileira no formato "6+5"."""
        return "+".join(str(n) for n in self.fileiras)

    def alerta(self, tipo, texto, interno=True):
        """Acrescenta um alerta (`tipo` aviso ou erro); `interno` some no modo cliente."""
        self.alertas.append({"tipo": tipo, "texto": texto, "interno": interno})

    @property
    def payback_texto(self):
        """Retorno do investimento por extenso ("4 anos e 3 meses"), ou vazio se não se paga."""
        if not self.resultado or self.resultado.payback_meses <= 0:
            return ""
        anos, meses = divmod(round(self.resultado.payback_meses), 12)
        texto_anos = f"{anos} ano" if anos == 1 else f"{anos} anos"
        texto_meses = f"{meses} mês" if meses == 1 else f"{meses} meses"
        if not anos:
            return texto_meses
        return texto_anos + (f" e {texto_meses}" if meses else "")


@dataclass
class LinhaKit:
    """Um item do kit (D34): do catálogo, da cotação ou acrescentado pelo vendedor."""

    funcao: str                          # "modulo", "inversor", "trilho"... ou "extra"
    equipamento: Equipamento | None
    descricao: str
    quantidade: int
    unidade: str = "un"
    sugerida: int | None = None          # quantidade que o sistema sugere
    alterada: bool = False               # o vendedor trocou o item ou a quantidade

    @property
    def preco(self):
        """Preço de referência unitário do equipamento (R$), ou None sem preço."""
        if self.equipamento and self.equipamento.preco_referencia is not None:
            return float(self.equipamento.preco_referencia)
        return None

    @property
    def subtotal(self):
        """Quantidade × preço (R$), ou None sem preço."""
        return self.quantidade * self.preco if self.preco is not None else None

    @property
    def rotulo(self):
        """Nome do papel do item no kit, para a tela."""
        return Equipamento.Funcao(self.funcao).label if self.funcao in Equipamento.Funcao.values else ""


def fase_do_inversor(ligacao):
    """Mono e bifásica usam inversor 220 V; trifásica, 380 V (D19)."""
    return "tri" if ligacao == "tri" else "mono"


def municipio_da_proposta(proposta):
    """Local da instalação: o da proposta (passo 1); nas antigas, o da UC ou o do cliente."""
    if proposta.municipio_id:
        return proposta.municipio
    if proposta.uc and proposta.uc.municipio_id:
        return proposta.uc.municipio
    return proposta.cliente.municipio if proposta.cliente_id else None


def _num(valor, casas=2):
    """1.5 → "1,50": números nos alertas com vírgula, como o vendedor lê."""
    return f"{valor:.{casas}f}".replace(".", ",")


def impedimentos_de_emissao(m, proposta=None):
    """O que impede emitir a proposta (A02). Lista vazia = pode emitir.

    Com `proposta`, confere também o CPF/CNPJ da proposta confirmada (D38).
    """
    if not m.resultado:
        return [m.mensagem or "Complete os passos da proposta antes de emitir."]
    motivos = [a["texto"] for a in m.alertas if a["tipo"] == "erro"]
    if proposta is not None and proposta.nivel == proposta.Nivel.CONFIRMADA and not proposta.cliente.cpf_cnpj:
        motivos.append("Falta o CPF ou CNPJ do titular da fatura. A fatura não traz o número completo: "
                       "peça ao cliente e preencha no passo 2.")
    if m.resultado.economia_mensal_ano1 <= 0:
        motivos.append("Com estes dados o sistema não gera economia. Confira o consumo e a quantidade de módulos.")
    if not m.mao_de_obra or m.mao_de_obra - m.desconto <= 0:
        motivos.append("A mão de obra está zerada. Informe o valor da instalação.")
    return motivos


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
    # Ano em que o sistema deve ser conectado: vale para a regra do Fio B (A17).
    conexao = timezone.localdate() + timedelta(days=config.prazo_homologacao_dias)
    premissas["ano_conexao"] = conexao.year
    return premissas


def sugerir_modulo(distribuidor):
    """Módulo ativo do distribuidor do kit com menor R$/Wp (D34)."""
    modulos = Equipamento.objects.filter(
        tipo="modulo", ativo=True, potencia_w__isnull=False, distribuidor__iexact=distribuidor)
    escolhido = calculo.escolher_modulo(
        [{"w": e.potencia_w, "preco": float(e.preco_referencia) if e.preco_referencia else None, "equipamento": e}
         for e in modulos])
    return escolhido["equipamento"] if escolhido else None


def inversores_candidatos(fase, distribuidor, tipo="inversor"):
    """Inversores (ou microinversores) ativos do distribuidor do kit. String: só os da fase da ligação."""
    todos = Equipamento.objects.filter(tipo=tipo, ativo=True, potencia_w__isnull=False,
                                       distribuidor__iexact=distribuidor)
    return list(todos.filter(fase=fase) if tipo == "inversor" else todos)


def _preco(equipamento):
    return float(equipamento.preco_referencia) if equipamento.preco_referencia is not None else None


def item_do_catalogo(funcao, distribuidor, estrutura="", espessura=None):
    """O item mais barato por peça para o papel no kit (D34), ou None.

    Estrutura: o item do tipo de telhado, se houver; senão um item que serve para qualquer um.
    Grampo final: o da espessura da moldura do módulo, se houver.
    """
    candidatos = list(Equipamento.objects.filter(funcao=funcao, ativo=True, distribuidor__iexact=distribuidor))
    exatos = [e for e in candidatos if estrutura and e.tipo_estrutura == estrutura]
    candidatos = exatos or [e for e in candidatos if not e.tipo_estrutura]
    if espessura:
        candidatos = [e for e in candidatos if e.espessura_mm == espessura] or candidatos
    if not candidatos:
        return None
    return min(candidatos, key=lambda e: (_preco(e) is None, (_preco(e) or 0) / max(e.pecas_por_embalagem, 1)))


def _conferir_cotacao(cotacao, m, tolerancia):
    """A cotação escolhida precisa ser do mesmo distribuidor e do mesmo tamanho do sistema (A01)."""
    if cotacao.distribuidor.lower() != m.modulo.distribuidor.lower():
        m.alerta("erro", f"A cotação é da {cotacao.distribuidor} e o módulo é da {m.modulo.distribuidor}. "
                         "Escolha a cotação do mesmo distribuidor.")
    kwp_cotacao = float(cotacao.kwp)
    if abs(m.kwp - kwp_cotacao) > kwp_cotacao * tolerancia:
        quantidade = round(kwp_cotacao * 1000 / m.modulo.potencia_w)
        m.alerta("erro", f"A cotação {cotacao.numero or ''} é de {_num(kwp_cotacao)} kWp e o sistema tem "
                         f"{_num(m.kwp)} kWp. Use {quantidade} módulos ou escolha outra cotação.".replace("  ", " "))


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
    """Tudo o que as telas e o PDF mostram, em etapas: tarifa → consumo → sistema → preço → financeiro.

    Cada etapa preenche `m`; se faltar algo, grava `m.mensagem` e a montagem para ali.
    """
    config = config or ConfigEmpresa.obter()
    m = Montagem()
    premissas = premissas_da_proposta(proposta, config)
    falta_tarifa = _etapa_tarifa(proposta, m)
    if m.mensagem:
        return m
    consumo_motor = _etapa_consumo(proposta, m)
    if consumo_motor is None:
        m.mensagem = m.mensagem or falta_tarifa
        return m
    if not _etapa_sistema(proposta, m, config, premissas):
        return m
    if not _etapa_preco(proposta, m, config):
        return m
    if falta_tarifa:
        m.mensagem = falta_tarifa
        m.alerta("erro", falta_tarifa)
        return m
    _etapa_financeiro(proposta, m, premissas, consumo_motor)
    return m


def _etapa_tarifa(proposta, m):
    """Tarifa com tributos (R$/kWh). Devolve o aviso de tarifa incompleta, que só pesa no financeiro."""
    tarifa = proposta.tipo_tarifa
    if not tarifa:
        m.mensagem = "Escolha o tipo de tarifa (passo 1)."
        return ""
    if tarifa.aliquota_tributos:
        m.tarifa_kwh = float(tarifa.tarifa_com_tributos)
    if not tarifa.aliquota_tributos or tarifa.fiob_kwh is None:
        return (f"A tarifa {tarifa.get_tipo_display()} está sem tributos ou sem Fio B. "
                "O gestor preenche em Configurações → Tarifas.")
    return ""


def _etapa_consumo(proposta, m):
    """Consumo, iluminação pública e consumo com folga. Devolve (kWh, dias) para o motor, ou None."""
    m.disponibilidade = UnidadeConsumidora.DISPONIBILIDADE_KWH.get(proposta.ligacao, 0)
    m.municipio = municipio_da_proposta(proposta)
    consumo_motor = _consumo(proposta, m)
    if consumo_motor is None:
        return None
    if proposta.origem_consumo != proposta.OrigemConsumo.CONTA:
        tabela = tabela_iluminacao(proposta, m.municipio) if proposta.iluminacao_publica is None else None
        if tabela:
            m.iluminacao, m.iluminacao_estimada = calculo.iluminacao_pela_tabela(m.consumo, *tabela), True
        else:
            m.iluminacao = float(proposta.iluminacao_publica or 0)
    m.consumo_alvo = calculo.geracao_necessaria(m.consumo, float(proposta.folga or 0))
    return consumo_motor


def _etapa_sistema(proposta, m, config, premissas):
    """Módulo e quantidade, inversor, strings, fileiras, kit, geração e alertas. False se faltar catálogo ou irradiação.

    A ordem é a do vendedor (D34): o módulo e a quantidade definem o resto do kit.
    """
    if not m.municipio or not m.municipio.irradiacao:
        m.mensagem = "O município do cliente está sem irradiação. Atualize em Configurações → Municípios."
        return False
    irradiacao = m.municipio.irradiacao
    fator = premissas.get("fator_orientacao", 1.0)
    perdas, clipping = premissas["perdas"], premissas["perda_clipping"]
    m.kwp_necessario = calculo.kwp_necessario(m.consumo, float(proposta.folga or 0), irradiacao, perdas, clipping, fator)
    da_cotacao = _principais_da_cotacao(proposta.cotacao) if proposta.cotacao_id else {}

    m.modulo = da_cotacao.get("modulo") or proposta.modulo or sugerir_modulo(config.distribuidor_kit)
    m.modulo_sugerido = not da_cotacao.get("modulo") and proposta.modulo_id is None
    if not m.modulo:
        m.mensagem = f"Nenhum módulo da {config.distribuidor_kit} no catálogo. Importe o catálogo em Catálogo solar."
        return False
    m.qtd_modulos_sugerida = calculo.quantidade_modulos(m.kwp_necessario, m.modulo.potencia_w)
    m.qtd_modulos = da_cotacao.get("qtd_modulos") or proposta.qtd_modulos or m.qtd_modulos_sugerida
    m.kwp = m.qtd_modulos * m.modulo.potencia_w / 1000

    m.sobrecarga_max = premissas["razao_cc_ca_max"]
    m.estrutura = dict(Equipamento.TipoEstrutura.choices).get(proposta.tipo_estrutura, "")
    m.micro = proposta.tipo_inversor == proposta.TipoInversor.MICRO
    fase = fase_do_inversor(proposta.ligacao)
    _escolher_inversor(proposta, m, config, premissas, fase, da_cotacao)
    if not m.inversor:
        tipo = "microinversor" if m.micro else "inversor da fase da ligação"
        m.mensagem = f"Nenhum {tipo} que sirva no catálogo. Cadastre em Catálogo solar."
        return False
    m.kw_ca = m.inversor.potencia_w / 1000 * m.qtd_inversores
    m.sobrecarga = m.kwp / m.kw_ca

    if m.micro:
        m.strings = m.qtd_inversores
    else:
        m.strings = calculo.strings_do_inversor(
            m.qtd_modulos, (m.inversor.mppts or 1) * m.qtd_inversores,
            config.modulos_por_string_min, config.modulos_por_string_max)
    _definir_fileiras(proposta, m, config)
    if proposta.cotacao_id:
        _kit_da_cotacao(proposta.cotacao, m)
    else:
        _kit_do_catalogo(proposta, m, config)

    m.geracao_media = m.kwp * calculo.geracao_por_kwp_mes(irradiacao, perdas, clipping, fator)
    if m.modulo.area_m2:
        m.area = m.qtd_modulos * float(m.modulo.area_m2)
    elif m.modulo.comprimento_mm and m.modulo.largura_mm:
        m.area = m.qtd_modulos * m.modulo.comprimento_mm * m.modulo.largura_mm / 1_000_000
    _alertas_do_sistema(proposta, m, config, premissas, fase)
    return True


def _principais_da_cotacao(cotacao):
    """Módulo e inversor da cotação vinculada, quando os itens estão ligados ao catálogo (D35)."""
    principais = {}
    for item in cotacao.itens.select_related("equipamento"):
        equipamento = item.equipamento
        if not equipamento:
            continue
        if equipamento.tipo == "modulo" and "modulo" not in principais:
            principais["modulo"], principais["qtd_modulos"] = equipamento, int(item.quantidade)
        elif equipamento.tipo in ("inversor", "microinversor") and "inversor" not in principais:
            principais["inversor"], principais["qtd_inversores"] = equipamento, int(item.quantidade)
    return principais


def _escolher_inversor(proposta, m, config, premissas, fase, da_cotacao):
    """O inversor da cotação ou do vendedor, ou o sugerido do tipo escolhido na chave (D19, D34)."""
    tipo = "microinversor" if m.micro else "inversor"
    if da_cotacao.get("inversor"):
        m.inversor, m.qtd_inversores = da_cotacao["inversor"], da_cotacao["qtd_inversores"]
        m.micro = m.inversor.tipo == "microinversor"
        m.inversor_sugerido = False
        return
    escolhido = proposta.inversor if proposta.inversor_id and proposta.inversor.tipo == tipo else None
    if proposta.inversor_id and not escolhido:
        m.alerta("aviso", f"O inversor escolhido não é {'micro' if m.micro else 'string'}: "
                          "o sistema sugeriu outro. Escolha de novo na lista.")
    m.inversor_sugerido = escolhido is None
    if escolhido:
        m.inversor = escolhido
        if m.micro:
            sugerida = calculo.quantidade_micros(m.qtd_modulos, escolhido.modulos_por_micro or 1)
        else:
            sugerida = max(1, math.ceil(m.kwp / (escolhido.potencia_w / 1000 * m.sobrecarga_max)))
        m.qtd_inversores = proposta.qtd_inversores or sugerida
        return
    candidatos = inversores_candidatos(fase, config.distribuidor_kit, tipo)
    if m.micro:
        sugerido, m.qtd_inversores = calculo.sugerir_micro(
            m.qtd_modulos, m.modulo.potencia_w,
            [{"w": e.potencia_w, "modulos": e.modulos_por_micro, "preco": _preco(e), "equipamento": e}
             for e in candidatos], m.sobrecarga_max)
    else:
        sugerido, m.qtd_inversores = calculo.sugerir_inversor(
            m.kwp, [{"kw": e.potencia_w / 1000, "fase": e.fase, "preco": _preco(e), "equipamento": e}
                    for e in candidatos],
            fase, m.sobrecarga_max, premissas.get("sobrecarga_min", 0.8))
    m.inversor = sugerido["equipamento"] if sugerido else None
    if proposta.qtd_inversores and m.inversor:
        m.qtd_inversores = proposta.qtd_inversores


def ler_fileiras(texto):
    """"6+5" → [6, 5]. Texto vazio ou inválido → []. A validação com mensagem fica no formulário."""
    partes = re.split(r"[+,;\s]+", (texto or "").strip())
    return [int(p) for p in partes if p.isdigit() and int(p) > 0]


def _definir_fileiras(proposta, m, config):
    """Fileiras do vendedor ou, em branco, os módulos divididos igual entre as strings (D34)."""
    m.fileiras = ler_fileiras(proposta.fileiras)
    m.fileiras_sugeridas = not m.fileiras
    if m.fileiras_sugeridas:
        partes = math.ceil(m.qtd_modulos / config.modulos_por_string_max) if m.micro else m.strings
        m.fileiras = calculo.dividir_em_fileiras(m.qtd_modulos, partes)


def _kit_da_cotacao(cotacao, m):
    """Kit = itens da cotação, como vieram; o catálogo é ignorado (D35)."""
    m.kit_da_cotacao = True
    itens = list(cotacao.itens.select_related("equipamento"))
    if not itens:  # cotação registrada só com o total: o PDF mostra ao menos módulo e inversor
        m.kit = [LinhaKit("modulo", None, m.modulo.descricao, m.qtd_modulos),
                 LinhaKit("inversor", None, m.inversor.descricao, m.qtd_inversores)]
        return
    for item in itens:
        equipamento = item.equipamento
        funcao = equipamento.tipo if equipamento and equipamento.tipo in ("modulo", "inversor") else ""
        m.kit.append(LinhaKit(funcao or (equipamento.funcao if equipamento else "") or "extra", None,
                              item.descricao, int(item.quantidade), item.unidade))


def _kit_do_catalogo(proposta, m, config):
    """Kit completo pelo catálogo (D34): módulo, inversor, estrutura, cabos, conectores e os extras do vendedor."""
    ajustes = proposta.ajustes_kit or {}
    m.kit = [
        LinhaKit("modulo", m.modulo, m.modulo.descricao, m.qtd_modulos, sugerida=m.qtd_modulos_sugerida,
                 alterada=not m.modulo_sugerido or m.qtd_modulos != m.qtd_modulos_sugerida),
        LinhaKit("inversor", m.inversor, m.inversor.descricao, m.qtd_inversores, alterada=not m.inversor_sugerido),
    ]
    espessura = m.modulo.espessura_mm or config.espessura_modulo_padrao
    papeis = ["trilho", "juncao", "fixacao", "haste", "mini_trilho", "grampo_final", "grampo_intermediario",
              "aterramento"]
    if m.micro:
        papeis.append("suporte_micro")
    escolhidos = {}
    for papel in papeis + ["cabo_vermelho", "cabo_preto", "conector"]:
        ajuste = ajustes.get(papel) or {}
        trocado = Equipamento.objects.filter(pk=ajuste.get("equipamento")).first() if ajuste.get("equipamento") else None
        escolhidos[papel] = trocado or item_do_catalogo(
            papel, config.distribuidor_kit, proposta.tipo_estrutura, espessura if papel == "grampo_final" else None)
    pecas = {papel: e.pecas_por_embalagem for papel, e in escolhidos.items() if e}

    sugeridas = calculo.quantidades_estrutura(m.fileiras, proposta.tipo_estrutura, pecas) if proposta.tipo_estrutura else {}
    if m.micro:
        sugeridas["suporte_micro"] = m.qtd_inversores
    sugeridas |= calculo.quantidades_eletricas(
        m.strings, 0 if m.micro else config.metros_cabo_por_string,
        config.pares_conector_por_micro if m.micro else config.pares_conector_por_string, pecas.get("conector", 1))

    for papel, sugerida in sugeridas.items():
        ajuste = ajustes.get(papel) or {}
        quantidade = ajuste["quantidade"] if ajuste.get("quantidade") is not None else sugerida
        equipamento = escolhidos.get(papel)
        if not equipamento:
            m.alerta("aviso", f"Sem {Equipamento.Funcao(papel).label.lower()} da {config.distribuidor_kit} no "
                              "catálogo. Acrescente o item à mão no kit.")
            continue
        if quantidade:
            unidade = "m" if papel.startswith("cabo") else "un"
            m.kit.append(LinhaKit(papel, equipamento, equipamento.descricao, quantidade, unidade, sugerida,
                                  alterada=bool(ajuste)))
    for extra in ajustes.get("extras", []):
        equipamento = Equipamento.objects.filter(pk=extra.get("equipamento")).first()
        if equipamento and extra.get("quantidade"):
            m.kit.append(LinhaKit("extra", equipamento, equipamento.descricao, extra["quantidade"], alterada=True))


def ajustes_do_kit_completo(m):
    """O kit montado escrito como ajustes do vendedor: na emissão, congela itens e quantidades (D34)."""
    ajustes = {"extras": []}
    for linha in m.kit:
        if linha.funcao in ("modulo", "inversor") or not linha.equipamento:
            continue
        if linha.funcao == "extra":
            ajustes["extras"].append({"equipamento": linha.equipamento.pk, "quantidade": linha.quantidade})
        else:
            ajustes[linha.funcao] = {"equipamento": linha.equipamento.pk, "quantidade": linha.quantidade}
    return ajustes


def _alertas_do_sistema(proposta, m, config, premissas, fase):
    sobrecarga_min = premissas.get("sobrecarga_min", 0.8)  # snapshots antigos não têm a chave (A25)
    if m.sobrecarga > m.sobrecarga_max:
        m.alerta("erro", f"Inversor pequeno demais: os módulos somam {_num(m.sobrecarga)} vezes a potência dele "
                         f"(máximo {_num(m.sobrecarga_max)}). Escolha um inversor maior ou mais um inversor.")
    elif m.sobrecarga < sobrecarga_min:
        m.alerta("aviso", f"Inversor grande para o sistema: os módulos somam só {_num(m.sobrecarga)} vezes a "
                          "potência dele. Há modelo menor?")
    if m.inversor.fase and m.inversor.fase != fase and not m.micro:
        m.alerta("erro", f"Ligação {proposta.get_ligacao_display().lower()} com inversor {m.inversor.get_fase_display().lower()}.")
    if m.micro and fase == "tri":
        m.alerta("aviso", "Microinversores são 220 V: numa ligação trifásica, divida os micros entre as fases.")
    if not m.micro and m.inversor.mppts and m.strings > m.inversor.mppts * m.qtd_inversores:
        m.alerta("aviso", f"{m.strings} strings para {m.inversor.mppts * m.qtd_inversores} MPPT: confira se o "
                          "inversor aceita duas strings por MPPT.")
    if sum(m.fileiras) != m.qtd_modulos:
        m.alerta("erro", f"As fileiras ({m.fileiras_texto}) somam {sum(m.fileiras)} módulos e o sistema tem "
                         f"{m.qtd_modulos}. Corrija as fileiras.")
    elif m.fileiras_sugeridas and not m.kit_da_cotacao:
        m.alerta("aviso", f"Fileiras sugeridas pelo sistema ({m.fileiras_texto}). Confira no telhado.")
    limite = float(config.limite_microgeracao_kwp)
    if m.kwp > limite:
        m.alerta("aviso", f"Sistema de {_num(m.kwp)} kWp: acima de {_num(limite, 0)} kWp deixa de ser microgeração "
                          "(Grupo A). Confira com o gestor.", interno=False)


def _custo_pelo_catalogo(m, config):
    """Soma dos itens do catálogo mais o frete (D34). Item sem preço impede o cálculo."""
    sem_preco = [linha.descricao for linha in m.kit if linha.preco is None]
    if sem_preco:
        m.mensagem = f"Sem preço no catálogo: {', '.join(sem_preco)}. Atualize o catálogo ou informe o custo do kit."
        m.alerta("erro", m.mensagem)
        return
    m.produtos_kit = sum(linha.subtotal for linha in m.kit)
    m.frete_kit = m.produtos_kit * float(config.frete_kit)
    m.custo_kit = calculo.custo_do_kit([(linha.quantidade, linha.preco) for linha in m.kit], float(config.frete_kit))
    datas = [linha.equipamento.preco_em for linha in m.kit if linha.equipamento.preco_em]
    if datas:
        dias = (timezone.localdate() - min(datas)).days
        if dias > config.dias_catalogo_velho:
            m.alerta("aviso", f"Preços do catálogo de {min(datas):%d/%m/%Y} ({dias} dias). "
                              "Reimporte o catálogo da " + config.distribuidor_kit + ".")


def _etapa_preco(proposta, m, config):
    """Custo do kit, mão de obra, desconto e investimento. False se não houver custo do kit."""
    if proposta.custo_kit is not None:
        m.custo_kit = float(proposta.custo_kit)
    elif proposta.cotacao_id:
        m.custo_kit = float(proposta.cotacao.total)
    else:
        _custo_pelo_catalogo(m, config)
    if proposta.cotacao_id:
        _conferir_cotacao(proposta.cotacao, m, float(config.tolerancia_kwp_cotacao))
        if proposta.cotacao.idade_dias > config.dias_preco_velho:
            m.alerta("aviso", f"Cotação do kit com {proposta.cotacao.idade_dias} dias. Peça uma cotação nova.")

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
        return False
    m.investimento = m.custo_kit + m.mao_de_obra - m.desconto
    m.rs_por_wp = m.investimento / (m.kwp * 1000)
    if proposta.nivel == proposta.Nivel.ESTIMATIVA:
        m.alerta("aviso", "Proposta de estimativa: vai com o aviso de dados não confirmados.", interno=False)
    return True


def _etapa_financeiro(proposta, m, premissas, consumo_motor):
    """Motor de cálculo (economia, retorno), conta de luz antes e depois e tabela de financiamento."""
    tarifa = proposta.tipo_tarifa
    kwh_fatura, dias = consumo_motor
    digitos = re.sub(r"\D", "", proposta.cliente.cpf_cnpj or "")
    entrada = calculo.EntradaCalculo(
        kwp=m.kwp, kw_ca=m.kw_ca, irradiacao=m.municipio.irradiacao, kwh_fatura=float(kwh_fatura), dias_ciclo=dias,
        tarifa=m.tarifa_kwh, fiob_kwh=float(tarifa.fiob_kwh), disponibilidade_kwh=m.disponibilidade,
        investimento=m.investimento,
        fiob_pct_por_ano={f.ano: float(f.percentual) / 100 for f in FioBEscalonamento.objects.all()},
        premissas=premissas, classe=tarifa.tipo[:2], cliente_pessoa_juridica=len(digitos) > 11,
        fator_orientacao=premissas.get("fator_orientacao", 1.0),
    )
    m.resultado = calculo.calcular(entrada)
    for texto in m.resultado.alertas:
        if not texto.startswith("Razão CC/CA"):  # a sobrecarga já tem alerta próprio
            m.alerta("aviso", texto)

    if proposta.origem_consumo == proposta.OrigemConsumo.CONTA:
        m.conta_hoje = float(proposta.conta_informada)  # o valor que o cliente paga, com bandeira e iluminação
    else:
        m.conta_hoje = m.consumo * m.tarifa_kwh + m.iluminacao
    # A economia ignora a disponibilidade (D33), mas a conta mostrada não fica abaixo do mínimo que a
    # distribuidora cobra: disponibilidade (30/50/100 kWh) mais a iluminação pública.
    conta_minima = m.disponibilidade * m.tarifa_kwh + m.iluminacao
    m.conta_com_sistema = max(m.conta_hoje - m.resultado.economia_mensal_ano1, conta_minima)

    taxas = [(t.banco, t.prazo_meses, float(t.taxa_mensal), float(t.tac_reais), float(t.tac_percentual))
             for t in TaxaFinanciamento.objects.all()]
    config = ConfigEmpresa.obter()
    iof_diario = float(config.iof_diario_pj if len(digitos) > 11 else config.iof_diario_pf)  # sem CPF: pessoa física
    m.iof = {"diario": iof_diario, "adicional": float(config.iof_adicional)}
    tabela = calculo.tabela_financiamento(m.investimento, taxas, m.iof["diario"], m.iof["adicional"])
    m.financiamento = [linha | {"taxa_pct": linha["taxa"] * 100, "taxa_ano_pct": ((1 + linha["taxa"]) ** 12 - 1) * 100}
                       for linha in tabela]
    prazos = [linha["prazo"] for linha in m.financiamento]
    if prazos:
        m.prazo = proposta.prazo_comparacao if proposta.prazo_comparacao in prazos else prazos[-1]
        m.parcela = next(linha for linha in m.financiamento if linha["prazo"] == m.prazo)
        m.conta_com_parcela = m.conta_com_sistema + m.parcela["parcela"]
    m.barra_max = max(m.conta_hoje, m.conta_com_parcela or 0)


def gravar_resultado(proposta, m):
    """Guarda o kit montado, o investimento e o resumo na proposta (rascunho)."""
    config = ConfigEmpresa.obter()
    proposta.premissas = premissas_da_proposta(proposta, config)
    proposta.investimento = Decimal(f"{m.investimento:.2f}") if m.investimento is not None else None
    proposta.kwp = Decimal(f"{m.kwp:.3f}") if m.kwp else None
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
    for ordem, linha in enumerate(m.kit):
        equipamento = linha.equipamento
        ItemKit.objects.create(
            proposta=proposta, tipo=_TIPO_DO_ITEM.get(linha.funcao, ItemKit.Tipo.ESTRUTURA if equipamento
                                                      and equipamento.tipo == "estrutura" else ItemKit.Tipo.OUTRO),
            equipamento=equipamento, descricao=linha.descricao, modelo=equipamento.codigo if equipamento else "",
            quantidade=linha.quantidade, unidade=linha.unidade,
            potencia_w=equipamento.potencia_w if equipamento else None, funcao=linha.funcao,
            preco_unitario=equipamento.preco_referencia if equipamento else None, ordem=ordem,
        )


_TIPO_DO_ITEM = {"modulo": ItemKit.Tipo.MODULO, "inversor": ItemKit.Tipo.INVERSOR,
                 "cabo_preto": ItemKit.Tipo.CABEAMENTO, "cabo_vermelho": ItemKit.Tipo.CABEAMENTO,
                 "conector": ItemKit.Tipo.CABEAMENTO}


def _equipamento(equipamento):
    if not equipamento:
        return None
    return {"id": equipamento.pk, "codigo": equipamento.codigo, "descricao": equipamento.descricao,
            "distribuidor": equipamento.distribuidor, "potencia_w": equipamento.potencia_w}


def _decimal(valor):
    return float(valor) if valor is not None else None


def registro_da_emissao(proposta, m, premissas):
    """Entradas e saídas do cálculo no momento da emissão (A10, D36), para auditoria.

    Guarda os valores (não só as chaves), porque tarifas, taxas e catálogo mudam depois.
    """
    tarifa, fatura, cotacao, municipio = proposta.tipo_tarifa, proposta.fatura, proposta.cotacao, m.municipio
    entradas = {
        "cliente": {"id": proposta.cliente_id, "nome": proposta.cliente.nome},
        "nivel": proposta.nivel,
        "ligacao": proposta.ligacao,
        "origem_consumo": proposta.origem_consumo,
        "conta_informada": _decimal(proposta.conta_informada),
        "kwh_informado": _decimal(proposta.kwh_informado),
        "iluminacao_publica": _decimal(proposta.iluminacao_publica),
        "bandeira": proposta.bandeira.nome if proposta.bandeira else None,
        "fatura": {"id": fatura.pk, "competencia": fatura.competencia.isoformat(), "kwh": fatura.kwh,
                   "dias_ciclo": fatura.dias_ciclo, "valor_total": _decimal(fatura.valor_total)} if fatura else None,
        "folga": _decimal(proposta.folga),
        "perfil_simultaneidade": proposta.perfil_simultaneidade,
        "orientacao": proposta.orientacao,
        "tipo_estrutura": proposta.tipo_estrutura,
        "tipo_inversor": proposta.tipo_inversor,
        "fileiras": proposta.fileiras,
        "ajustes_kit": proposta.ajustes_kit,
        "tarifa": {"id": tarifa.pk, "tipo": tarifa.tipo, "vigencia_inicio": tarifa.vigencia_inicio.isoformat(),
                   "tusd": _decimal(tarifa.tusd), "te": _decimal(tarifa.te),
                   "aliquota_tributos": _decimal(tarifa.aliquota_tributos), "fiob_kwh": _decimal(tarifa.fiob_kwh)},
        "municipio": {"id": municipio.pk, "nome": municipio.nome, "irradiacao": municipio.irradiacao,
                      "fonte_irradiacao": municipio.fonte_irradiacao},
        "premissas": premissas,
        "cotacao": {"id": cotacao.pk, "distribuidor": cotacao.distribuidor, "numero": cotacao.numero,
                    "kwp": _decimal(cotacao.kwp), "total": _decimal(cotacao.total)} if cotacao else None,
        "custo_kit_digitado": _decimal(proposta.custo_kit),
        "mao_de_obra_digitada": _decimal(proposta.mao_de_obra),
        "desconto_pct": _decimal(proposta.desconto_pct),
        "iof": getattr(m, "iof", None),
    }
    saidas = {
        "consumo_kwh": m.consumo,
        "consumo_alvo_kwh": m.consumo_alvo,
        "tarifa_kwh": m.tarifa_kwh,
        "iluminacao": m.iluminacao,
        "iluminacao_estimada": m.iluminacao_estimada,
        "modulo": _equipamento(m.modulo),
        "qtd_modulos": m.qtd_modulos,
        "modulo_sugerido": m.modulo_sugerido,
        "inversor": _equipamento(m.inversor),
        "qtd_inversores": m.qtd_inversores,
        "inversor_sugerido": m.inversor_sugerido,
        "micro": m.micro,
        "strings": m.strings,
        "fileiras": m.fileiras,
        "kit": [{"funcao": linha.funcao, "codigo": linha.equipamento.codigo if linha.equipamento else "",
                 "descricao": linha.descricao, "quantidade": linha.quantidade, "unidade": linha.unidade,
                 "preco": linha.preco, "sugerida": linha.sugerida} for linha in m.kit],
        "kit_da_cotacao": m.kit_da_cotacao,
        "kwp": m.kwp,
        "kw_ca": m.kw_ca,
        "sobrecarga": m.sobrecarga,
        "geracao_media_kwh": m.geracao_media,
        "custo_kit": m.custo_kit,
        "produtos_kit": m.produtos_kit,
        "frete_kit": m.frete_kit,
        "mao_de_obra": m.mao_de_obra,
        "mo_sugerida": m.mo_sugerida,
        "desconto": m.desconto,
        "investimento": m.investimento,
        "resultado": asdict(m.resultado) if m.resultado else None,
        "conta_hoje": m.conta_hoje,
        "conta_com_sistema": m.conta_com_sistema,
        "financiamento": m.financiamento,
        "prazo": m.prazo,
        "alertas": m.alertas,
    }
    return {"versao_registro": 2, "entradas": entradas, "saidas": saidas}
