"""Nova proposta em 4 passos (fatia v2.5, D29): cliente → consumo → sistema e preço → proposta."""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from clientes.models import Cliente, UnidadeConsumidora
from core import ia
from core.forms import AcompanhamentoForm
from core.models import ConfigEmpresa
from core.permissoes import eh_gestor
from core.validacoes import formatar_reais, nomes_iguais

from ..forms import Passo1Form, Passo2Form, Passo3Form
from ..models import FaturaReferencia, Proposta
from ..montagem import gravar_resultado, impedimentos_de_emissao, montar
from ..services import leitura_ia


# ---------- Proposta v2: os 4 passos (fatia v2.5, D29) ----------

PASSOS = [(1, "Cliente"), (2, "Consumo"), (3, "Sistema e preço"), (4, "Proposta")]
FORM_DO_PASSO = {2: Passo2Form, 3: Passo3Form}


def _modo_cliente(request):
    return bool(request.session.get("modo_cliente"))


def _form_do_passo(n, proposta, dados=None, arquivos=None, previa=False):
    if n == 1:
        cliente = proposta.cliente if proposta else None
        inicial = {}
        if cliente:
            inicial = {"nome": cliente.nome, "telefone": cliente.telefone_formatado, "municipio": proposta.municipio_id or cliente.municipio_id,
                       "cpf_cnpj": cliente.cpf_cnpj_formatado, "ligacao": proposta.ligacao,
                       "tipo_tarifa": proposta.tipo_tarifa_id}
        return Passo1Form(dados, initial=inicial)
    if n == 2:
        config = ConfigEmpresa.obter()
        inicial = {} if proposta.origem_consumo else {"origem_consumo": Proposta.OrigemConsumo.CONTA}
        return Passo2Form(dados, arquivos, instance=proposta, perfis=config.perfis_simultaneidade, initial=inicial,
                          config=config, exigir_confirmacao=not previa)
    if n == 3:
        inicial = {} if proposta.orientacao else {"orientacao": Proposta.Orientacao.NORTE}
        return Passo3Form(dados, instance=proposta, initial=inicial)
    return None


def _contexto_passos(request, proposta, n, form=None, m=None):
    contexto = {
        "proposta": proposta,
        "passo": n,
        "passos": PASSOS,
        "form": form,
        "m": m if m is not None else (montar(proposta) if proposta else None),
        "modo_cliente": _modo_cliente(request),
        "aviso_estimativa": ConfigEmpresa.obter().aviso_estimativa,
    }
    if n == 3 and form is not None:
        contexto["kit_editavel"] = form.linhas_do_kit(contexto["m"])
        contexto["kit_extras"] = form.extras()
    if n == 4 and contexto["m"]:
        contexto["impedimentos"] = impedimentos_de_emissao(contexto["m"], proposta)
    if n == 4 and proposta:
        contexto["acompanhamento_form"] = AcompanhamentoForm(objeto=proposta, gestor=eh_gestor(request.user))
    return contexto


def _cliente_novo_ou_existente(request, dados):
    """Cliente de uma proposta nova: o já cadastrado com o mesmo CPF/CNPJ ou telefone, ou um novo.

    Nunca troca o nome de uma ficha existente (A04): se o nome digitado é outro, pergunta se é a
    mesma pessoa. Devolve (cliente, [(campo, erro)]).
    """
    por_cpf = Cliente.objects.filter(cpf_cnpj=dados["cpf_cnpj"]).first() if dados["cpf_cnpj"] else None
    por_telefone = Cliente.objects.filter(telefone=dados["telefone"]).first()
    if not por_cpf and por_telefone and dados["cpf_cnpj"] and por_telefone.cpf_cnpj:
        return None, [("cpf_cnpj", f"Este telefone já é de {por_telefone.nome}, com outro CPF/CNPJ. "
                                   "Confira o CPF/CNPJ e o telefone.")]
    existente = por_cpf or por_telefone
    resposta = dados.get("mesma_pessoa")
    if existente and (nomes_iguais(existente.nome, dados["nome"]) or resposta == "sim"):
        if dados["cpf_cnpj"] and not existente.cpf_cnpj:
            existente.cpf_cnpj = dados["cpf_cnpj"]
        if not existente.municipio_id:
            existente.municipio = dados["municipio"]
        existente.save()
        messages.success(request, f"{existente.nome} já estava cadastrado: usamos a ficha existente.")
        return existente, []
    if existente and resposta != "nao":
        pelo = "CPF/CNPJ" if por_cpf else "telefone"
        local = f", de {existente.municipio.nome}" if existente.municipio_id else ""
        return None, [("mesma_pessoa", f"Já existe {existente.nome}{local}, com este {pelo}. É a mesma pessoa?")]
    if por_cpf:  # outra pessoa não pode ter o mesmo CPF/CNPJ
        return None, [("cpf_cnpj", f"Este CPF/CNPJ já é de {por_cpf.nome}. Confira os números.")]
    cliente = Cliente.objects.create(
        nome=dados["nome"], telefone=dados["telefone"], municipio=dados["municipio"], cpf_cnpj=dados["cpf_cnpj"],
    )
    return cliente, []


