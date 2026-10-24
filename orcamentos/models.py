from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from clientes.models import Cliente


def parcelamento_padrao():
    """Prazos do PDF (H10, D44). Acréscimo vazio até o gestor informar: o prazo não aparece."""
    return [{"parcelas": n, "acrescimo": None} for n in (3, 6, 12, 21)]


class ParametrosOrcamento(models.Model):
    """Registro único com os padrões do módulo (D13/D14). Editado pelo admin."""

    uf_destino = models.CharField(
        "UF de destino na tabela Intelbras", max_length=2, default="TO",
        help_text="A importação da tabela usa só as linhas desta UF.",
    )
    markup_padrao = models.DecimalField(
        "markup padrão (%)", max_digits=6, decimal_places=2, default=Decimal("30"),
        help_text="Usado quando o segmento não tem markup próprio. 30% ≈ PSCF.",
    )
    validade_padrao_dias = models.PositiveIntegerField("validade padrão (dias)", default=7)
    forma_pagamento_padrao = models.CharField("forma de pagamento padrão", max_length=255, blank=True)
    prazo_padrao = models.CharField("prazo de execução padrão", max_length=255, blank=True)
    garantia_padrao = models.TextField("garantia padrão", blank=True)
    observacoes_padrao = models.TextField("observações padrão", blank=True)
    parcelamento = models.JSONField(
        "parcelamento", default=parcelamento_padrao,
        help_text='Lista de {"parcelas": 3, "acrescimo": 0.05}; acréscimo em fração do total.',
    )

    class Meta:
        verbose_name = "Parâmetros de orçamento"
        verbose_name_plural = "Parâmetros de orçamento"

    def __str__(self):
        return "Parâmetros de orçamento"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obter(cls):
        """O registro único de parâmetros, criado na primeira vez."""
        return cls.objects.get_or_create(pk=1)[0]


class MarkupSegmento(models.Model):
    segmento = models.CharField(max_length=120, unique=True, help_text="Nome exato do segmento na tabela Intelbras.")
    markup = models.DecimalField("markup (%)", max_digits=6, decimal_places=2)

    class Meta:
        verbose_name = "Markup por segmento"
        verbose_name_plural = "Markups por segmento"
        ordering = ["segmento"]

    def __str__(self):
        return f"{self.segmento}: {self.markup}%"


class TabelaPreco(models.Model):
    """Uma importação da tabela Intelbras. Guarda o arquivo original e o resumo das mudanças."""

    referencia = models.CharField(max_length=60, help_text='Ex.: "OUTUBRO/2026".')
    arquivo = models.FileField(upload_to="tabelas/")
    uf_destino = models.CharField(max_length=2)
    importada_em = models.DateTimeField(default=timezone.now)
    resumo = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Tabela de preços importada"
        verbose_name_plural = "Tabelas de preços importadas"
        ordering = ["-importada_em"]

    def __str__(self):
        return f"{self.referencia} ({self.importada_em:%d/%m/%Y %H:%M})"


class Produto(models.Model):
    """Produto Intelbras, espelho da última tabela importada. Custo = PSD (D13)."""

    codigo = models.CharField(max_length=20, unique=True)
    descricao = models.CharField(max_length=500)
    resumo = models.CharField(max_length=255, blank=True)
    bu = models.CharField("BU", max_length=60, blank=True)
    segmento = models.CharField(max_length=120, blank=True, db_index=True)
    familia = models.CharField(max_length=120, blank=True)
    uf_origem = models.CharField(max_length=2, blank=True)
    ipi = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    icms = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    psd = models.DecimalField("PSD (custo)", max_digits=12, decimal_places=2, default=0)
    pscf = models.DecimalField("PSCF", max_digits=12, decimal_places=2, default=0)
    qtd_multipla = models.PositiveIntegerField("qtd. múltipla", default=1)
    preco_referencia = models.CharField(max_length=40, blank=True)
    observacoes = models.CharField(max_length=255, blank=True)
    ncm = models.CharField("NCM", max_length=20, blank=True)
    ativo = models.BooleanField(default=True, help_text="Falso quando o produto saiu da tabela.")
    em_encerramento = models.BooleanField(default=False)
    substituto = models.CharField(max_length=255, blank=True)
    tabela = models.ForeignKey(TabelaPreco, on_delete=models.SET_NULL, null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produto Intelbras"
        verbose_name_plural = "Produtos Intelbras"
        ordering = ["descricao"]

    def __str__(self):
        return f"{self.codigo} — {self.resumo or self.descricao}"

    @property
    def nome(self):
        """Nome curto do produto (o resumo da tabela, ou a descrição)."""
        return self.resumo or self.descricao


class ItemProprio(models.Model):
    """Material de outra marca ou serviço da Optimus, reutilizável nos orçamentos."""

    class Tipo(models.TextChoices):
        MATERIAL = "material", "Material"
        SERVICO = "servico", "Serviço"

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    descricao = models.CharField(max_length=255)
    unidade = models.CharField(max_length=10, default="un")
    custo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    preco = models.DecimalField("preço de venda", max_digits=12, decimal_places=2)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Item próprio (material/serviço)"
        verbose_name_plural = "Itens próprios (materiais/serviços)"
        ordering = ["tipo", "descricao"]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.descricao}"


