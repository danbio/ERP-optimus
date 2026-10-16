from django import forms

from .models import Cliente, UnidadeConsumidora


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "razao_social", "cpf_cnpj", "telefone", "email", "observacoes"]


class UnidadeConsumidoraForm(forms.ModelForm):
    class Meta:
        model = UnidadeConsumidora
        fields = ["cliente", "numero_uc", "endereco", "municipio", "uf", "concessionaria", "classe", "ligacao"]