def _atualizar_cliente(cliente, dados, proposta):
    """Correção de nome, telefone ou CPF no passo 1. Devolve [(campo, erro)].

    Se o cliente tem outras propostas, nome e telefone só mudam na ficha dele (A04).
    """
    if dados["cpf_cnpj"]:
        dono = Cliente.objects.filter(cpf_cnpj=dados["cpf_cnpj"]).exclude(pk=cliente.pk).first()
        if dono:
            return [("cpf_cnpj", f"Este CPF/CNPJ já é de {dono.nome}.")]
    mudou = cliente.nome != dados["nome"] or cliente.telefone != dados["telefone"]
    outras = cliente.propostas.exclude(pk=proposta.pk)
    if proposta.numero:
        outras = outras.exclude(numero=proposta.numero)
    if mudou and outras.exists():
        return [("nome", "Este cliente tem outras propostas. Corrija nome e telefone na ficha do cliente "
                         "(menu Clientes).")]
    cliente.nome, cliente.telefone = dados["nome"], dados["telefone"]
    if dados["cpf_cnpj"]:
        cliente.cpf_cnpj = dados["cpf_cnpj"]
    if not cliente.municipio_id:
        cliente.municipio = dados["municipio"]
    cliente.save()
    return []


def proposta_nova(request):
    return proposta_passo(request, None, 1)


