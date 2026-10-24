from django import forms

from core.forms import higienizar, texto_limpo

from .models import Orcamento


class OrcamentoNovoForm(forms.ModelForm):
    class Meta:
        model = Orcamento
        fields = ["cliente", "titulo", "local_instalacao"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        higienizar(self)

    def clean_titulo(self):
        return texto_limpo(self.cleaned_data["titulo"])


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        higienizar(self)

    def clean_titulo(self):
        return texto_limpo(self.cleaned_data["titulo"])

    def clean_validade_dias(self):
        dias = self.cleaned_data["validade_dias"]
        if dias is not None and not 1 <= dias <= 90:
            raise forms.ValidationError("A validade precisa ficar entre 1 e 90 dias.")
        return dias


class ImportarTabelaForm(forms.Form):
    arquivo = forms.FileField(label="Tabela de preços Intelbras (.xlsb)")

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith(".xlsb"):
            raise forms.ValidationError("Envie o arquivo .xlsb original da Intelbras.")
        if arquivo.size > 50 * 1024 * 1024:
            raise forms.ValidationError("Arquivo grande demais: o limite é 50 MB.")
        return arquivo
