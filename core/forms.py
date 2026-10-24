"""Formulários da tela de Configurações (fatia v2.2) e campos de reais e percentual (D24)."""

from datetime import date
from decimal import Decimal

from django import forms
from django.core import validators

from propostas.models import Bandeira, TarifaVigente, TaxaFinanciamento

from .models import ConfigEmpresa
from .validacoes import (
    ARQUIVO_IMAGEM, conferir_arquivo, formatar_cpf_cnpj, formatar_percentual, formatar_reais,
    formatar_telefone, limpar_cpf_cnpj,
    limpar_linhas, limpar_percentual, limpar_reais, limpar_telefone, limpar_texto,
)

# Limites de texto quando o modelo não tem max_length (P1, D41).
TAMANHO_LINHA = 200
TAMANHO_TEXTO = 3000


def _validador_de_arquivo(tipo):
    def validar(arquivo):
        if arquivo and hasattr(arquivo, "size"):  # arquivo novo; o já gravado não é conferido de novo
            try:
                conferir_arquivo(arquivo.name, arquivo.size, tipo)
            except ValueError as erro:
                raise forms.ValidationError(str(erro))
    return validar


def higienizar(form, arquivos=None):
    """Regra P1 (D41) num formulário: chamar no fim do __init__.

    Todo campo de texto ganha limite de tamanho (o do modelo ou TAMANHO_LINHA / TAMANHO_TEXTO) e
    todo campo de arquivo listado em `arquivos` ({campo: ARQUIVO_IMAGEM ou ARQUIVO_PDF}) é conferido
    pela extensão e pelo tamanho.
    """
    for campo in form.fields.values():
        if type(campo) is forms.CharField and not campo.max_length:
            maximo = TAMANHO_TEXTO if isinstance(campo.widget, forms.Textarea) else TAMANHO_LINHA
            campo.max_length = maximo
            campo.validators.append(validators.MaxLengthValidator(maximo))
            campo.widget.attrs["maxlength"] = str(maximo)
    for nome, tipo in (arquivos or {}).items():
        form.fields[nome].validators.append(_validador_de_arquivo(tipo))
        form.fields[nome].widget.attrs["accept"] = ",".join(sorted(tipo[0]))


def texto_limpo(valor, maximo=TAMANHO_LINHA):
    """Versão para formulário de limpar_texto: ValueError vira erro do campo."""
    try:
        return limpar_texto(valor, maximo)
    except ValueError as erro:
        raise forms.ValidationError(str(erro))


