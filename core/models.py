from decimal import Decimal

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
    ufs_atendidas = models.CharField(
        "estados atendidos", max_length=60, default="TO", help_text='Siglas separadas por vírgula: "TO, GO".',
    )
    # IOF do financiamento (D43, Decreto 6.306/2007): frações. O gestor confere se a Receita mudar.
    iof_adicional = models.DecimalField("IOF adicional (fração)", max_digits=7, decimal_places=6, default=Decimal("0.0038"))
    iof_diario_pf = models.DecimalField("IOF diário pessoa física (fração)", max_digits=8, decimal_places=7,
                                        default=Decimal("0.000082"))
    iof_diario_pj = models.DecimalField("IOF diário pessoa jurídica (fração)", max_digits=8, decimal_places=7,
                                        default=Decimal("0.000041"))
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

    # Travas de digitação e de emissão (D33, plano de correções A01, A02, A06)
    conta_alta = models.DecimalField(
        "conta acima de (R$) pede confirmação", max_digits=10, decimal_places=2, default=5000,
    )
    consumo_alto = models.PositiveIntegerField("consumo acima de (kWh/mês) pede confirmação", default=3000)
    tolerancia_tarifa_fatura = models.DecimalField(
        "diferença aceita entre o R$/kWh da fatura e a tarifa (fração)", max_digits=4, decimal_places=2, default=0.30,
    )
    tolerancia_kwp_cotacao = models.DecimalField(
        "diferença aceita entre o kWp da cotação e o do sistema (fração)", max_digits=4, decimal_places=2,
        default=0.05,
    )
    limite_microgeracao_kwp = models.DecimalField(
        "limite da microgeração (kWp)", max_digits=6, decimal_places=2, default=75,
    )
    # Ano de conexão do rascunho = hoje + prazo de homologação (A17, D36).
    prazo_homologacao_dias = models.PositiveSmallIntegerField("prazo até a conexão (dias)", default=60)
    # Painel da página inicial (D46)
    dias_aviso_vencimento = models.PositiveSmallIntegerField("avisar proposta vencendo em (dias)", default=3)
    dias_sem_retorno = models.PositiveSmallIntegerField("proposta parada após (dias sem contato)", default=7)

    # Kit montado pelo catálogo (D34)
    distribuidor_kit = models.CharField("distribuidor do kit", max_length=60, default="Belenus")
    frete_kit = models.DecimalField("frete sobre o kit (fração)", max_digits=5, decimal_places=4, default=0.07)
    dias_catalogo_velho = models.PositiveIntegerField("dias para o preço do catálogo ficar velho", default=30)
    metros_cabo_por_string = models.PositiveSmallIntegerField("cabo solar por string, de cada cor (m)", default=15)
    pares_conector_por_string = models.PositiveSmallIntegerField("pares de conector por string", default=2)
    pares_conector_por_micro = models.PositiveSmallIntegerField("pares de conector por microinversor", default=4)
    modulos_por_string_min = models.PositiveSmallIntegerField("mínimo de módulos por string", default=4)
    modulos_por_string_max = models.PositiveSmallIntegerField("máximo de módulos por string", default=12)
    espessura_modulo_padrao = models.PositiveSmallIntegerField(
        "espessura da moldura do módulo sem cadastro (mm)", default=30,
    )

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

    def ufs(self):
        return [uf.strip().upper() for uf in self.ufs_atendidas.split(",") if uf.strip()]


class Distribuidora(models.Model):
    """Distribuidora de energia (D47). As tarifas e os municípios apontam para ela pelo nome."""

    nome = models.CharField(max_length=60, unique=True, help_text='Como aparece nas tarifas: "Energisa TO".')
    sigla_aneel = models.CharField(
        "sigla na ANEEL", max_length=20, blank=True,
        help_text="Campo SigAgente do conjunto de tarifas da ANEEL. Vazio: as tarifas são digitadas.",
    )
    uf = models.CharField("UF", max_length=2)

    class Meta:
        verbose_name = "Distribuidora"
        verbose_name_plural = "Distribuidoras"
        ordering = ["uf", "nome"]

    def __str__(self):
        return self.nome


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
    # Iluminação pública (D32): a lei municipal fixa o valor por faixa de consumo, em unidade fiscal.
    valor_unidade_fiscal = models.DecimalField(
        "valor da unidade fiscal (R$)", max_digits=10, decimal_places=4, null=True, blank=True,
        help_text="Ex.: UFIRG de Gurupi. Muda todo ano.",
    )
    lei_iluminacao = models.CharField("lei da iluminação pública", max_length=255, blank=True)
    distribuidora = models.ForeignKey(
        Distribuidora, on_delete=models.PROTECT, null=True, blank=True, related_name="municipios",
    )

    class Meta:
        verbose_name = "Município"
        verbose_name_plural = "Municípios"
        ordering = ["uf", "nome"]

    def __str__(self):
        return f"{self.nome}/{self.uf}"

    @classmethod
    def atendidos(cls):
        """Municípios dos estados em que a Optimus vende (D47)."""
        config = ConfigEmpresa.obter()
        return cls.objects.filter(uf__in=config.ufs() if config else [])

    @property
    def media_irradiacao(self):
        return sum(self.irradiacao) / 12 if self.irradiacao else None


class FaixaIluminacao(models.Model):
    """Uma faixa da tabela de iluminação pública (CIP/COSIP) do município (D32)."""

    class Classe(models.TextChoices):
        RESIDENCIAL = "residencial", "Residencial"
        NAO_RESIDENCIAL = "nao_residencial", "Não residencial"

    municipio = models.ForeignKey(Municipio, on_delete=models.CASCADE, related_name="faixas_iluminacao")
    classe = models.CharField(max_length=20, choices=Classe.choices)
    ate_kwh = models.PositiveIntegerField("até (kWh)", null=True, blank=True, help_text="Vazio = sem limite.")
    unidades = models.DecimalField("valor (unidades fiscais)", max_digits=8, decimal_places=2)

    class Meta:
        verbose_name = "Faixa de iluminação pública"
        verbose_name_plural = "Faixas de iluminação pública"
        ordering = ["municipio", "classe", models.F("ate_kwh").asc(nulls_last=True)]

    def __str__(self):
        limite = f"até {self.ate_kwh} kWh" if self.ate_kwh is not None else "acima"
        return f"{self.municipio} · {self.get_classe_display()} · {limite}"