def proposta_passo(request, pk, n):
    if n not in (1, 2, 3, 4):
        raise Http404("Passo inexistente.")
    proposta = get_object_or_404(Proposta, pk=pk) if pk else None
    if proposta and proposta.status != Proposta.Status.RASCUNHO:
        return redirect("propostas:detalhe", pk=proposta.pk)
    if not proposta and n != 1:
        return redirect("propostas:nova")

    if n == 4:
        if request.method == "POST" and request.POST.get("prazo", "").isdigit():
            proposta.prazo_comparacao = int(request.POST["prazo"])
            proposta.save(update_fields=["prazo_comparacao"])
            return redirect("propostas:passo", pk=proposta.pk, n=4)
        return render(request, "propostas/v2/passos.html", _contexto_passos(request, proposta, 4))

    if request.method == "POST" and n == 3 and _modo_cliente(request):
        # O preço não vai ao navegador no modo cliente (A29): gravar agora apagaria custo e mão de obra.
        messages.error(request, "Saia do modo cliente para alterar o sistema e o preço.")
        return redirect("propostas:passo", pk=proposta.pk, n=3)
    form = _form_do_passo(n, proposta, request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid() and n == 3:
        _conferir_desconto(form)
    if request.method == "POST" and form.is_valid():
        if n in (1, 2):
            gravar = _gravar_passo1 if n == 1 else _gravar_passo2
            proposta, erros = gravar(request, form, proposta)
            if erros:
                for campo, erro in erros:
                    form.add_error(campo, erro)
                return render(request, "propostas/v2/passos.html", _contexto_passos(request, proposta, n, form))
        else:
            form.save()
        proposta.refresh_from_db()
        proposta.passo_atual = max(proposta.passo_atual, n + 1)
        proposta.save(update_fields=["passo_atual"])
        gravar_resultado(proposta, montar(proposta))
        return redirect("propostas:passo", pk=proposta.pk, n=n + 1)
    return render(request, "propostas/v2/passos.html", _contexto_passos(request, proposta, n, form))


def _conferir_desconto(form):
    """O desconto vale só na mão de obra (D18): recusa desconto maior que ela, mesmo a sugerida pelo sistema."""
    m = montar(form.save(commit=False))
    if m.mao_de_obra is None:
        return
    desconto, pct = form.cleaned_data.get("desconto_texto") or (None, None)
    valor = m.mao_de_obra * float(pct) if pct is not None else float(desconto or 0)
    if valor > m.mao_de_obra + 0.005:
        form.add_error("desconto_texto", f"O desconto passa da mão de obra (R$ {formatar_reais(m.mao_de_obra)}).")


def _gravar_passo1(request, form, proposta):
    """Devolve (proposta, [(campo, erro)])."""
    dados = form.cleaned_data
    if proposta:
        cliente = proposta.cliente
        erros = _atualizar_cliente(cliente, dados, proposta)
    else:
        cliente, erros = _cliente_novo_ou_existente(request, dados)
    if erros:
        return proposta, erros
    config = ConfigEmpresa.obter()
    if not proposta:
        proposta = Proposta(
            versao=1, status=Proposta.Status.RASCUNHO,  # sem número até a primeira emissão (A13)
            validade_dias=config.validade_padrao_dias, beneficios=config.beneficios_padrao,
            escopo=config.escopo_padrao, texto_sobre=config.texto_sobre,
            perfil_simultaneidade=(config.perfis_simultaneidade[0]["nome"] if config.perfis_simultaneidade else ""),
            vendedor=request.user if request.user.is_authenticated else None,  # D46
        )
    proposta.cliente = cliente
    proposta.municipio = dados["municipio"]
    proposta.ligacao = dados["ligacao"]
    proposta.tipo_tarifa = dados["tipo_tarifa"]
    proposta.save()
    if proposta.uc and proposta.uc.municipio_id != proposta.municipio_id:
        proposta.uc.municipio = proposta.municipio  # na v2 a instalação fica no município do passo 1
        proposta.uc.save(update_fields=["municipio"])
    return proposta, []


def _gravar_passo2(request, form, proposta):
    """Grava o consumo. Com fatura, cria UC e fatura e a proposta vira confirmada (D29). Devolve (proposta, [(campo, erro)])."""
    dados = form.cleaned_data
    proposta = form.save(commit=False)
    if proposta.origem_consumo != Proposta.OrigemConsumo.FATURA:
        proposta.nivel = Proposta.Nivel.ESTIMATIVA
        proposta.uc = None  # sem fatura, não há UC confirmada; o município vem do passo 1
        proposta.fatura = None
        proposta.save()
        return proposta, []

    cliente = proposta.cliente
    if dados["cpf_cnpj"]:  # vazio é aceito aqui; a emissão exige (D38)
        dono = Cliente.objects.filter(cpf_cnpj=dados["cpf_cnpj"]).exclude(pk=cliente.pk).first()
        if dono:
            return proposta, [("cpf_cnpj", f"Este CPF/CNPJ já é de {dono.nome}.")]
        if cliente.cpf_cnpj and cliente.cpf_cnpj != dados["cpf_cnpj"]:
            # A fatura pode estar no nome de outra pessoa (cônjuge, empresa): não troca o documento do cliente (D42).
            return proposta, [("cpf_cnpj", f"{cliente.nome} já tem o CPF/CNPJ {cliente.cpf_cnpj_formatado}. "
                                           "Se a fatura é de outro titular, cadastre-o como cliente; "
                                           "se o cadastro está errado, corrija na ficha do cliente.")]
        cliente.cpf_cnpj = dados["cpf_cnpj"]
        cliente.save(update_fields=["cpf_cnpj"])
    if not cliente.logradouro and dados["endereco"]:
        # Cliente sem endereço recebe o da fatura; com endereço, o dele fica (D42, H15).
        cliente.logradouro = dados["endereco"][:200]
        cliente.save(update_fields=["logradouro"])
    uc = UnidadeConsumidora.objects.filter(cliente=cliente, numero_uc=dados["numero_uc"]).first() or UnidadeConsumidora(
        cliente=cliente, numero_uc=dados["numero_uc"])
    uc.endereco = dados["endereco"]
    uc.municipio = proposta.municipio or cliente.municipio
    if uc.municipio and uc.municipio.distribuidora:
        uc.concessionaria = uc.municipio.distribuidora.nome  # D47
    elif not uc.concessionaria:
        uc.concessionaria = proposta.tipo_tarifa.distribuidora
    uc.classe = proposta.tipo_tarifa.tipo[:2]
    uc.ligacao = proposta.ligacao
    uc.save()
    fatura = proposta.fatura if proposta.fatura and proposta.fatura.uc_id == uc.pk else FaturaReferencia(uc=uc)
    fatura.competencia = dados["competencia"]
    fatura.kwh = dados["fatura_kwh"]
    fatura.dias_ciclo = dados["dias_ciclo"]
    fatura.valor_total = dados["valor_fatura"]
    if dados.get("arquivo_fatura"):
        fatura.arquivo = dados["arquivo_fatura"]
    fatura.save()
    proposta.uc = uc
    proposta.fatura = fatura
    proposta.nivel = Proposta.Nivel.CONFIRMADA
    proposta.save()
    return proposta, []


@require_POST
def proposta_previa(request, pk, n):
    """Recalcula enquanto o vendedor digita (HTMX): devolve o resumo e os números do passo, sem gravar."""
    if n not in (1, 2, 3, 4):
        raise Http404("Passo inexistente.")
    proposta = get_object_or_404(Proposta, pk=pk)
    form = _form_do_passo(n, proposta, request.POST, previa=True)
    if n == 3 and _modo_cliente(request):
        pass  # A29: sem os campos de preço, a prévia mostraria outro investimento; fica a gravada
    elif n in (2, 3) and form.is_valid():
        proposta = form.save(commit=False)
        if n == 2 and proposta.origem_consumo == Proposta.OrigemConsumo.FATURA:
            proposta.fatura = FaturaReferencia(
                kwh=form.cleaned_data.get("fatura_kwh") or 0, dias_ciclo=form.cleaned_data.get("dias_ciclo") or 0,
            )
    else:
        proposta = get_object_or_404(Proposta, pk=pk)
    return render(request, "propostas/v2/_previa.html", _contexto_passos(request, proposta, n))


CAMPOS_DA_FATURA = ["numero_uc", "endereco", "competencia", "fatura_kwh", "dias_ciclo", "valor_fatura", "cpf_cnpj"]


@require_POST
def ler_fatura(request, pk):
    """IA lê o PDF da fatura e preenche os campos do passo 2 (D35, D37). Não grava: o vendedor confere e salva."""
    proposta = get_object_or_404(Proposta, pk=pk, status=Proposta.Status.RASCUNHO)
    valores = {campo: request.POST.get(campo, "") for campo in CAMPOS_DA_FATURA}
    contexto = {"leitura_avisos": []}
    arquivo = request.FILES.get("arquivo_fatura")
    if not arquivo:
        contexto["leitura_erro"] = "Escolha o PDF da fatura antes de pedir a leitura."
    else:
        try:
            lido = leitura_ia.campos_da_fatura(
                ia.ler_pdf(arquivo.read(), leitura_ia.INSTRUCAO_FATURA, leitura_ia.ESQUEMA_FATURA))
        except ia.ErroLeitura as erro:
            contexto["leitura_erro"] = str(erro)
        else:
            titular = lido.pop("titular")
            valores |= {campo: valor for campo, valor in lido.items() if valor}
            contexto["leitura_ok"] = True
            vazios = [Passo2Form.base_fields[c].label for c in CAMPOS_DA_FATURA
                      if not lido.get(c) and c != "cpf_cnpj"]
            if vazios:
                contexto["leitura_avisos"].append(f"A IA não achou: {', '.join(vazios)}. Preencha à mão.")
            if not valores.get("cpf_cnpj"):  # a fatura costuma esconder parte do CPF (H14)
                contexto["leitura_avisos"].append(
                    "A fatura não traz o CPF ou CNPJ completo. Peça ao cliente: ele é exigido para emitir.")
            if titular and not nomes_iguais(titular, proposta.cliente.nome):
                contexto["leitura_avisos"].append(
                    f"A fatura está no nome de {titular} e o cliente é {proposta.cliente.nome}. Confira.")
    config = ConfigEmpresa.obter()
    contexto["form"] = Passo2Form(instance=proposta, perfis=config.perfis_simultaneidade, config=config,
                                  initial=valores)
    return render(request, "propostas/v2/_campos_fatura.html", contexto)


@require_POST
def alternar_modo_cliente(request):
    request.session["modo_cliente"] = not _modo_cliente(request)
    destino = request.POST.get("voltar", "")
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = reverse("propostas:lista")  # A23: só volta para página do próprio ERP
    return redirect(destino)


def proposta_abrir(request, pk):
    """Rascunho abre no passo em que parou; as outras, no detalhe."""
    proposta = get_object_or_404(Proposta, pk=pk)
    if proposta.status != Proposta.Status.RASCUNHO:
        return redirect("propostas:detalhe", pk=pk)
    return redirect("propostas:passo", pk=pk, n=min(proposta.passo_atual, 4))
