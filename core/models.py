from django.db import models


class ConfigEmpresa(models.Model):
    """Registro único com os dados da empresa. Usado no rodapé e capa da proposta."""

    razao_social = models.CharField(max_length=200)
    nome_fantasia = models.CharField(max_length=200, blank=True)
    cnpj = models.CharField(max_length=20)
    endereco = models.CharField(max_length=255)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to="config/", blank=True)
    projetos_entregues = models.PositiveIntegerField(default=0)
    anos_atuacao = models.PositiveIntegerField(default=0)
    texto_sobre = models.TextField(blank=True, help_text='Bloco "Sobre a Optimus".')
    beneficios_padrao = models.TextField(blank=True, help_text="Um benefício por linha.")
    escopo_padrao = models.TextField(blank=True, help_text='Itens do "Escopo incluso", um por linha.')
    etapas_padrao = models.TextField(
        blank=True, help_text="Uma etapa por linha, no formato 'Título | descrição'."
    )
    validade_padrao_dias = models.PositiveIntegerField(default=15)
    premissas_padrao = models.JSONField(default=dict)

    class Meta:
        verbose_name = "Configuração da empresa"
        verbose_name_plural = "Configuração da empresa"

    def __str__(self):
        return self.nome_fantasia or self.razao_social

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obter(cls):
        return cls.objects.first()


class Municipio(models.Model):
    """Município do IBGE, com coordenadas e irradiação (D21, D26)."""

    codigo_ibge = models.PositiveIntegerField("código IBGE", unique=True)
    nome = models.CharField(max_length=120)
    uf = models.CharField("UF", max_length=2)
    latitude = models.FloatField()
    longitude = models.FloatField()
    irradiacao = models.JSONField(
        "irradiação", null=True, blank=True, help_text="12 valores mensais, kWh/m²·dia, plano horizontal."
    )
    fonte_irradiacao = models.CharField("fonte da irradiação", max_length=255, blank=True)
    atualizado_em = models.DateField("irradiação atualizada em", null=True, blank=True)

    class Meta:
        verbose_name = "Município"
        verbose_name_plural = "Municípios"
        ordering = ["uf", "nome"]

    def __str__(self):
        return f"{self.nome}/{self.uf}"
