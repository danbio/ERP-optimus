import re
from datetime import date
from decimal import Decimal

from django import forms
from django.db.models import Q

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

from .models import Cotacao, Equipamento, ItemCotado, Proposta, TarifaVigente

# ---------- Catálogo solar e memória de cotações (fatia v2.4, D28) ----------

class EquipamentoForm(forms.ModelForm):
    preco_referencia = CampoReais(label="Preço de referência (R$)", required=False)

    class Meta:
        model = Equipamento
        fields = [
            "tipo", "distribuidor", "codigo", "fabricante", "modelo", "descricao", "potencia_w",
            "fase", "tensao", "tipo_estrutura", "area_m2", "preco_referencia", "preco_em",
            "funcao", "pecas_por_embalagem", "mppts", "modulos_por_micro", "espessura_mm",
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
        if dados.get("tipo") == "microinversor" and not dados.get("modulos_por_micro"):
            self.add_error("modulos_por_micro", "Informe quantos módulos ligam em cada micro.")
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
    # Ligação e tarifa começam sem escolha: o vendedor apressado não passa direto (A14).
    ligacao = forms.ChoiceField(
        label="Ligação", choices=[("", "Escolha a ligação")] + UnidadeConsumidora.Ligacao.choices,
        help_text="Veja no padrão de entrada ou na conta: 1 fase = monofásica, 2 = bifásica, 3 = trifásica.",
    )
    tipo_tarifa = forms.ModelChoiceField(
        queryset=TarifaVigente.objects.none(), label="Tipo de tarifa", empty_label="Escolha o tipo",
        help_text="Residencial, rural ou comercial: está escrito na conta, em \"classe\".",
    )
    # Aparece só quando o telefone ou o CPF já são de um cliente com outro nome (A04).
    mesma_pessoa = forms.ChoiceField(
        label="É a mesma pessoa?", required=False, widget=forms.RadioSelect,
        choices=[("sim", "Sim, usar a ficha que já existe"), ("nao", "Não, é outra pessoa")],
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
    iluminacao_publica = CampoReais(label="Iluminação pública na conta (R$; em branco, o sistema estima)", required=False)
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
    # Aparece só quando um valor foge do normal (A06): o vendedor confere com o cliente e confirma.
    confirmo = forms.BooleanField(label="Conferi com o cliente: o valor está certo", required=False)

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

    def __init__(self, *args, perfis=(), config=None, exigir_confirmacao=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config
        self.exigir_confirmacao = exigir_confirmacao  # a prévia ao vivo calcula mesmo sem a confirmação
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

    def clean_numero_uc(self):
        numero = self.cleaned_data["numero_uc"].strip()
        if numero and (re.search(r"[^\d./\-\s]", numero) or len(re.sub(r"\D", "", numero)) < 4):
            raise forms.ValidationError("Copie o número da UC como está na conta: só números.")
        return numero

    def clean_competencia(self):
        competencia = self.cleaned_data["competencia"]
        if competencia:
            hoje = date.today()
            if (competencia.year, competencia.month) > (hoje.year, hoje.month):
                raise forms.ValidationError("O mês da fatura não pode ser no futuro.")
            if (hoje.year - competencia.year) * 12 + hoje.month - competencia.month > 13:
                raise forms.ValidationError("Fatura com mais de 13 meses. Peça uma recente ao cliente.")
        return competencia

    def _valores_fora_do_normal(self, dados):
        """Avisos que pedem confirmação do vendedor (A06). Limites em Configurações."""
        config, avisos = self.config, []
        if not config:
            return avisos
        conta = dados.get("conta_informada")
        if conta is not None and conta > config.conta_alta:
            avisos.append(f"Conta de R$ {formatar_reais(conta)} é alta para o padrão.")
        for campo in ("kwh_informado", "fatura_kwh"):
            if dados.get(campo) is not None and dados[campo] > config.consumo_alto:
                avisos.append(f"Consumo de {dados[campo]:.0f} kWh/mês é alto para o padrão.")
        kwh, valor, tarifa = dados.get("fatura_kwh"), dados.get("valor_fatura"), self.instance.tipo_tarifa
        if kwh and valor and tarifa and tarifa.aliquota_tributos:
            por_kwh, vigente = valor / kwh, tarifa.tarifa_com_tributos
            if abs(por_kwh / vigente - 1) > config.tolerancia_tarifa_fatura:
                avisos.append(f"A fatura dá R$ {formatar_reais(por_kwh)}/kWh e a tarifa vigente é "
                              f"R$ {formatar_reais(vigente)}/kWh. Confira o consumo e o valor.")
        return avisos

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
        avisos = self._valores_fora_do_normal(dados)
        if avisos and self.exigir_confirmacao and not dados.get("confirmo"):
            self.add_error("confirmo", " ".join(avisos) + " Confira com o cliente e marque a caixa.")
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


# Papéis do kit que o vendedor pode trocar ou mudar a quantidade no passo 3 (D34).
PAPEIS_EDITAVEIS = [valor for valor, _ in Equipamento.Funcao.choices if valor != "juncao"]
EXTRAS_EM_BRANCO = 2


class Passo3Form(forms.ModelForm):
    """Sistema e preço (D34): módulo e quantidade primeiro, depois inversor, fileiras, kit e preço.

    Os itens do kit têm campos `kit_<papel>_equipamento` e `kit_<papel>_qtd` (vazio = sugestão;
    quantidade 0 = tirar do kit) e os acrescentados, `extra_<n>_equipamento` e `extra_<n>_qtd`.
    """

    modulo = forms.ModelChoiceField(
        queryset=Equipamento.objects.filter(tipo="modulo", ativo=True, potencia_w__isnull=False),
        required=False, label="Módulo", empty_label="Sugestão do sistema (menor R$/Wp)",
    )
    inversor = forms.ModelChoiceField(
        queryset=Equipamento.objects.none(), required=False, label="Inversor", empty_label="Sugestão do sistema",
    )
    cotacao = forms.ModelChoiceField(
        queryset=Cotacao.objects.all(), required=False, label="Cotação do kit para esta proposta",
        empty_label="Ainda não cotei (usar o catálogo)",
    )
    custo_kit = CampoReais(label="Custo do kit (R$, com frete)", required=False)
    mao_de_obra = CampoReais(label="Mão de obra (R$)", required=False)
    desconto_texto = DescontoField(label="Desconto na mão de obra (R$ ou %)", required=False)

    class Meta:
        model = Proposta
        fields = ["orientacao", "tipo_estrutura", "modulo", "qtd_modulos", "tipo_inversor", "inversor",
                  "qtd_inversores", "fileiras", "cotacao", "custo_kit", "mao_de_obra"]
        labels = {
            "orientacao": "Orientação do telhado", "tipo_estrutura": "Estrutura",
            "qtd_modulos": "Quantidade de módulos", "qtd_inversores": "Quantidade de inversores",
            "tipo_inversor": "Tipo de inversor", "fileiras": "Módulos por fileira",
        }
        help_texts = {"fileiras": 'Ex.: 6+5 são duas fileiras, uma de 6 e outra de 5. Em branco, o sistema divide.'}
        widgets = {
            "qtd_modulos": forms.NumberInput(attrs={"inputmode": "numeric", "min": 0}),
            "qtd_inversores": forms.NumberInput(attrs={"inputmode": "numeric", "min": 0}),
            "tipo_inversor": forms.RadioSelect,
            "fileiras": forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "6+5"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["orientacao"].required = True
        self.fields["orientacao"].choices = Proposta.Orientacao.choices
        self.fields["tipo_estrutura"] = forms.ChoiceField(label="Estrutura", choices=Equipamento.TipoEstrutura.choices)
        self.fields["tipo_inversor"].choices = Proposta.TipoInversor.choices
        self.fields["tipo_inversor"].required = False  # sem escolha: inversor string
        self.fields["modulo"].label_from_instance = _rotulo_com_preco
        fase = "tri" if self.instance.ligacao == "tri" else "mono"
        self.fields["inversor"].queryset = Equipamento.objects.filter(
            Q(tipo="inversor", fase=fase) | Q(tipo="microinversor"), ativo=True, potencia_w__isnull=False,
        ).order_by("tipo", "potencia_w", "preco_referencia")
        self.fields["inversor"].label_from_instance = (
            lambda e: ("Micro · " if e.tipo == "microinversor" else "") + _rotulo_com_preco(e))
        # Só cotações dentro da validade, mais a já escolhida (A01).
        hoje = date.today()
        self.fields["cotacao"].queryset = Cotacao.objects.filter(
            Q(validade__isnull=True) | Q(validade__gte=hoje) | Q(pk=self.instance.cotacao_id)
        )
        self.fields["cotacao"].label_from_instance = (
            lambda c: f"{c.distribuidor} {c.numero} · {c.data:%d/%m/%Y} · R$ {formatar_reais(c.total)}")
        if not self.is_bound:
            if self.instance.desconto_pct is not None:
                self.initial["desconto_texto"] = f"{formatar_percentual(float(self.instance.desconto_pct))}%"
            elif self.instance.desconto is not None:
                self.initial["desconto_texto"] = formatar_reais(self.instance.desconto)
        self._campos_do_kit()

    def _campos_do_kit(self):
        ajustes = self.instance.ajustes_kit or {}
        for papel in PAPEIS_EDITAVEIS:
            ajuste = ajustes.get(papel) or {}
            campo = forms.ModelChoiceField(
                queryset=Equipamento.objects.filter(funcao=papel, ativo=True).order_by("preco_referencia"),
                required=False, empty_label="Sugestão do sistema", label="Item",
                initial=ajuste.get("equipamento"))
            campo.label_from_instance = _rotulo_com_preco
            self.fields[f"kit_{papel}_equipamento"] = campo
            self.fields[f"kit_{papel}_qtd"] = forms.IntegerField(
                required=False, min_value=0, label="Quantidade", initial=ajuste.get("quantidade"),
                widget=forms.NumberInput(attrs={"inputmode": "numeric", "min": 0}))
        extras = ajustes.get("extras", [])
        catalogo = Equipamento.objects.filter(ativo=True).exclude(tipo__in=["modulo", "inversor", "microinversor"])
        for n in range(len(extras) + EXTRAS_EM_BRANCO):
            extra = extras[n] if n < len(extras) else {}
            campo = forms.ModelChoiceField(queryset=catalogo.order_by("tipo", "descricao"), required=False,
                                           empty_label="Acrescentar item do catálogo", label="Item",
                                           initial=extra.get("equipamento"))
            campo.label_from_instance = _rotulo_com_preco
            self.fields[f"extra_{n}_equipamento"] = campo
            self.fields[f"extra_{n}_qtd"] = forms.IntegerField(
                required=False, min_value=0, label="Quantidade", initial=extra.get("quantidade"),
                widget=forms.NumberInput(attrs={"inputmode": "numeric", "min": 0}))
        self.n_extras = len(extras) + EXTRAS_EM_BRANCO

    def linhas_do_kit(self, m):
        """Para o template: cada item do kit montado com os campos de troca e de quantidade."""
        linhas = []
        for linha in m.kit if m else []:
            if linha.funcao in PAPEIS_EDITAVEIS:
                linhas.append({"linha": linha, "item": self[f"kit_{linha.funcao}_equipamento"],
                               "qtd": self[f"kit_{linha.funcao}_qtd"]})
        return linhas

    def extras(self):
        return [{"item": self[f"extra_{n}_equipamento"], "qtd": self[f"extra_{n}_qtd"]} for n in range(self.n_extras)]

    def clean_tipo_inversor(self):
        return self.cleaned_data.get("tipo_inversor") or Proposta.TipoInversor.STRING

    def clean_fileiras(self):
        texto = (self.cleaned_data.get("fileiras") or "").strip()
        if not texto:
            return ""
        partes = [p for p in re.split(r"[+,;\s]+", texto) if p]
        if not all(p.isdigit() and int(p) > 0 for p in partes):
            raise forms.ValidationError("Use só números separados por +, por exemplo 6+5.")
        return "+".join(str(int(p)) for p in partes)

    def clean(self):
        dados = super().clean()
        for campo in ("qtd_modulos", "qtd_inversores"):
            if dados.get(campo) == 0:
                self.add_error(campo, "Use pelo menos 1, ou deixe em branco para a sugestão.")
        if dados.get("custo_kit") is not None and dados["custo_kit"] <= 0:
            self.add_error("custo_kit", "O custo do kit precisa ser maior que zero.")
        if dados.get("mao_de_obra") is not None and dados["mao_de_obra"] < 0:
            self.add_error("mao_de_obra", "A mão de obra não pode ser negativa.")
        for n in range(self.n_extras):
            if dados.get(f"extra_{n}_equipamento") and dados.get(f"extra_{n}_qtd") is None:
                self.add_error(f"extra_{n}_qtd", "Informe a quantidade.")
        return dados

    def ajustes_kit(self):
        """Trocas e quantidades digitadas pelo vendedor, no formato de `Proposta.ajustes_kit`."""
        dados, ajustes = self.cleaned_data, {}
        for papel in PAPEIS_EDITAVEIS:
            ajuste = {}
            if dados.get(f"kit_{papel}_equipamento"):
                ajuste["equipamento"] = dados[f"kit_{papel}_equipamento"].pk
            if dados.get(f"kit_{papel}_qtd") is not None:
                ajuste["quantidade"] = dados[f"kit_{papel}_qtd"]
            if ajuste:
                ajustes[papel] = ajuste
        ajustes["extras"] = [
            {"equipamento": dados[f"extra_{n}_equipamento"].pk, "quantidade": dados[f"extra_{n}_qtd"]}
            for n in range(self.n_extras)
            if dados.get(f"extra_{n}_equipamento") and dados.get(f"extra_{n}_qtd")
        ]
        return ajustes

    def save(self, commit=True):
        proposta = super().save(commit=False)
        proposta.desconto, proposta.desconto_pct = self.cleaned_data.get("desconto_texto") or (None, None)
        proposta.ajustes_kit = self.ajustes_kit()
        if commit:
            proposta.save()
        return proposta


def _rotulo_com_preco(equipamento):
    preco = f" · R$ {formatar_reais(equipamento.preco_referencia)}" if equipamento.preco_referencia is not None else ""
    return f"{equipamento.descricao} · {equipamento.distribuidor}{preco}"


# ---------- Emissão e versões (fatia v2.7, D31)

class AceiteForm(forms.Form):
    data_aceite = forms.DateField(label="Data do aceite", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))


class DesfazerAceiteForm(forms.Form):
    motivo = forms.CharField(label="Por que desfazer o aceite?", widget=forms.Textarea(attrs={"rows": 2}))


class PerdaForm(forms.Form):
    motivo_perda = forms.ChoiceField(label="Motivo", choices=Proposta.MotivoPerda.choices)
    obs_perda = forms.CharField(label="Observação (opcional)", required=False, widget=forms.Textarea(attrs={"rows": 2}))
