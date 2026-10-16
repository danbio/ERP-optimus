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


class IrradiacaoMunicipio(models.Model):
    municipio = models.CharField(max_length=120)
    uf = models.CharField(max_length=2)
    valores = models.JSONField(help_text="12 valores mensais, kWh/m²·dia, plano horizontal.")
    fonte = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Irradiação do município"
        verbose_name_plural = "Irradiação por município"
        constraints = [
            models.UniqueConstraint(fields=["municipio", "uf"], name="irradiacao_municipio_uf_unico")
        ]
        ordering = ["municipio"]

    def __str__(self):
        return f"{self.municipio}/{self.uf}"


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
