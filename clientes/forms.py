from django import forms

from core.models import Municipio
from core.validacoes import limpar_cpf_cnpj, limpar_nome, limpar_telefone

from .models import Cliente, UnidadeConsumidora


def _limpar(funcao, valor):
    """Chama a validação pura e traduz o ValueError para o erro do formulário."""
    try:
        return funcao(valor)
    except ValueError as erro:
        raise forms.ValidationError(str(erro))


class MunicipioSelect(forms.ModelChoiceField):
    def label_from_instance(self, municipio):
        return municipio.nome


class ClienteForm(forms.ModelForm):
    # CharField simples: a máscara mostra pontos e traços, e o servidor guarda só os números.
    cpf_cnpj = forms.CharField(label="CPF ou CNPJ", required=False)
    telefone = forms.CharField(label="Telefone com DDD")
    municipio = MunicipioSelect(
        queryset=Municipio.objects.filter(uf="TO"), label="Município", required=False,
        empty_label="Escolha o município",
    )

    class Meta:
        model = Cliente
        fields = ["nome", "telefone", "municipio", "cpf_cnpj", "razao_social", "email", "observacoes"]
        labels = {"nome": "Nome do cliente"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cpf_cnpj"].widget.attrs.update({"data-mascara": "cpf_cnpj", "inputmode": "numeric"})
        self.fields["telefone"].widget.attrs.update({"data-mascara": "telefone", "inputmode": "tel"})
        self.fields["observacoes"].widget.attrs["rows"] = 3
        if self.instance.pk:
            self.initial["cpf_cnpj"] = self.instance.cpf_cnpj_formatado
            self.initial["telefone"] = self.instance.telefone_formatado

    def clean_nome(self):
        return _limpar(limpar_nome, self.cleaned_data["nome"])

    def clean_telefone(self):
        return _limpar(limpar_telefone, self.cleaned_data["telefone"])

    def clean_cpf_cnpj(self):
        digitos = _limpar(limpar_cpf_cnpj, self.cleaned_data["cpf_cnpj"])
        if digitos:
            repetido = Cliente.objects.filter(cpf_cnpj=digitos).exclude(pk=self.instance.pk).first()
            if repetido:
                raise forms.ValidationError(f"Este CPF/CNPJ já está cadastrado para {repetido.nome}.")
        return digitos


class UnidadeConsumidoraForm(forms.ModelForm):
    municipio = MunicipioSelect(
        queryset=Municipio.objects.filter(uf="TO"), label="Município", empty_label="Escolha o município",
    )

    class Meta:
        model = UnidadeConsumidora
        fields = ["cliente", "numero_uc", "endereco", "municipio", "concessionaria", "classe", "ligacao"]
        labels = {"numero_uc": "Número da UC (na fatura)"}
