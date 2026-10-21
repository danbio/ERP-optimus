from django.db import models
from django.utils import timezone

from clientes.models import UnidadeConsumidora


class FaturaReferencia(models.Model):
    uc = models.ForeignKey(UnidadeConsumidora, on_delete=models.CASCADE, related_name="faturas")
    competencia = models.DateField(help_text="Mês/ano de referência da fatura.")
    kwh = models.PositiveIntegerField("consumo (kWh)")
    dias_ciclo = models.PositiveIntegerField("dias do ciclo")
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    tarifa_kwh = models.DecimalField("tarifa com tributos (R$/kWh)", max_digits=10, decimal_places=6)
    valor_distribuicao = models.DecimalField(
        "serviço de distribuição, sem tributos (R$)", max_digits=10, decimal_places=2
    )
    impostos = models.DecimalField(max_digits=10, decimal_places=2)
    tusd_fiob_kwh = models.DecimalField(
        "TUSD Fio B informada (R$/kWh)", max_digits=10, decimal_places=6, null=True, blank=True
    )
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
    """Só `rascunho` é editável. "Revisar" uma emitida cria nova versão em rascunho copiando tudo."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        EMITIDA = "emitida", "Emitida"
        ACEITA = "aceita", "Aceita"
        PERDIDA = "perdida", "Perdida"

    numero = models.CharField(max_length=30, unique=True)
    versao = models.PositiveIntegerField(default=1)
    origem = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="revisoes"
    )
    uc = models.ForeignKey(UnidadeConsumidora, on_delete=models.PROTECT, related_name="propostas")
    fatura = models.ForeignKey(FaturaReferencia, on_delete=models.PROTECT, related_name="propostas")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RASCUNHO)
    emissao = models.DateField(null=True, blank=True)
    validade_dias = models.PositiveIntegerField(default=15)
    investimento = models.DecimalField(max_digits=12, decimal_places=2)
    forma_pagamento = models.CharField(max_length=255, blank=True)
    beneficios = models.TextField(blank=True)
    escopo = models.TextField(blank=True)
    texto_sobre = models.TextField(blank=True)
    premissas = models.JSONField(default=dict, help_text="Snapshot das premissas no momento da emissão.")
    resultados = models.JSONField(default=dict, blank=True, help_text="Snapshot dos resultados calculados.")
    pdf = models.FileField(upload_to="propostas/", blank=True)

    class Meta:
        verbose_name = "Proposta"
        verbose_name_plural = "Propostas"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.numero} v{self.versao}"

    @property
    def cliente(self):
        """O cliente não tem FK própria: é sempre o dono da UC (ver D11)."""
        return self.uc.cliente

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

    @property
    def kwp(self):
        total = sum(
            item.quantidade * (item.potencia_w or 0)
            for item in self.itens_kit.filter(tipo=ItemKit.Tipo.MODULO)
        )
        return total / 1000

    @property
    def kw_ca(self):
        total = sum(
            item.quantidade * (item.potencia_w or 0)
            for item in self.itens_kit.filter(tipo=ItemKit.Tipo.INVERSOR)
        )
        return total / 1000


class ItemKit(models.Model):
    class Tipo(models.TextChoices):
        MODULO = "modulo", "Módulo"
        INVERSOR = "inversor", "Inversor"
        ESTRUTURA = "estrutura", "Estrutura"
        CABEAMENTO = "cabeamento", "Cabeamento"
        OUTRO = "outro", "Outro"

    proposta = models.ForeignKey(Proposta, on_delete=models.CASCADE, related_name="itens_kit")
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    descricao = models.CharField(max_length=255)
    modelo = models.CharField(max_length=120, blank=True)
    quantidade = models.PositiveIntegerField(default=1)
    potencia_w = models.PositiveIntegerField(null=True, blank=True)
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
        """A tarifa mais recente de cada tipo."""
        mais_recentes = {}
        for tarifa in cls.objects.order_by("tipo", "-vigencia_inicio"):
            mais_recentes.setdefault(tarifa.tipo, tarifa)
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