def linhas_limpas(valor, maximo=TAMANHO_TEXTO):
    """Texto de várias linhas higienizado para um `clean_*` (D41); erro vira ValidationError."""
    try:
        return limpar_linhas(valor, maximo)
    except ValueError as erro:
        raise forms.ValidationError(str(erro))


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

    def __init__(self, *args, minimo=0.0, maximo=100.0, casas=2, **kwargs):
        self.minimo = minimo
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
            return limpar_percentual(value, minimo=self.minimo, maximo=self.maximo)
        except ValueError as erro:
            raise forms.ValidationError(str(erro))


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = ConfigEmpresa
        fields = [
            "razao_social", "nome_fantasia", "cnpj", "endereco", "telefone", "email", "logo",
            "projetos_entregues", "anos_atuacao", "validade_padrao_dias", "ufs_atendidas",
            "texto_sobre", "beneficios_padrao", "escopo_padrao", "etapas_padrao", "aviso_estimativa",
        ]
        labels = {
            "razao_social": "Razão social", "nome_fantasia": "Nome fantasia", "cnpj": "CNPJ",
            "endereco": "Endereço", "projetos_entregues": "Projetos entregues", "anos_atuacao": "Anos de atuação",
            "validade_padrao_dias": "Validade da proposta (dias)", "ufs_atendidas": "Estados atendidos",
            "texto_sobre": 'Texto "Sobre a Optimus"',
            "beneficios_padrao": "Benefícios (um por linha)", "escopo_padrao": "Escopo incluso (um por linha)",
            "etapas_padrao": "Etapas (Título | descrição, uma por linha)",
            "aviso_estimativa": "Aviso da proposta sem fatura (estimativa)",
        }
        widgets = {campo: forms.Textarea(attrs={"rows": 4}) for campo in (
            "texto_sobre", "beneficios_padrao", "escopo_padrao", "etapas_padrao",
        )} | {"aviso_estimativa": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        higienizar(self, arquivos={"logo": ARQUIVO_IMAGEM})
        self.fields["cnpj"].widget.attrs.update({"data-mascara": "cpf_cnpj", "inputmode": "numeric"})
        self.fields["telefone"].widget.attrs.update({"data-mascara": "telefone", "inputmode": "tel"})
        self.fields["ufs_atendidas"].required = False

    def clean_ufs_atendidas(self):
        """Siglas conhecidas e com distribuidora cadastrada (D47). Vazio mantém o que estava."""
        from .dados_oficiais import CODIGOS_UF
        from .models import Distribuidora

        texto = self.cleaned_data["ufs_atendidas"].upper().replace(";", ",").replace(" ", ",")
        ufs = list(dict.fromkeys(uf for uf in texto.split(",") if uf))
        if not ufs:
            return self.instance.ufs_atendidas or self.fields["ufs_atendidas"].initial
        desconhecidas = [uf for uf in ufs if uf not in CODIGOS_UF]
        if desconhecidas:
            raise forms.ValidationError(f"Sigla de estado desconhecida: {', '.join(desconhecidas)}.")
        sem_distribuidora = [uf for uf in ufs if not Distribuidora.objects.filter(uf=uf).exists()]
        if sem_distribuidora:
            raise forms.ValidationError(f"{', '.join(sem_distribuidora)} ainda não tem distribuidora cadastrada: "
                                        "inclua no admin (/admin/), em Distribuidoras, antes.")
        return ", ".join(ufs)

    def clean_cnpj(self):
        try:
            digitos = limpar_cpf_cnpj(self.cleaned_data["cnpj"])
        except ValueError as erro:
            raise forms.ValidationError(str(erro))
        if len(digitos) != 14:
            raise forms.ValidationError("Informe o CNPJ da empresa (14 números).")
        return formatar_cpf_cnpj(digitos)  # gravado formatado: os PDFs mostram como está

    def clean_telefone(self):
        if not self.cleaned_data["telefone"]:
            return ""
        try:
            return formatar_telefone(limpar_telefone(self.cleaned_data["telefone"]))
        except ValueError as erro:
            raise forms.ValidationError(str(erro))

    def clean_razao_social(self):
        return texto_limpo(self.cleaned_data["razao_social"])

    def clean_nome_fantasia(self):
        return texto_limpo(self.cleaned_data["nome_fantasia"])

    def clean_endereco(self):
        return texto_limpo(self.cleaned_data["endereco"], 255)

    def clean_validade_padrao_dias(self):  # A22
        dias = self.cleaned_data["validade_padrao_dias"]
        if not 5 <= dias <= 60:
            raise forms.ValidationError("A validade precisa ficar entre 5 e 60 dias.")
        return dias

    def clean_projetos_entregues(self):
        return _no_maximo(self.cleaned_data["projetos_entregues"], 100000)

    def clean_anos_atuacao(self):
        return _no_maximo(self.cleaned_data["anos_atuacao"], 100)

    def clean_texto_sobre(self):
        return linhas_limpas(self.cleaned_data["texto_sobre"], 1500)

    def clean_beneficios_padrao(self):
        return linhas_limpas(self.cleaned_data["beneficios_padrao"])

    def clean_escopo_padrao(self):
        return linhas_limpas(self.cleaned_data["escopo_padrao"])

    def clean_etapas_padrao(self):
        etapas = linhas_limpas(self.cleaned_data["etapas_padrao"])
        for linha in etapas.splitlines():
            if linha and "|" not in linha:
                raise forms.ValidationError(f'Etapa sem "|": "{linha}". Use "Título | descrição".')
        return etapas

    def clean_aviso_estimativa(self):
        return linhas_limpas(self.cleaned_data["aviso_estimativa"], 500)


def _no_maximo(valor, maximo):
    if valor is not None and valor > maximo:
        raise forms.ValidationError(f"Use um valor até {maximo}.")
    return valor


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

    # Painel da página inicial (D46)
    dias_aviso_vencimento = forms.IntegerField(
        label="Avisar proposta vencendo em (dias)", min_value=1, max_value=30)
    dias_sem_retorno = forms.IntegerField(
        label="Proposta parada após (dias sem contato)", min_value=1, max_value=90)

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
    consumo_alto = forms.IntegerField(label="Consumo alto: pedir confirmação acima de (kWh/mês)", min_value=1,
                                      max_value=100000)
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
        "dias_aviso_vencimento", "dias_sem_retorno",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for chave, rotulo in PREMISSAS_PERCENTUAIS:
            self.fields[chave] = CampoPercentual(label=rotulo)
        for chave, rotulo in ORIENTACOES:
            self.fields[f"orientacao_{chave}"] = CampoPercentual(label=rotulo, minimo=50, maximo=100)  # A22

    def clean(self):
        dados = super().clean()
        minimo, maximo = dados.get("modulos_por_string_min"), dados.get("modulos_por_string_max")
        if minimo and maximo and minimo > maximo:
            self.add_error("modulos_por_string_max", "O máximo precisa ser maior ou igual ao mínimo.")
        return dados

    @classmethod
    def da_config(cls, config):
        """Valores iniciais do formulário a partir da ConfigEmpresa (premissas, orientação e limites)."""
        premissas = config.premissas_padrao
        inicial = {chave: premissas.get(chave) for chave, _ in PREMISSAS_PERCENTUAIS}
        inicial |= {chave: premissas.get(chave) for chave in (
            "horizonte_anos", "razao_cc_ca_max", "sobrecarga_min", "cobertura_min", "cobertura_max",
        )}
        inicial |= {f"orientacao_{chave}": config.fatores_orientacao.get(chave) for chave, _ in ORIENTACOES}
        inicial |= {campo: getattr(config, campo) for campo in cls.CAMPOS_DA_CONFIG}
        return cls(initial=inicial)

    def gravar(self, config):
        """Grava premissas, orientação e limites na ConfigEmpresa (D19)."""
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


class BasePerfisFormSet(forms.BaseFormSet):
    def clean(self):
        """Pelo menos um perfil, sem nome repetido (A22): a proposta escolhe um deles."""
        if any(self.errors):
            return
        nomes = [f.cleaned_data["nome"].strip().casefold() for f in self.forms
                 if f.cleaned_data.get("nome", "").strip()]
        if not nomes:
            raise forms.ValidationError("Cadastre pelo menos um perfil de simultaneidade.")
        if len(nomes) != len(set(nomes)):
            raise forms.ValidationError("Há perfis com o mesmo nome.")


PerfisFormSet = forms.formset_factory(PerfilForm, formset=BasePerfisFormSet, extra=1)


class TarifaForm(forms.ModelForm):
    """Tributos e Fio B de uma tarifa: o gestor digita da conta e da resolução da ANEEL (D21, D32)."""

    aliquota_tributos = CampoPercentual(label="Tributos (%)", maximo=60)
    fiob_kwh = forms.DecimalField(
        label="Fio B (R$/kWh)", required=False, min_value=0, max_value=2, decimal_places=6, localize=True,
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


class BandeiraForm(forms.ModelForm):
    adicional_kwh = forms.DecimalField(
        min_value=0, max_value=1, decimal_places=5, localize=True,  # R$/kWh: a vermelha 2 fica perto de 0,08
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )

    class Meta:
        model = Bandeira
        fields = ["adicional_kwh", "vigencia"]
        widgets = {"vigencia": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


BandeirasFormSet = forms.modelformset_factory(Bandeira, form=BandeiraForm, extra=0)


class TaxasForm(forms.Form):
    """Grade banco × prazo (D22), com a TAC de cada banco e o IOF (D43). Uma linha vazia para incluir outro banco."""

    iof_adicional = CampoPercentual(label="IOF adicional (%)", required=False, maximo=5, casas=4)
    iof_diario_pf = CampoPercentual(label="IOF ao dia, pessoa física (%)", required=False, maximo=1, casas=4)
    iof_diario_pj = CampoPercentual(label="IOF ao dia, pessoa jurídica (%)", required=False, maximo=1, casas=4)

    def __init__(self, *args, taxas=(), config=None, **kwargs):
        super().__init__(*args, **kwargs)
        if config:
            for campo in ("iof_adicional", "iof_diario_pf", "iof_diario_pj"):
                self.fields[campo].initial = float(getattr(config, campo))
        self.taxas_atuais = {(t.banco, t.prazo_meses): t for t in taxas}
        tac_do_banco = {t.banco: t for t in taxas}
        bancos = sorted(tac_do_banco)
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
                    label=f"{prazo}× (% ao mês)", required=False, maximo=10, casas=3,
                    initial=float(atual.taxa_mensal) if atual else None,
                )
                campos.append(nome)
            exemplo = tac_do_banco.get(banco)
            self.fields[f"tac_reais_{indice}"] = CampoReais(
                label="TAC (R$)", required=False, initial=exemplo.tac_reais if exemplo and exemplo.tac_reais else None)
            self.fields[f"tac_pct_{indice}"] = CampoPercentual(
                label="TAC (%)", required=False, maximo=10, casas=2,
                initial=float(exemplo.tac_percentual) if exemplo and exemplo.tac_percentual else None)
            self.linhas.append((f"banco_{indice}", campos, f"tac_reais_{indice}", f"tac_pct_{indice}"))

    def linhas_renderizadas(self):
        """(banco, [(campo da taxa, % ao ano equivalente ou None)], TAC R$, TAC %) para o template."""
        linhas = []
        for banco, campos, tac_reais, tac_pct in self.linhas:
            taxas = []
            for nome in campos:
                inicial = self.fields[nome].initial
                anual = ((1 + inicial) ** 12 - 1) * 100 if inicial is not None else None
                taxas.append((self[nome], anual))
            linhas.append((self[banco], taxas, self[tac_reais], self[tac_pct]))
        return linhas

    def clean(self):
        dados = super().clean()
        vistos = set()
        for banco, campos, tac_reais, tac_pct in self.linhas:
            nome = (dados.get(banco) or "").strip()
            tem_taxa = any(dados.get(c) is not None for c in campos)
            if tem_taxa and not nome:
                self.add_error(banco, "Informe o nome do banco.")
            if nome and nome.lower() in vistos:
                self.add_error(banco, "Banco repetido.")
            vistos.add(nome.lower())
            if dados.get(tac_reais) is not None and dados[tac_reais] < 0:
                self.add_error(tac_reais, "A TAC não pode ser negativa.")
        return dados

    def gravar(self, config):
        """Grava o IOF na `config` e as taxas e TAC de cada banco; apaga as que saíram da grade (D43)."""
        dados = self.cleaned_data
        for campo in ("iof_adicional", "iof_diario_pf", "iof_diario_pj"):
            if dados.get(campo) is not None:  # vazio mantém o valor atual
                setattr(config, campo, Decimal(str(dados[campo])))
        config.save(update_fields=["iof_adicional", "iof_diario_pf", "iof_diario_pj"])
        novas = {}
        for banco, campos, tac_reais, tac_pct in self.linhas:
            nome = (dados.get(banco) or "").strip()
            if not nome:
                continue
            tac = {"tac_reais": dados.get(tac_reais) or Decimal("0"),
                   "tac_percentual": Decimal(str(dados.get(tac_pct) or 0))}
            for campo, prazo in zip(campos, TaxaFinanciamento.PRAZOS):
                if dados.get(campo) is not None:
                    novas[(nome, prazo)] = (Decimal(str(dados[campo])), tac)
        for chave, taxa in self.taxas_atuais.items():
            if chave not in novas:
                taxa.delete()
        for (banco, prazo), (valor, tac) in novas.items():
            atual = self.taxas_atuais.get((banco, prazo))
            if atual and atual.taxa_mensal == valor and atual.tac_reais == tac["tac_reais"] \
                    and atual.tac_percentual == tac["tac_percentual"]:
                continue
            TaxaFinanciamento.objects.update_or_create(
                banco=banco, prazo_meses=prazo,
                defaults={"taxa_mensal": valor, "vigente_desde": date.today()} | tac,
            )


class AcompanhamentoForm(forms.Form):
    """Próximo contato e, para o gestor, o vendedor responsável (A20, D46). Serve à proposta e ao orçamento."""

    proximo_contato = forms.DateField(
        label="Próximo contato", required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Vazio = sem contato marcado. Aparece em \"Ligar hoje\" na página inicial.",
    )

    def __init__(self, *args, objeto=None, gestor=False, **kwargs):
        if objeto is not None:
            kwargs.setdefault("initial", {"proximo_contato": objeto.proximo_contato, "vendedor": objeto.vendedor_id})
        super().__init__(*args, **kwargs)
        if gestor:
            from django.contrib.auth import get_user_model
            self.fields["vendedor"] = forms.ModelChoiceField(
                label="Vendedor responsável", required=False, empty_label="Ninguém",
                queryset=get_user_model().objects.filter(is_active=True).order_by("username"),
            )

    def clean_proximo_contato(self):
        data = self.cleaned_data["proximo_contato"]
        if data and data < date.today():
            raise forms.ValidationError("O próximo contato não pode ser no passado.")
        if data and (data - date.today()).days > 366:
            raise forms.ValidationError("Marque o próximo contato dentro de um ano.")
        return data

    def gravar(self, objeto):
        """Grava o próximo contato e, se o gestor mudou, o vendedor responsável no `objeto`."""
        campos = ["proximo_contato"]
        objeto.proximo_contato = self.cleaned_data["proximo_contato"]
        if "vendedor" in self.fields:
            objeto.vendedor = self.cleaned_data["vendedor"]
            campos.append("vendedor")
        objeto.save(update_fields=campos)
