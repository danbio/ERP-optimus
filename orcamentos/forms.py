from django import forms

from core.forms import CampoPercentual, higienizar, texto_limpo

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
            "mostrar_precos", "mostrar_parcelamento",
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


class ParcelamentoForm(forms.Form):
    """Prazos e acréscimos do parcelamento do orçamento (H10, D44). Uma linha vazia para incluir prazo."""

    LINHAS = 6

    def __init__(self, *args, opcoes=(), **kwargs):
        super().__init__(*args, **kwargs)
        opcoes = list(opcoes)
        self.linhas = []
        for i in range(self.LINHAS):
            atual = opcoes[i] if i < len(opcoes) else {}
            self.fields[f"parcelas_{i}"] = forms.IntegerField(
                label="Parcelas", required=False, min_value=2, max_value=36, initial=atual.get("parcelas"))
            self.fields[f"acrescimo_{i}"] = CampoPercentual(
                label="Acréscimo total (%)", required=False, maximo=100, casas=2, initial=atual.get("acrescimo"))
            self.linhas.append((f"parcelas_{i}", f"acrescimo_{i}"))

    def linhas_renderizadas(self):
        """(campo das parcelas, campo do acréscimo) de cada linha, para o template."""
        return [(self[p], self[a]) for p, a in self.linhas]

    def clean(self):
        dados = super().clean()
        vistos = set()
        for parcelas, acrescimo in self.linhas:
            n = dados.get(parcelas)
            if n is None:
                if dados.get(acrescimo) is not None:
                    self.add_error(parcelas, "Informe em quantas vezes.")
                continue
            if n in vistos:
                self.add_error(parcelas, "Prazo repetido.")
            vistos.add(n)
        return dados

    def opcoes(self):
        """Prazos preenchidos, em ordem: [{"parcelas", "acrescimo" em fração ou None}]."""
        dados = self.cleaned_data
        lista = [{"parcelas": dados[p], "acrescimo": dados.get(a)} for p, a in self.linhas if dados.get(p)]
        return sorted(lista, key=lambda o: o["parcelas"])
