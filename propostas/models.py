from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone

from clientes.models import Cliente, UnidadeConsumidora


class FaturaReferencia(models.Model):
    uc = models.ForeignKey(UnidadeConsumidora, on_delete=models.CASCADE, related_name="faturas")
    competencia = models.DateField(help_text="Mês/ano de referência da fatura.")
    kwh = models.PositiveIntegerField("consumo (kWh)")
    dias_ciclo = models.PositiveIntegerField("dias do ciclo")
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    composicao = models.JSONField(
        null=True, blank=True, help_text='Opcional: [{"item": "...", "pct": 31.68}, ...]'
    )
    arquivo = models.FileField("arquivo da fatura (PDF)", upload_to="faturas/", blank=True)

    class Meta:
        verbose_name = "Fatura de referência"
        verbose_name_plural = "Faturas de referência"
        ordering = ["-competencia"]

    def __str__(self):
        return f"Fatura {self.uc.numero_uc} — {self.competencia:%m/%Y}"


class FioBEscalonamento(models.Model):
    ano = models.PositiveIntegerField(unique=True)
    percentual = models.DecimalField("percentual (%)", max_digits=5, decimal_places=2)

    class Meta:
        verbose_name = "Escalonamento do Fio B"
        verbose_name_plural = "Escalonamento do Fio B"
        ordering = ["ano"]

    def __str__(self):
        return f"{self.ano}: {self.percentual}%"