class Orcamento(models.Model):
    """Só `rascunho` é editável. "Revisar" um emitido cria nova versão (D07/D14)."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        EMITIDO = "emitido", "Emitido"
        ACEITO = "aceito", "Aceito"
        PERDIDO = "perdido", "Perdido"

    numero = models.CharField(max_length=30)
    versao = models.PositiveIntegerField(default=1)
    origem = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="revisoes")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="orcamentos")
    titulo = models.CharField("título", max_length=200, help_text='Ex.: "Sistema de CFTV com 8 câmeras".')
    local_instalacao = models.CharField("local de instalação", max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RASCUNHO)
    emissao = models.DateField(null=True, blank=True)
    validade_dias = models.PositiveIntegerField("validade (dias)", default=7)
    forma_pagamento = models.CharField("forma de pagamento", max_length=255, blank=True)
    mostrar_precos = models.BooleanField("Mostrar o preço de cada item no PDF", default=True)
    mostrar_parcelamento = models.BooleanField("Mostrar o parcelamento no PDF", default=True)
    prazo_execucao = models.CharField("prazo de execução", max_length=255, blank=True)
    garantia = models.TextField(blank=True)
    observacoes = models.TextField("observações", blank=True)
    desconto_pct = models.DecimalField("desconto (%)", max_digits=5, decimal_places=2, default=0)
    projeto_registrado = models.BooleanField("projeto registrado na Intelbras", default=False)
    numero_registro = models.CharField("nº do registro de projeto", max_length=60, blank=True)
    tabela_referencia = models.CharField(max_length=60, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pdf = models.FileField(upload_to="orcamentos/", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    # Acompanhamento (A20, D46)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="vendedor responsável",
    )
    proximo_contato = models.DateField("próximo contato", null=True, blank=True)

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["numero", "versao"], name="orcamento_numero_versao_unico")
        ]

    def __str__(self):
        return f"{self.numero} v{self.versao}"

    @property
    def editavel(self):
        """Só o rascunho pode ser alterado."""
        return self.status == self.Status.RASCUNHO

    @property
    def validade_ate(self):
        """Data final da validade, ou None antes da emissão."""
        if not self.emissao:
            return None
        return self.emissao + timezone.timedelta(days=self.validade_dias)

    @classmethod
    def proximo_numero(cls, ano=None):
        """Próximo número do ano no formato ORC-2026-0001."""
        ano = ano or timezone.localdate().year
        prefixo = f"ORC-{ano}-"
        ultimo = (
            cls.objects.filter(numero__startswith=prefixo)
            .order_by("-numero")
            .values_list("numero", flat=True)
            .first()
        )
        proxima_seq = int(ultimo.rsplit("-", 1)[-1]) + 1 if ultimo else 1
        return f"{prefixo}{proxima_seq:04d}"


class ItemOrcamento(models.Model):
    """Snapshot do item no momento da inclusão: não muda se a tabela mudar."""

    class Tipo(models.TextChoices):
        INTELBRAS = "intelbras", "Equipamento Intelbras"
        MATERIAL = "material", "Material"
        SERVICO = "servico", "Serviço"

    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name="itens")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True, blank=True)
    codigo = models.CharField(max_length=20, blank=True)
    descricao = models.CharField(max_length=500)
    unidade = models.CharField(max_length=10, default="un")
    quantidade = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    preco_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pscf_unitario = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    qtd_multipla = models.PositiveIntegerField(default=1)
    ativo_na_tabela = models.BooleanField(default=True)
    em_encerramento = models.BooleanField(default=False)
    substituto = models.CharField(max_length=255, blank=True)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Item do orçamento"
        verbose_name_plural = "Itens do orçamento"
        ordering = ["ordem", "id"]

    def __str__(self):
        return f"{self.quantidade}x {self.descricao}"

    @property
    def total(self):
        """Quantidade × preço unitário, em R$ com centavos."""
        return (self.quantidade * self.preco_unitario).quantize(Decimal("0.01"))
