"""Formulários da tela de Configurações (fatia v2.2) e campos de reais e percentual (D24)."""

from datetime import date
from decimal import Decimal

from django import forms

from propostas.models import Bandeira, TarifaVigente, TaxaFinanciamento

from .models import ConfigEmpresa
from .validacoes import formatar_percentual, formatar_reais, limpar_percentual, limpar_reais


class CampoReais(forms.CharField):
    """Texto "1.234,56" na tela, Decimal no servidor."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget.attrs.update({"inputmode": "decimal", "data-mascara": "reais"})

    def prepare_value(self, value):
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            return value
        return formatar_reais(value)

    def clean(self, value):
        value = super().clean(value)
        if value in ("", None):
            return None
        try:
            return limpar_reais(value)
        except ValueError as erro:
            raise forms.ValidationError(str(erro))


class CampoPercentual(forms.CharField):
    """Texto "18,5" (em %) na tela, fração 0.185 no servidor."""

    def __init__(self, *args, maximo=100.0, casas=2, **kwargs):
        self.maximo = maximo
        self.casas = casas
        super().__init__(*args, **kwargs)
        self.widget.attrs.update({"inputmode": "decimal", "class": "campo-percentual"})

    def prepare_value(self, value):
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            return value
        return formatar_percentual(float(value), self.casas)

    def clean(self, value):
        value = super().clean(value)
        if value in ("", None):
            return None
        try:
            return limpar_percentual(value, maximo=self.maximo)
        except ValueError as erro:
            raise forms.ValidationError(str(erro))


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = ConfigEmpresa
        fields = [
            "razao_social", "nome_fantasia", "cnpj", "endereco", "telefone", "email", "logo",
            "projetos_entregues", "anos_atuacao", "validade_padrao_dias",
            "texto_sobre", "beneficios_padrao", "escopo_padrao", "etapas_padrao", "aviso_estimativa",
        ]
        labels = {
            "razao_social": "Razão social", "nome_fantasia": "Nome fantasia", "cnpj": "CNPJ",
            "endereco": "Endereço", "projetos_entregues": "Projetos entregues", "anos_atuacao": "Anos de atuação",
            "validade_padrao_dias": "Validade da proposta (dias)", "texto_sobre": 'Texto "Sobre a Optimus"',
            "beneficios_padrao": "Benefícios (um por linha)", "escopo_padrao": "Escopo incluso (um por linha)",
            "etapas_padrao": "Etapas (Título | descrição, uma por linha)",
            "aviso_estimativa": "Aviso da proposta sem fatura (estimativa)",
        }
        widgets = {campo: forms.Textarea(attrs={"rows": 4}) for campo in (
            "texto_sobre", "beneficios_padrao", "escopo_padrao", "etapas_padrao",
        )} | {"aviso_estimativa": forms.Textarea(attrs={"rows": 2})}


# Premissas técnicas: chave em premissas_padrao → rótulo. Percentuais guardados em fração.
PREMISSAS_PERCENTUAIS = [
    ("perdas", "Perdas do sistema (%)"),
    ("perda_clipping", "Perda por clipping (%)"),
    ("simultaneidade", "Simultaneidade padrão (%)"),
    ("reajuste_anual", "Reajuste anual da tarifa (%)"),
    ("degradacao_ano1", "Degradação no 1º ano (%)"),
    ("degradacao_anual", "Degradação anual, a partir do 2º ano (%)"),
]

ORIENTACOES = [
    ("norte", "Norte"),
    ("nordeste_noroeste", "Nordeste ou noroeste"),
    ("leste_oeste", "Leste ou oeste"),
    ("sul", "Sul"),
]


class PremissasForm(forms.Form):
    """Premissas técnicas, fatores de orientação e mão de obra. Só o gestor altera (D19)."""

    prazo_homologacao_dias = forms.IntegerField(
        label="Prazo da venda até a conexão (dias)", min_value=0, max_value=365,
        help_text="Define o ano de conexão de cada proposta (regra do Fio B).",
    )
    horizonte_anos = forms.IntegerField(label="Horizonte da análise (anos)", min_value=1, max_value=40)
    razao_cc_ca_max = forms.DecimalField(
        label="Sobrecarga máxima do inversor (CC/CA)", min_value=1, max_value=2, decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}), localize=True,
    )
    sobrecarga_min = forms.DecimalField(
        label="Avisar inversor grande abaixo de (CC/CA)", min_value=Decimal("0.3"), max_value=1, decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}), localize=True,
    )
    cobertura_min = CampoPercentual(label="Avisar cobertura abaixo de (%)")
    cobertura_max = CampoPercentual(label="Avisar cobertura acima de (%)", maximo=300)

    mo_por_kwp = CampoReais(label="Mão de obra por kWp (R$)")
    mo_por_kwp_solo = CampoReais(label="Mão de obra por kWp em solo (R$)")
    mo_minima = CampoReais(label="Mão de obra mínima (R$)")
    dias_preco_velho = forms.IntegerField(label="Cotação do kit fica velha após (dias)", min_value=1, max_value=365)

    # Kit montado pelo catálogo (D34)
    distribuidor_kit = forms.CharField(label="Distribuidor do kit", max_length=60)
    frete_kit = CampoPercentual(label="Frete sobre os produtos do kit (%)", maximo=50)
    dias_catalogo_velho = forms.IntegerField(
        label="Preço do catálogo fica velho após (dias)", min_value=1, max_value=365)
    metros_cabo_por_string = forms.IntegerField(
        label="Cabo solar por string, de cada cor (m)", min_value=0, max_value=200)
    pares_conector_por_string = forms.IntegerField(
        label="Pares de conector por string", min_value=0, max_value=20)
    pares_conector_por_micro = forms.IntegerField(
        label="Pares de conector por microinversor", min_value=0, max_value=20)
    modulos_por_string_min = forms.IntegerField(label="Mínimo de módulos por string", min_value=1, max_value=40)
    modulos_por_string_max = forms.IntegerField(label="Máximo de módulos por string", min_value=1, max_value=40)
    espessura_modulo_padrao = forms.IntegerField(
        label="Moldura do módulo sem cadastro (mm)", min_value=20, max_value=60,
        help_text="Escolhe o grampo final quando o módulo não tem a espessura cadastrada.")

    # Travas da proposta (A06, A01, A02): acima disso o sistema pede confirmação ou avisa.
    conta_alta = CampoReais(label="Conta alta: pedir confirmação acima de (R$)")
    consumo_alto = forms.IntegerField(label="Consumo alto: pedir confirmação acima de (kWh/mês)", min_value=1)
    tolerancia_tarifa_fatura = CampoPercentual(label="R$/kWh da fatura: diferença aceita da tarifa (%)")
    tolerancia_kwp_cotacao = CampoPercentual(label="kWp da cotação: diferença aceita do sistema (%)", maximo=50)
    limite_microgeracao_kwp = forms.DecimalField(
        label="Avisar acima de (kWp)", min_value=1, decimal_places=2, localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )

    CAMPOS_DA_CONFIG = (
        "mo_por_kwp", "mo_por_kwp_solo", "mo_minima", "dias_preco_velho", "prazo_homologacao_dias",
        "conta_alta", "consumo_alto", "tolerancia_tarifa_fatura", "tolerancia_kwp_cotacao", "limite_microgeracao_kwp",
        "distribuidor_kit", "frete_kit", "dias_catalogo_velho", "metros_cabo_por_string", "pares_conector_por_string", "pares_conector_por_micro",
        "modulos_por_string_min", "modulos_por_string_max", "espessura_modulo_padrao",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for chave, rotulo in PREMISSAS_PERCENTUAIS:
            self.fields[chave] = CampoPercentual(label=rotulo)
        for chave, rotulo in ORIENTACOES:
            self.fields[f"orientacao_{chave}"] = CampoPercentual(label=rotulo, maximo=100)

    def clean(self):
        dados = super().clean()
        minimo, maximo = dados.get("modulos_por_string_min"), dados.get("modulos_por_string_max")
        if minimo and maximo and minimo > maximo:
            self.add_error("modulos_por_string_max", "O máximo precisa ser maior ou igual ao mínimo.")
        return dados

    @classmethod
    def da_config(cls, config):
        premissas = config.premissas_padrao
        inicial = {chave: premissas.get(chave) for chave, _ in PREMISSAS_PERCENTUAIS}
        inicial |= {chave: premissas.get(chave) for chave in (
            "horizonte_anos", "razao_cc_ca_max", "sobrecarga_min", "cobertura_min", "cobertura_max",
        )}
        inicial |= {f"orientacao_{chave}": config.fatores_orientacao.get(chave) for chave, _ in ORIENTACOES}
        inicial |= {campo: getattr(config, campo) for campo in cls.CAMPOS_DA_CONFIG}
        return cls(initial=inicial)

    def gravar(self, config):
        dados = self.cleaned_data
        premissas = dict(config.premissas_padrao)
        for chave, _ in PREMISSAS_PERCENTUAIS:
            premissas[chave] = dados[chave]
        premissas["horizonte_anos"] = dados["horizonte_anos"]
        premissas["razao_cc_ca_max"] = float(dados["razao_cc_ca_max"])
        premissas["sobrecarga_min"] = float(dados["sobrecarga_min"])
        premissas["cobertura_min"] = dados["cobertura_min"]
        premissas["cobertura_max"] = dados["cobertura_max"]
        premissas["cobrar_disponibilidade"] = False  # a disponibilidade não entra na economia (D33)
        config.premissas_padrao = premissas
        config.fatores_orientacao = {chave: dados[f"orientacao_{chave}"] for chave, _ in ORIENTACOES}
        for campo in self.CAMPOS_DA_CONFIG:
            setattr(config, campo, dados[campo])
        config.save()


class PerfilForm(forms.Form):
    nome = forms.CharField(label="Perfil", required=False, max_length=80)
    simultaneidade = CampoPercentual(label="Simultaneidade (%)", required=False)

    def clean(self):
        dados = super().clean()
        if dados.get("nome") and dados.get("simultaneidade") is None:
            self.add_error("simultaneidade", "Informe a simultaneidade deste perfil.")
        return dados


PerfisFormSet = forms.formset_factory(PerfilForm, extra=1)


class TarifaForm(forms.ModelForm):
    """Tributos e Fio B de uma tarifa: o que a ANEEL não publica e o gestor digita (D21)."""

    aliquota_tributos = CampoPercentual(label="Tributos (%)", maximo=60)
    fiob_kwh = forms.DecimalField(
        label="Fio B (R$/kWh)", required=False, min_value=0, decimal_places=6, localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    fiob_conferido = forms.BooleanField(label="Fio B conferido nesta vigência", required=False)

    class Meta:
        model = TarifaVigente
        fields = ["aliquota_tributos", "fiob_kwh"]

    def clean_aliquota_tributos(self):
        return Decimal(str(self.cleaned_data["aliquota_tributos"]))

    def save(self, commit=True):
        tarifa = super().save(commit=False)
        if "fiob_kwh" in self.changed_data or self.cleaned_data.get("fiob_conferido"):
            tarifa.fiob_conferido_em = date.today()
        if commit:
            tarifa.save()
        return tarifa


BandeirasFormSet = forms.modelformset_factory(
    Bandeira,
    fields=["adicional_kwh", "vigencia"],
    extra=0,
    field_classes={"adicional_kwh": forms.DecimalField},
    widgets={"adicional_kwh": forms.TextInput(attrs={"inputmode": "decimal"}), "vigencia": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")},
    localized_fields=["adicional_kwh"],
)


class TaxasForm(forms.Form):
    """Grade banco × prazo (D22). Uma linha por banco e uma linha vazia para incluir outro."""

    def __init__(self, *args, taxas=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.taxas_atuais = {(t.banco, t.prazo_meses): t for t in taxas}
        bancos = sorted({t.banco for t in taxas})
        self.linhas = []
        for indice, banco in enumerate(bancos + [""]):
            self.fields[f"banco_{indice}"] = forms.CharField(
                label="Banco", required=False, max_length=60, initial=banco,
            )
            campos = []
            for prazo in TaxaFinanciamento.PRAZOS:
                nome = f"taxa_{indice}_{prazo}"
                atual = self.taxas_atuais.get((banco, prazo))
                self.fields[nome] = CampoPercentual(
                    label=f"{prazo}×", required=False, maximo=10, casas=3,
                    initial=float(atual.taxa_mensal) if atual else None,
                )
                campos.append(nome)
            self.linhas.append((f"banco_{indice}", campos))

    def linhas_renderizadas(self):
        return [(self[banco], [self[c] for c in campos]) for banco, campos in self.linhas]

    def clean(self):
        dados = super().clean()
        vistos = set()
        for banco, campos in self.linhas:
            nome = (dados.get(banco) or "").strip()
            tem_taxa = any(dados.get(c) is not None for c in campos)
            if tem_taxa and not nome:
                self.add_error(banco, "Informe o nome do banco.")
            if nome.lower() in vistos:
                self.add_error(banco, "Banco repetido.")
            vistos.add(nome.lower())
        return dados

    def gravar(self):
        dados = self.cleaned_data
        novas = {}
        for banco, campos in self.linhas:
            nome = (dados.get(banco) or "").strip()
            if not nome:
                continue
            for campo, prazo in zip(campos, TaxaFinanciamento.PRAZOS):
                if dados.get(campo) is not None:
                    novas[(nome, prazo)] = Decimal(str(dados[campo]))
        for chave, taxa in self.taxas_atuais.items():
            if chave not in novas:
                taxa.delete()
        for (banco, prazo), valor in novas.items():
            atual = self.taxas_atuais.get((banco, prazo))
            if atual and atual.taxa_mensal == valor:
                continue
            TaxaFinanciamento.objects.update_or_create(
                banco=banco, prazo_meses=prazo, defaults={"taxa_mensal": valor, "vigente_desde": date.today()},
            )