class Proposta(models.Model):
    """Só `rascunho` é editável. "Revisar" uma emitida cria nova versão em rascunho copiando tudo.

    Entrada em 4 passos (D17–D29); a proposta da fatia 4 (formulário antigo) foi removida na rodada 3.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        EMITIDA = "emitida", "Emitida"
        ACEITA = "aceita", "Aceita"
        PERDIDA = "perdida", "Perdida"
        SUBSTITUIDA = "substituida", "Substituída"

    class MotivoPerda(models.TextChoices):
        PRECO = "preco", "Preço"
        CONCORRENTE = "concorrente", "Fechou com concorrente"
        FINANCIAMENTO = "financiamento", "Financiamento negado"
        DESISTIU = "desistiu", "Cliente desistiu ou adiou"
        SEM_RETORNO = "sem_retorno", "Sem retorno do cliente"
        OUTRO = "outro", "Outro"

    class Nivel(models.TextChoices):
        ESTIMATIVA = "estimativa", "Estimativa"
        CONFIRMADA = "confirmada", "Confirmada"

    class OrigemConsumo(models.TextChoices):
        CONTA = "rs", "Valor da conta"
        KWH = "kwh", "kWh por mês"
        FATURA = "fatura", "Fatura"

    class TipoInversor(models.TextChoices):
        STRING = "string", "Inversor string"
        MICRO = "microinversor", "Microinversor"

    class Orientacao(models.TextChoices):
        NORTE = "norte", "Norte"
        NORDESTE_NOROESTE = "nordeste_noroeste", "Nordeste ou noroeste"
        LESTE_OESTE = "leste_oeste", "Leste ou oeste"
        SUL = "sul", "Sul"

    # O mesmo em todas as versões (D31). Vazio no rascunho: o número sai na primeira emissão (D36).
    numero = models.CharField("número", max_length=30, null=True, blank=True)
    versao = models.PositiveIntegerField(default=1)
    origem = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="revisoes"
    )
    # Local da instalação. Fica na proposta (não no cliente) para mudar sem afetar outras propostas (A04).
    municipio = models.ForeignKey(
        "core.Municipio", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        verbose_name="município da instalação",
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="propostas")
    uc = models.ForeignKey(
        UnidadeConsumidora, on_delete=models.PROTECT, related_name="propostas", null=True, blank=True
    )
    fatura = models.ForeignKey(
        FaturaReferencia, on_delete=models.PROTECT, related_name="propostas", null=True, blank=True
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RASCUNHO)
    emissao = models.DateField(null=True, blank=True)
    data_aceite = models.DateField("data do aceite", null=True, blank=True)
    motivo_perda = models.CharField("motivo da perda", max_length=15, choices=MotivoPerda.choices, blank=True)
    obs_perda = models.TextField("observação da perda", blank=True)
    # Aceite desfeito (D33): a última vez, com o motivo. Volta a ser emitida.
    aceite_desfeito_em = models.DateField("aceite desfeito em", null=True, blank=True)
    motivo_aceite_desfeito = models.TextField("motivo do aceite desfeito", blank=True)
    validade_dias = models.PositiveIntegerField(default=15)
    investimento = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    kwp = models.DecimalField("potência (kWp)", max_digits=8, decimal_places=3, null=True, blank=True)  # A28

    # ---- Proposta v2: entrada em 4 passos (D17–D29). Tudo opcional para salvar o rascunho a cada passo.
    nivel = models.CharField("nível", max_length=10, choices=Nivel.choices, default=Nivel.ESTIMATIVA)
    passo_atual = models.PositiveSmallIntegerField(default=1)
    ligacao = models.CharField("ligação", max_length=4, choices=UnidadeConsumidora.Ligacao.choices, blank=True)
    tipo_tarifa = models.ForeignKey(
        "TarifaVigente", on_delete=models.PROTECT, null=True, blank=True, verbose_name="tipo de tarifa"
    )
    origem_consumo = models.CharField(
        "origem do consumo", max_length=6, choices=OrigemConsumo.choices, blank=True
    )
    conta_informada = models.DecimalField("valor da conta (R$)", max_digits=10, decimal_places=2, null=True, blank=True)
    iluminacao_publica = models.DecimalField(
        "iluminação pública (R$)", max_digits=10, decimal_places=2, null=True, blank=True
    )
    bandeira = models.ForeignKey("Bandeira", on_delete=models.SET_NULL, null=True, blank=True)
    kwh_informado = models.DecimalField("consumo (kWh/mês)", max_digits=10, decimal_places=2, null=True, blank=True)
    folga = models.DecimalField("folga (fração)", max_digits=6, decimal_places=4, null=True, blank=True)
    perfil_simultaneidade = models.CharField("perfil de uso", max_length=80, blank=True)
    orientacao = models.CharField("orientação", max_length=20, choices=Orientacao.choices, blank=True)
    tipo_estrutura = models.CharField("estrutura", max_length=15, blank=True)
    # Kit: vazio = usar a sugestão do sistema (o vendedor só preenche o que quer mudar).
    modulo = models.ForeignKey(
        "Equipamento", on_delete=models.PROTECT, null=True, blank=True, related_name="+", verbose_name="módulo",
    )
    qtd_modulos = models.PositiveIntegerField("quantidade de módulos", null=True, blank=True)
    inversor = models.ForeignKey(
        "Equipamento", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    qtd_inversores = models.PositiveSmallIntegerField("quantidade de inversores", null=True, blank=True)
    tipo_inversor = models.CharField(
        "tipo de inversor", max_length=13, choices=TipoInversor.choices, default=TipoInversor.STRING,
    )
    fileiras = models.CharField(
        "módulos por fileira", max_length=120, blank=True, help_text='Ex.: "6+5". Vazio = o sistema divide.',
    )
    # Trocas do vendedor nos outros itens do kit (D34), por papel no kit:
    # {"trilho": {"equipamento": 12, "quantidade": 8}, ..., "extras": [{"equipamento": 30, "quantidade": 2}]}.
    # O que não está aqui segue a sugestão. Na emissão, o kit inteiro é gravado aqui.
    ajustes_kit = models.JSONField("ajustes do kit", default=dict, blank=True)
    cotacao = models.ForeignKey(
        "Cotacao", on_delete=models.SET_NULL, null=True, blank=True, related_name="propostas_vinculadas",
        verbose_name="cotação do kit",
    )
    custo_kit = models.DecimalField("custo do kit (R$)", max_digits=12, decimal_places=2, null=True, blank=True)
    mao_de_obra = models.DecimalField("mão de obra (R$)", max_digits=12, decimal_places=2, null=True, blank=True)
    desconto = models.DecimalField("desconto (R$)", max_digits=12, decimal_places=2, null=True, blank=True)
    desconto_pct = models.DecimalField(
        "desconto (fração da mão de obra)", max_digits=6, decimal_places=4, null=True, blank=True,
        help_text="Preenchido quando o vendedor digitou o desconto em %.",
    )
    prazo_comparacao = models.PositiveSmallIntegerField("prazo para comparar (meses)", null=True, blank=True)
    forma_pagamento = models.CharField(max_length=255, blank=True)
    beneficios = models.TextField(blank=True)
    escopo = models.TextField(blank=True)
    texto_sobre = models.TextField(blank=True)
    premissas = models.JSONField(default=dict, help_text="Snapshot das premissas no momento da emissão.")
    resultados = models.JSONField(default=dict, blank=True, help_text="Snapshot dos resultados calculados.")
    pdf = models.FileField(upload_to="propostas/", blank=True)
    # Registro da emissão (A10, D36): entradas e saídas do cálculo, e quem fez cada ação.
    registro = models.JSONField(default=dict, blank=True, help_text="Entradas e saídas do cálculo na emissão.")
    emitida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    aceita_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    perdida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="marcada como perdida por",
    )
    aceite_desfeito_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "Proposta"
        verbose_name_plural = "Propostas"
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["numero", "versao"], name="proposta_numero_versao_unica")]

    def __str__(self):
        return self.identificacao

    @property
    def identificacao(self):
        """"OPT-2026-0001 v2" ou, antes da primeira emissão, "Rascunho 15"."""
        if not self.numero:
            return f"Rascunho {self.pk}"
        return f"{self.numero} v{self.versao}"

    @property
    def validade_ate(self):
        return self.emissao + timezone.timedelta(days=self.validade_dias) if self.emissao else None

    @property
    def vencida(self):
        """Emitida com a validade passada. Não é gravada: é calculada na hora (D31)."""
        return self.status == self.Status.EMITIDA and self.emissao is not None and timezone.localdate() > self.validade_ate

    @property
    def situacao(self):
        return "vencida" if self.vencida else self.status

    @property
    def situacao_display(self):
        return "Vencida" if self.vencida else self.get_status_display()

    @classmethod
    def proximo_numero(cls, ano=None):
        ano = ano or timezone.localdate().year
        prefixo = f"OPT-{ano}-"
        ultimo = (
            cls.objects.filter(numero__startswith=prefixo)
            .order_by("-numero")
            .values_list("numero", flat=True)
            .first()
        )
        proxima_seq = int(ultimo.rsplit("-", 1)[-1]) + 1 if ultimo else 1
        return f"{prefixo}{proxima_seq:04d}"


class ItemKit(models.Model):
    class Tipo(models.TextChoices):
        MODULO = "modulo", "Módulo"
        INVERSOR = "inversor", "Inversor"
        ESTRUTURA = "estrutura", "Estrutura"
        CABEAMENTO = "cabeamento", "Cabeamento"
        OUTRO = "outro", "Outro"

    proposta = models.ForeignKey(Proposta, on_delete=models.CASCADE, related_name="itens_kit")
    equipamento = models.ForeignKey("Equipamento", on_delete=models.SET_NULL, null=True, blank=True)
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    descricao = models.CharField(max_length=255)
    modelo = models.CharField(max_length=120, blank=True)
    quantidade = models.PositiveIntegerField(default=1)
    unidade = models.CharField(max_length=10, default="un")
    potencia_w = models.PositiveIntegerField(null=True, blank=True)
    funcao = models.CharField("papel no kit", max_length=25, blank=True)
    preco_unitario = models.DecimalField(
        "preço unitário (R$)", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Preço do catálogo, sem frete. Vazio quando o kit vem de uma cotação.",
    )
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Item do kit"
        verbose_name_plural = "Itens do kit"
        ordering = ["ordem"]

    def __str__(self):
        return f"{self.quantidade}x {self.descricao}"


class TarifaVigente(models.Model):
    """Tarifa do Grupo B por tipo (D19, D21). TUSD e TE vêm da ANEEL; tributos e Fio B, do gestor."""

    class Tipo(models.TextChoices):
        B1 = "B1", "B1 residencial"
        B1_BAIXA_RENDA = "B1_BAIXA_RENDA", "B1 residencial baixa renda"
        B2 = "B2", "B2 rural"
        B3 = "B3", "B3 comercial e demais"

    distribuidora = models.CharField(max_length=60, default="Energisa TO")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    vigencia_inicio = models.DateField("início da vigência")
    tusd = models.DecimalField("TUSD (R$/kWh, sem tributos)", max_digits=10, decimal_places=6)
    te = models.DecimalField("TE (R$/kWh, sem tributos)", max_digits=10, decimal_places=6)
    aliquota_tributos = models.DecimalField(
        "tributos (fração: ICMS + PIS/COFINS)", max_digits=6, decimal_places=4, default=0,
        help_text="Alíquota efetiva sobre a tarifa final. Digitada pelo gestor.",
    )
    fiob_kwh = models.DecimalField(
        "TUSD Fio B (R$/kWh)", max_digits=10, decimal_places=6, null=True, blank=True,
        help_text="A ANEEL não publica separado: o gestor digita após cada reajuste.",
    )
    fiob_conferido_em = models.DateField("Fio B conferido em", null=True, blank=True)
    fonte = models.CharField(max_length=255, blank=True)
    atualizado_em = models.DateField("atualizado em")

    class Meta:
        verbose_name = "Tarifa vigente"
        verbose_name_plural = "Tarifas vigentes"
        ordering = ["tipo", "-vigencia_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["distribuidora", "tipo", "vigencia_inicio"], name="tarifa_distribuidora_tipo_vigencia_unica"
            )
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.distribuidora} ({self.vigencia_inicio:%d/%m/%Y})"

    @property
    def tarifa_com_tributos(self):
        """Tarifa final por kWh, como aparece na conta: (TUSD + TE) / (1 − tributos)."""
        return (self.tusd + self.te) / (1 - self.aliquota_tributos)

    @property
    def fiob_desatualizado(self):
        return self.fiob_kwh is None or self.fiob_conferido_em is None or self.fiob_conferido_em < self.vigencia_inicio

    @classmethod
    def vigentes(cls):
        """A tarifa mais recente de cada tipo, em cada distribuidora (uma não substitui a outra)."""
        mais_recentes = {}
        for tarifa in cls.objects.order_by("distribuidora", "tipo", "-vigencia_inicio"):
            mais_recentes.setdefault((tarifa.distribuidora, tarifa.tipo), tarifa)
        return list(mais_recentes.values())


class Bandeira(models.Model):
    """Adicional da bandeira tarifária por kWh (ANEEL). Mantido pelo gestor."""

    nome = models.CharField(max_length=40, unique=True)
    adicional_kwh = models.DecimalField("adicional (R$/kWh)", max_digits=8, decimal_places=5)
    vigencia = models.DateField("vigente desde")
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Bandeira tarifária"
        verbose_name_plural = "Bandeiras tarifárias"
        ordering = ["ordem"]

    def __str__(self):
        return self.nome


class TaxaFinanciamento(models.Model):
    """Taxa mensal por banco e prazo (D22). Mantida pelo gestor."""

    PRAZOS = [12, 24, 36, 48, 60, 72]

    banco = models.CharField(max_length=60)
    prazo_meses = models.PositiveSmallIntegerField("prazo (meses)")
    taxa_mensal = models.DecimalField("taxa ao mês (fração)", max_digits=7, decimal_places=5)
    # TAC do banco (D43): igual em todos os prazos do banco; valor fixo, percentual do valor, ou os dois.
    tac_reais = models.DecimalField("TAC (R$)", max_digits=10, decimal_places=2, default=0)
    tac_percentual = models.DecimalField("TAC (fração do valor)", max_digits=6, decimal_places=5, default=0)
    vigente_desde = models.DateField()

    class Meta:
        verbose_name = "Taxa de financiamento"
        verbose_name_plural = "Taxas de financiamento"
        ordering = ["banco", "prazo_meses"]
        constraints = [
            models.UniqueConstraint(fields=["banco", "prazo_meses"], name="taxa_banco_prazo_unica")
        ]

    def __str__(self):
        return f"{self.banco} {self.prazo_meses}×: {self.taxa_mensal * 100:.2f}% a.m."


class Equipamento(models.Model):
    """Catálogo de referência dos distribuidores (D18, D28). Base da sugestão de módulo e inversor."""

    class Tipo(models.TextChoices):
        MODULO = "modulo", "Módulo"
        INVERSOR = "inversor", "Inversor"
        MICROINVERSOR = "microinversor", "Microinversor"
        ESTRUTURA = "estrutura", "Estrutura"
        CABO = "cabo", "Cabo"
        CONECTOR = "conector", "Conector"
        OUTRO = "outro", "Outro"

    class Funcao(models.TextChoices):
        """Papel do item na montagem automática do kit (D34)."""
        TRILHO = "trilho", "Trilho"
        MINI_TRILHO = "mini_trilho", "Mini trilho (telha metálica)"
        FIXACAO = "fixacao", "Fixação no telhado (gancho, pé em L, suporte)"
        HASTE = "haste", "Haste (fibrocimento)"
        GRAMPO_FINAL = "grampo_final", "Grampo final"
        GRAMPO_INTERMEDIARIO = "grampo_intermediario", "Grampo intermediário"
        ATERRAMENTO = "aterramento", "Aterramento"
        JUNCAO = "juncao", "Junção de trilho"
        SUPORTE_MICRO = "suporte_micro", "Suporte do microinversor"
        CABO_PRETO = "cabo_preto", "Cabo solar preto"
        CABO_VERMELHO = "cabo_vermelho", "Cabo solar vermelho"
        CONECTOR = "conector", "Conector"

    class Fase(models.TextChoices):
        MONO = "mono", "Monofásico (220 V)"
        TRI = "tri", "Trifásico (380 V)"

    class TipoEstrutura(models.TextChoices):
        CERAMICA = "ceramica", "Telha cerâmica"
        FIBROCIMENTO = "fibrocimento", "Fibrocimento"
        METALICA = "metalica", "Telha metálica"
        LAJE = "laje", "Laje"
        SOLO = "solo", "Solo"

    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    distribuidor = models.CharField(max_length=60)
    codigo = models.CharField("código", max_length=60)
    fabricante = models.CharField(max_length=60, blank=True)
    modelo = models.CharField(max_length=120, blank=True)
    descricao = models.CharField("descrição", max_length=255)
    potencia_w = models.PositiveIntegerField("potência (W)", null=True, blank=True)
    fase = models.CharField(max_length=4, choices=Fase.choices, blank=True)
    tensao = models.PositiveSmallIntegerField("tensão (V)", null=True, blank=True)
    tipo_estrutura = models.CharField("tipo de estrutura", max_length=15, choices=TipoEstrutura.choices, blank=True)
    area_m2 = models.DecimalField("área (m²)", max_digits=6, decimal_places=3, null=True, blank=True)
    # Montagem do kit pelo catálogo (D34). Lidos da descrição na importação; o gestor corrige na tela.
    funcao = models.CharField(
        "papel no kit", max_length=25, choices=Funcao.choices, blank=True,
        help_text="Vazio: o item não entra sozinho no kit, só se o vendedor acrescentar.",
    )
    pecas_por_embalagem = models.PositiveSmallIntegerField(
        "peças por embalagem", default=1, help_text='Peças (ou pares) vendidas juntas: "4 Pecas" = 4.',
    )
    mppts = models.PositiveSmallIntegerField("MPPT", null=True, blank=True, help_text="Só inversor string.")
    modulos_por_micro = models.PositiveSmallIntegerField(
        "módulos por microinversor", null=True, blank=True,
    )
    comprimento_mm = models.PositiveSmallIntegerField("comprimento (mm)", null=True, blank=True,
                                                      help_text="Só módulo.")
    largura_mm = models.PositiveSmallIntegerField("largura (mm)", null=True, blank=True, help_text="Só módulo.")
    espessura_mm = models.PositiveSmallIntegerField(
        "espessura da moldura (mm)", null=True, blank=True,
        help_text="Módulo: espessura da moldura. Grampo final: moldura que ele prende.",
    )
    preco_referencia = models.DecimalField(
        "preço de referência (R$)", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Preço unitário no site do distribuidor, sem frete. Só referência (D28).",
    )
    preco_em = models.DateField("preço consultado em", null=True, blank=True)
    foto = models.FileField(upload_to="catalogo/fotos/", blank=True)
    datasheet = models.FileField(upload_to="catalogo/datasheets/", blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Equipamento"
        verbose_name_plural = "Equipamentos"
        ordering = ["tipo", "potencia_w", "descricao"]
        constraints = [
            models.UniqueConstraint(fields=["distribuidor", "codigo"], name="equipamento_distribuidor_codigo_unico")
        ]

    def __str__(self):
        return f"{self.descricao} ({self.distribuidor})"

    @property
    def rs_por_wp(self):
        if self.preco_referencia and self.potencia_w:
            return self.preco_referencia / self.potencia_w
        return None


class Cotacao(models.Model):
    """Memória de cotações (D18): o kit inteiro de um distribuidor, com frete."""

    distribuidor = models.CharField(max_length=60)
    numero = models.CharField("número", max_length=60, blank=True)
    data = models.DateField()
    validade = models.DateField("válida até", null=True, blank=True)
    arquivo = models.FileField("PDF da cotação", upload_to="cotacoes/", blank=True)
    kwp = models.DecimalField("kWp do kit", max_digits=8, decimal_places=3)
    total_produtos = models.DecimalField("total dos produtos (R$)", max_digits=12, decimal_places=2)
    frete = models.DecimalField("frete (R$)", max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField("total (R$)", max_digits=12, decimal_places=2)
    proposta = models.ForeignKey(
        Proposta, on_delete=models.SET_NULL, null=True, blank=True, related_name="cotacoes",
    )
    observacao = models.TextField("observação", blank=True)

    class Meta:
        verbose_name = "Cotação"
        verbose_name_plural = "Cotações"
        ordering = ["-data", "-pk"]

    def __str__(self):
        return f"{self.distribuidor} {self.numero} ({self.data:%d/%m/%Y})"

    @property
    def rs_por_wp(self):
        return self.total / (self.kwp * 1000)

    @property
    def idade_dias(self):
        return (date.today() - self.data).days

    @classmethod
    def referencias(cls):
        """A cotação mais recente de cada distribuidor, a do menor R$/Wp primeiro."""
        mais_recentes = {}
        for cotacao in cls.objects.order_by("-data", "-pk"):
            mais_recentes.setdefault(cotacao.distribuidor.lower(), cotacao)
        return sorted(mais_recentes.values(), key=lambda c: c.rs_por_wp)


class ItemCotado(models.Model):
    cotacao = models.ForeignKey(Cotacao, on_delete=models.CASCADE, related_name="itens")
    equipamento = models.ForeignKey(Equipamento, on_delete=models.SET_NULL, null=True, blank=True)
    descricao = models.CharField("descrição", max_length=255)
    codigo = models.CharField("código", max_length=60, blank=True)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    unidade = models.CharField(max_length=10, default="un")

    class Meta:
        verbose_name = "Item cotado"
        verbose_name_plural = "Itens cotados"
        ordering = ["pk"]

    def __str__(self):
        return f"{self.quantidade:g} {self.unidade} {self.descricao}"
