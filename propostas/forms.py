from decimal import Decimal

from django import forms

from core.forms import CampoReais

from .models import Cotacao, Equipamento, FaturaReferencia, ItemCotado, ItemKit, Proposta


class FaturaReferenciaForm(forms.ModelForm):
    class Meta:
        model = FaturaReferencia
        fields = [
            "uc", "competencia", "kwh", "dias_ciclo", "valor_total", "tarifa_kwh",
            "valor_distribuicao", "impostos", "tusd_fiob_kwh", "arquivo",
        ]
        widgets = {"competencia": forms.DateInput(attrs={"type": "date"})}


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
        if dados.get("total_produtos") is not None and dados.get("total") is None:
            dados["total"] = dados["total_produtos"] + frete  # total em branco: produtos + frete
        if dados.get("kwp") is not None and dados["kwp"] <= 0:
            self.add_error("kwp", "O kWp precisa ser maior que zero.")
        return dados


class ItemCotadoForm(forms.ModelForm):
    class Meta:
        model = ItemCotado
        fields = ["codigo", "descricao", "quantidade", "unidade"]
        widgets = {"quantidade": forms.TextInput(attrs={"inputmode": "decimal"})}
        localized_fields = ["quantidade"]


ItensCotadosFormSet = forms.inlineformset_factory(
    Cotacao, ItemCotado, form=ItemCotadoForm, extra=3, can_delete=True,
)
