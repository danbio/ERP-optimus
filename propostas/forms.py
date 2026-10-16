from django import forms

from .models import FaturaReferencia, ItemKit, Proposta


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
