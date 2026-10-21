from decimal import Decimal

from django import forms

from clientes.forms import MunicipioSelect, _limpar
from clientes.models import UnidadeConsumidora
from core.forms import CampoPercentual, CampoReais
from core.models import Municipio
from core.validacoes import (
    formatar_percentual,
    formatar_reais,
    limpar_cpf_cnpj,
    limpar_nome,
    limpar_percentual,
    limpar_reais,
    limpar_telefone,
)

from .models import Cotacao, Equipamento, FaturaReferencia, ItemCotado, ItemKit, Proposta, TarifaVigente


class FaturaReferenciaForm(forms.ModelForm):
    class Meta:
        model = FaturaReferencia
        fields = [
            "uc", "competencia", "kwh", "dias_ciclo", "valor_total", "tarifa_kwh",
            "valor_distribuicao", "impostos", "tusd_fiob_kwh", "arquivo",
        ]
        widgets = {"competencia": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # O cálculo antigo (fatia 4) usa tarifa, distribuição e impostos da fatura; na v2 eles são opcionais (D29).
        for campo in ("tarifa_kwh", "valor_distribuicao", "impostos"):
            self.fields[campo].required = True


class PropostaForm(forms.ModelForm):
    class Meta:
        model = Proposta
        fields = [
            "uc", "fatura", "investimento", "forma_pagamento", "validade_dias",
            "beneficios", "escopo", "texto_sobre",
        ]
        widgets = {
            "beneficios": forms.Textarea(attrs={"rows": 4}),
            "escopo": forms.Textarea(attrs={"rows": 4}),
            "texto_sobre": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Na v2 estes campos são opcionais; o formulário antigo continua exigindo todos (D29).
        for campo in ("uc", "fatura", "investimento"):
            self.fields[campo].required = True
        self.fields["fatura"].queryset = FaturaReferencia.objects.filter(tarifa_kwh__isnull=False)


class PremissasForm(forms.Form):
    perdas = forms.FloatField(label="Perdas do sistema (fração, ex.: 0,18 = 18%)")
    perda_clipping = forms.FloatField(label="Perda por clipping (fração)")
    ano_conexao = forms.IntegerField(label="Ano de conexão")
    simultaneidade = forms.FloatField(label="Simultaneidade (fração)")
    reajuste_anual = forms.FloatField(label="Reajuste tarifário anual (fração)")
    degradacao_ano1 = forms.FloatField(label="Degradação no 1º ano (fração)")
    degradacao_anual = forms.FloatField(label="Degradação anual, a partir do 2º ano (fração)")
    cobrar_disponibilidade = forms.BooleanField(label="Cobrar disponibilidade", required=False)
    horizonte_anos = forms.IntegerField(label="Horizonte (anos)")
    razao_cc_ca_max = forms.FloatField(label="Razão CC/CA máxima do inversor")


class ItemKitForm(forms.Form):
    tipo = forms.ChoiceField(choices=ItemKit.Tipo.choices)
    descricao = forms.CharField(max_length=255)
    modelo = forms.CharField(max_length=120, required=False)
    quantidade = forms.IntegerField(min_value=1, initial=1)
    potencia_w = forms.IntegerField(required=False, min_value=0, label="Potência (W)")


# ---------- Catálogo solar e memória de cotações (fatia v2.4, D28) ----------

class EquipamentoForm(forms.ModelForm):
    preco_referencia = CampoReais(label="Preço de referência (R$)", required=False)

    class Meta:
        model = Equipamento
        fields = [
            "tipo", "distribuidor", "codigo", "fabricante", "modelo", "descricao", "potencia_w",
            "fase", "tensao", "tipo_estrutura", "area_m2", "preco_referencia", "preco_em",
            "foto", "datasheet", "ativo",
        ]
        labels = {
            "codigo": "Código no distribuidor", "descricao": "Descrição", "potencia_w": "Potência (W)",
            "fase": "Fase (inversor)", "tensao": "Tensão (V)", "tipo_estrutura": "Tipo de estrutura",
            "area_m2": "Área (m²)", "preco_em": "Preço consultado em", "ativo": "Ativo (aparece na sugestão)",
        }
        widgets = {"preco_em": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        localized_fields = ["area_m2"]

    def clean_preco_referencia(self):
        preco = self.cleaned_data["preco_referencia"]
        if preco is not None and preco < 0:
            raise forms.ValidationError("O preço não pode ser negativo.")
        return preco

    def clean(self):
        dados = super().clean()
        if dados.get("tipo") in ("modulo", "inversor", "microinversor") and not dados.get("potencia_w"):
            self.add_error("potencia_w", "Informe a potência: o dimensionamento usa este valor.")
        if dados.get("tipo") == "inversor" and not dados.get("fase"):
            self.add_error("fase", "Informe a fase: a sugestão de inversor filtra pela ligação do cliente.")
        return dados


class CotacaoForm(forms.ModelForm):
    total_produtos = CampoReais(label="Total dos produtos (R$)")
    frete = CampoReais(label="Frete (R$)", required=False)
    total = CampoReais(label="Total da cotação (R$)", required=False)

    class Meta:
        model = Cotacao
        fields = ["distribuidor", "numero", "data", "validade", "kwp", "total_produtos", "frete", "total",
                  "arquivo", "observacao"]
        labels = {"numero": "Número da cotação", "kwp": "kWp do kit", "validade": "Válida até",
                  "observacao": "Observação", "arquivo": "PDF da cotação"}
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "validade": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "kwp": forms.TextInput(attrs={"inputmode": "decimal"}),
            "observacao": forms.Textarea(attrs={"rows": 2}),
        }
        localized_fields = ["kwp"]

    def clean(self):
        dados = super().clean()
        frete = dados.get("frete") or Decimal("0")
        dados["frete"] = frete
        if frete < 0:
            self.add_error("frete", "O frete não pode ser negativo.")
        if dados.get("total_produtos") is not None and dados["total_produtos"] <= 0:
            self.add_error("total_produtos", "O total dos produtos precisa ser maior que zero.")
        if dados.get("total_produtos") is not None and dados.get("total") is None:
            dados["total"] = dados["total_produtos"] + frete  # total em branco: produtos + frete
        if dados.get("total") is not None and dados["total"] <= 0:
            self.add_error("total", "O total precisa ser maior que zero.")
        if dados.get("kwp") is not None and dados["kwp"] <= 0:
            self.add_error("kwp", "O kWp precisa ser maior que zero.")
        return dados


class ItemCotadoForm(forms.ModelForm):
    class Meta:
        model = ItemCotado
        fields = ["codigo", "descricao", "quantidade", "unidade"]
        widgets = {"quantidade": forms.TextInput(attrs={"inputmode": "decimal"})}
        localized_fields = ["quantidade"]

    def clean_quantidade(self):
        quantidade = self.cleaned_data["quantidade"]
        if quantidade is not None and quantidade <= 0:
            raise forms.ValidationError("A quantidade precisa ser maior que zero.")
        return quantidade


ItensCotadosFormSet = forms.inlineformset_factory(
    Cotacao, ItemCotado, form=ItemCotadoForm, extra=3, can_delete=True,
)


# ---------- Proposta v2: os 4 passos (fatia v2.5, D29) ----------

class Passo1Form(forms.Form):
    nome = forms.CharField(label="Nome do cliente", max_length=200)
    telefone = forms.CharField(
        label="Telefone / WhatsApp", widget=forms.TextInput(attrs={"data-mascara": "telefone", "inputmode": "tel"}),
    )
    municipio = MunicipioSelect(
        queryset=Municipio.objects.filter(uf="TO"), label="Município da instalação", empty_label="Escolha o município",
    )
    cpf_cnpj = forms.CharField(
        label="CPF ou CNPJ (opcional agora)", required=False,
        widget=forms.TextInput(attrs={"data-mascara": "cpf_cnpj", "inputmode": "numeric"}),
    )
    ligacao = forms.ChoiceField(label="Ligação", choices=UnidadeConsumidora.Ligacao.choices)
    tipo_tarifa = forms.ModelChoiceField(
        queryset=TarifaVigente.objects.none(), label="Tipo de tarifa", empty_label=None,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_tarifa"].queryset = TarifaVigente.objects.filter(pk__in=[t.pk for t in TarifaVigente.vigentes()])
        self.fields["tipo_tarifa"].label_from_instance = lambda t: t.get_tipo_display()

    def clean_nome(self):
        return _limpar(limpar_nome, self.cleaned_data["nome"])

    def clean_telefone(self):
        return _limpar(limpar_telefone, self.cleaned_data["telefone"])

    def clean_cpf_cnpj(self):
        return _limpar(limpar_cpf_cnpj, self.cleaned_data["cpf_cnpj"])


class Passo2Form(forms.ModelForm):
    conta_informada = CampoReais(label="Valor médio da conta (R$)", required=False)
    iluminacao_publica = CampoReais(label="Iluminação pública na conta (R$, se souber)", required=False)
    folga = CampoPercentual(label="Folga para consumo futuro (%)", required=False)
    perfil_simultaneidade = forms.ChoiceField(label="Quando o cliente usa energia", choices=())

    # Aba "Tenho a fatura": vira proposta confirmada (D29).
    numero_uc = forms.CharField(label="Número da UC (na fatura)", max_length=30, required=False)
    endereco = forms.CharField(label="Endereço da instalação", max_length=255, required=False)
    competencia = forms.DateField(
        label="Mês da fatura", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    fatura_kwh = forms.IntegerField(label="Consumo na fatura (kWh)", min_value=1, required=False)
    dias_ciclo = forms.IntegerField(label="Dias do ciclo", min_value=15, max_value=45, required=False)
    valor_fatura = CampoReais(label="Valor total da fatura (R$)", required=False)
    arquivo_fatura = forms.FileField(label="PDF da fatura", required=False)
    cpf_cnpj = forms.CharField(
        label="CPF ou CNPJ do titular", required=False,
        widget=forms.TextInput(attrs={"data-mascara": "cpf_cnpj", "inputmode": "numeric"}),
    )

    class Meta:
        model = Proposta
        fields = ["origem_consumo", "conta_informada", "iluminacao_publica", "bandeira", "kwh_informado",
                  "folga", "perfil_simultaneidade"]
        labels = {"bandeira": "Bandeira da conta", "kwh_informado": "Consumo médio (kWh/mês)"}
        widgets = {"origem_consumo": forms.RadioSelect, "kwh_informado": forms.TextInput(attrs={"inputmode": "decimal"})}
        localized_fields = ["kwh_informado"]

    # Campos de cada aba de consumo. Os das abas não escolhidas são ignorados (ficam só escondidos na tela).
    CAMPOS_DA_ORIGEM = {
        "rs": ["conta_informada", "iluminacao_publica"],
        "kwh": ["kwh_informado"],
        "fatura": ["numero_uc", "endereco", "competencia", "fatura_kwh", "dias_ciclo", "valor_fatura",
                   "arquivo_fatura", "cpf_cnpj"],
    }

    def __init__(self, *args, perfis=(), **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound:
            origem = self.data.get("origem_consumo")
            self.data = self.data.copy()
            for outra, campos in self.CAMPOS_DA_ORIGEM.items():
                if outra != origem:
                    for campo in campos:
                        self.data.pop(campo, None)
                        if self.files:
                            self.files = self.files.copy()
                            self.files.pop(campo, None)
        self.fields["origem_consumo"].required = True
        self.fields["origem_consumo"].choices = [
            ("rs", "Valor da conta (R$)"), ("kwh", "kWh por mês"), ("fatura", "Tenho a fatura"),
        ]
        self.fields["perfil_simultaneidade"].choices = [
            (p["nome"], f"{p['nome']} ({p['simultaneidade'] * 100:.0f}%)") for p in perfis
        ]
        self.fields["bandeira"].empty_label = None
        fatura = self.instance.fatura
        if fatura and not self.is_bound:
            self.initial |= {
                "numero_uc": fatura.uc.numero_uc, "endereco": fatura.uc.endereco, "competencia": fatura.competencia,
                "fatura_kwh": fatura.kwh, "dias_ciclo": fatura.dias_ciclo, "valor_fatura": fatura.valor_total,
            }
        if self.instance.cliente_id and not self.is_bound:
            self.initial["cpf_cnpj"] = self.instance.cliente.cpf_cnpj_formatado

    def clean_cpf_cnpj(self):
        return _limpar(limpar_cpf_cnpj, self.cleaned_data["cpf_cnpj"])

    def clean_folga(self):
        folga = self.cleaned_data["folga"]
        return None if folga is None else Decimal(str(round(folga, 4)))

    def clean(self):
        dados = super().clean()
        origem = dados.get("origem_consumo")
        obrigatorios = {
            Proposta.OrigemConsumo.CONTA: ["conta_informada"],
            Proposta.OrigemConsumo.KWH: ["kwh_informado"],
            Proposta.OrigemConsumo.FATURA: ["numero_uc", "endereco", "competencia", "fatura_kwh", "dias_ciclo",
                                            "valor_fatura", "cpf_cnpj"],
        }.get(origem, [])
        for campo in obrigatorios:
            if dados.get(campo) in (None, ""):
                self.add_error(campo, "Preencha este campo.")
        if dados.get("kwh_informado") is not None and dados["kwh_informado"] <= 0:
            self.add_error("kwh_informado", "O consumo precisa ser maior que zero.")
        conta, iluminacao = dados.get("conta_informada"), dados.get("iluminacao_publica")
        if conta is not None and conta <= 0:
            self.add_error("conta_informada", "O valor da conta precisa ser maior que zero.")
        elif iluminacao is not None and iluminacao < 0:
            self.add_error("iluminacao_publica", "A iluminação pública não pode ser negativa.")
        elif conta is not None and iluminacao is not None and iluminacao >= conta:
            self.add_error("iluminacao_publica", "A iluminação pública precisa ser menor que a conta.")
        return dados


class DescontoField(forms.CharField):
    """"5%" → (None, 0.05); "300,00" → (Decimal("300.00"), None); vazio → (None, None)."""

    def clean(self, value):
        value = super().clean(value).strip()
        if not value:
            return None, None
        try:
            if "%" in value:
                pct = Decimal(str(limpar_percentual(value)))
                if not 0 <= pct <= 1:
                    raise forms.ValidationError("O desconto em % precisa estar entre 0% e 100%.")
                return None, pct
            reais = limpar_reais(value)
        except ValueError as erro:
            raise forms.ValidationError(str(erro))
        if reais < 0:
            raise forms.ValidationError("O desconto não pode ser negativo.")
        return reais, None


class Passo3Form(forms.ModelForm):
    modulo = forms.ModelChoiceField(
        queryset=Equipamento.objects.filter(tipo="modulo", ativo=True, potencia_w__isnull=False),
        required=False, label="Módulo", empty_label="Sugestão do sistema",
    )
    inversor = forms.ModelChoiceField(
        queryset=Equipamento.objects.filter(tipo="inversor", ativo=True, potencia_w__isnull=False),
        required=False, label="Inversor", empty_label="Sugestão do sistema",
    )
    cotacao = forms.ModelChoiceField(
        queryset=Cotacao.objects.all(), required=False, label="Cotação do kit para esta proposta",
        empty_label="Ainda não cotei",
    )
    custo_kit = CampoReais(label="Custo do kit (R$, com frete)", required=False)
    mao_de_obra = CampoReais(label="Mão de obra (R$)", required=False)
    desconto_texto = DescontoField(label="Desconto na mão de obra (R$ ou %)", required=False)

    class Meta:
        model = Proposta
        fields = ["orientacao", "tipo_estrutura", "modulo", "qtd_modulos", "inversor", "qtd_inversores",
                  "cabo_preto_m", "cabo_vermelho_m", "cotacao", "custo_kit", "mao_de_obra"]
        labels = {
            "orientacao": "Orientação do telhado", "tipo_estrutura": "Estrutura",
            "qtd_modulos": "Quantidade de módulos", "qtd_inversores": "Quantidade de inversores",
            "cabo_preto_m": "Cabo solar preto 4 mm (m)", "cabo_vermelho_m": "Cabo solar vermelho 4 mm (m)",
        }
        widgets = {campo: forms.NumberInput(attrs={"inputmode": "numeric", "min": 0}) for campo in (
            "qtd_modulos", "qtd_inversores", "cabo_preto_m", "cabo_vermelho_m")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["orientacao"].required = True
        self.fields["orientacao"].choices = Proposta.Orientacao.choices
        self.fields["tipo_estrutura"] = forms.ChoiceField(label="Estrutura", choices=Equipamento.TipoEstrutura.choices)
        self.fields["modulo"].label_from_instance = lambda e: f"{e.descricao} · {e.distribuidor}"
        fase = "tri" if self.instance.ligacao == "tri" else "mono"
        self.fields["inversor"].queryset = self.fields["inversor"].queryset.filter(fase=fase)
        self.fields["inversor"].label_from_instance = lambda e: f"{e.descricao} · {e.distribuidor}"
        self.fields["cotacao"].label_from_instance = (
            lambda c: f"{c.distribuidor} {c.numero} · {c.data:%d/%m/%Y} · R$ {formatar_reais(c.total)}")
        if not self.is_bound:
            if self.instance.desconto_pct is not None:
                self.initial["desconto_texto"] = f"{formatar_percentual(float(self.instance.desconto_pct))}%"
            elif self.instance.desconto is not None:
                self.initial["desconto_texto"] = formatar_reais(self.instance.desconto)

    def clean(self):
        dados = super().clean()
        for campo in ("qtd_modulos", "qtd_inversores"):
            if dados.get(campo) == 0:
                self.add_error(campo, "Use pelo menos 1, ou deixe em branco para a sugestão.")
        if dados.get("custo_kit") is not None and dados["custo_kit"] <= 0:
            self.add_error("custo_kit", "O custo do kit precisa ser maior que zero.")
        if dados.get("mao_de_obra") is not None and dados["mao_de_obra"] < 0:
            self.add_error("mao_de_obra", "A mão de obra não pode ser negativa.")
        return dados

    def save(self, commit=True):
        proposta = super().save(commit=False)
        proposta.desconto, proposta.desconto_pct = self.cleaned_data.get("desconto_texto") or (None, None)
        if commit:
            proposta.save()
        return proposta
