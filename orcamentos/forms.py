from django import forms

from .models import Orcamento


class OrcamentoNovoForm(forms.ModelForm):
    class Meta:
        model = Orcamento
        fields = ["cliente", "titulo", "local_instalacao"]


class OrcamentoDadosForm(forms.ModelForm):
    class Meta:
        model = Orcamento
        fields = [
            "cliente", "titulo", "local_instalacao", "validade_dias", "forma_pagamento",
            "prazo_execucao", "garantia", "observacoes", "projeto_registrado", "numero_registro",
        ]
        widgets = {
            "garantia": forms.Textarea(attrs={"rows": 3}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class ImportarTabelaForm(forms.Form):
    arquivo = forms.FileField(label="Tabela de preços Intelbras (.xlsb)")

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(".xlsb"):
            raise forms.ValidationError("Envie o arquivo .xlsb original da Intelbras.")
        return arquivo
