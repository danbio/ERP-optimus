from django.db import models

AVISO_ESTIMATIVA_PADRAO = (
    "Valores estimados a partir de dados informados pelo cliente, sem análise da fatura. "
    "Sujeitos a discrepâncias com os dados reais."
)


# Valores iniciais aprovados no protótipo (21/10/2026); o gestor ajusta em Configurações.
def fatores_orientacao_padrao():
    return {"norte": 1.0, "nordeste_noroeste": 0.97, "leste_oeste": 0.90, "sul": 0.80}


def perfis_simultaneidade_padrao():
    return [
        {"nome": "Mais à noite (residencial)", "simultaneidade": 0.35},
        {"nome": "Dia e noite (rural)", "simultaneidade": 0.50},
        {"nome": "Mais de dia (comércio)", "simultaneidade": 0.65},
    ]


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

    # Proposta v2 (D18, D19, D20, D23)
    mo_por_kwp = models.DecimalField("mão de obra por kWp (R$)", max_digits=10, decimal_places=2, default=500)
    mo_por_kwp_solo = models.DecimalField(
        "mão de obra por kWp em solo (R$)", max_digits=10, decimal_places=2, default=700
    )
    mo_minima = models.DecimalField("mão de obra mínima (R$)", max_digits=10, decimal_places=2, default=4500)
    fatores_orientacao = models.JSONField("fatores de orientação", default=fatores_orientacao_padrao)
    perfis_simultaneidade = models.JSONField("perfis de simultaneidade", default=perfis_simultaneidade_padrao)
    dias_preco_velho = models.PositiveIntegerField("dias para o preço do kit ficar velho", default=15)
    aviso_estimativa = models.TextField("aviso da estimativa", default=AVISO_ESTIMATIVA_PADRAO)

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

    @property
    def media_irradiacao(self):
        return sum(self.irradiacao) / 12 if self.irradiacao else None
