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

    ano_conexao = forms.IntegerField(label="Ano de conexão", min_value=2023, max_value=2100)
    horizonte_anos = forms.IntegerField(label="Horizonte da análise (anos)", min_value=1, max_value=40)
    razao_cc_ca_max = forms.DecimalField(
        label="Sobrecarga máxima do inversor (CC/CA)", min_value=1, max_value=2, decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}), localize=True,
    )
    cobrar_disponibilidade = forms.BooleanField(label="Cobrar custo de disponibilidade", required=False)

    mo_por_kwp = CampoReais(label="Mão de obra por kWp (R$)")
    mo_por_kwp_solo = CampoReais(label="Mão de obra por kWp em solo (R$)")
    mo_minima = CampoReais(label="Mão de obra mínima (R$)")
    dias_preco_velho = forms.IntegerField(label="Preço do kit fica velho após (dias)", min_value=1, max_value=365)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for chave, rotulo in PREMISSAS_PERCENTUAIS:
            self.fields[chave] = CampoPercentual(label=rotulo)
        for chave, rotulo in ORIENTACOES:
            self.fields[f"orientacao_{chave}"] = CampoPercentual(label=rotulo, maximo=100)

    @classmethod
    def da_config(cls, config):
        premissas = config.premissas_padrao
        inicial = {chave: premissas.get(chave) for chave, _ in PREMISSAS_PERCENTUAIS}
        inicial |= {chave: premissas.get(chave) for chave in (
            "ano_conexao", "horizonte_anos", "razao_cc_ca_max", "cobrar_disponibilidade",
        )}
        inicial |= {f"orientacao_{chave}": config.fatores_orientacao.get(chave) for chave, _ in ORIENTACOES}
        inicial |= {
            "mo_por_kwp": config.mo_por_kwp, "mo_por_kwp_solo": config.mo_por_kwp_solo,
            "mo_minima": config.mo_minima, "dias_preco_velho": config.dias_preco_velho,
        }
        return cls(initial=inicial)

    def gravar(self, config):
        dados = self.cleaned_data
        premissas = dict(config.premissas_padrao)
        for chave, _ in PREMISSAS_PERCENTUAIS:
            premissas[chave] = dados[chave]
        premissas["ano_conexao"] = dados["ano_conexao"]
        premissas["horizonte_anos"] = dados["horizonte_anos"]
        premissas["razao_cc_ca_max"] = float(dados["razao_cc_ca_max"])
        premissas["cobrar_disponibilidade"] = dados["cobrar_disponibilidade"]
        config.premissas_padrao = premissas
        config.fatores_orientacao = {chave: dados[f"orientacao_{chave}"] for chave, _ in ORIENTACOES}
        config.mo_por_kwp = dados["mo_por_kwp"]
        config.mo_por_kwp_solo = dados["mo_por_kwp_solo"]
        config.mo_minima = dados["mo_minima"]
        config.dias_preco_velho = dados["dias_preco_velho"]
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
