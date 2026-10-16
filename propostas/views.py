import re

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from clientes.models import UnidadeConsumidora
from core.models import ConfigEmpresa

from .forms import FaturaReferenciaForm, ItemKitForm, PremissasForm, PropostaForm
from .models import FaturaReferencia, FioBEscalonamento, IrradiacaoMunicipio, ItemKit, Proposta
from .services.calculo import EntradaCalculo, calcular, fiob_fallback

LINHA_KIT_RE = re.compile(r"^kit-(\d+)-tipo$")


def _parse_kit_linhas(post):
    """Lê as linhas do kit do POST (convenção de nomes kit-<indice>-campo). Linhas sem
    descrição preenchida são ignoradas (linha em branco, não é um item real)."""
    indices = {int(m.group(1)) for chave in post if (m := LINHA_KIT_RE.match(chave))}
    linhas = []
    valido = True
    for indice in sorted(indices):
        prefixo = f"kit-{indice}"
        if not post.get(f"{prefixo}-descricao", "").strip():
            continue
        formulario = ItemKitForm(post, prefix=prefixo)
        if formulario.is_valid():
            linhas.append(formulario.cleaned_data)
        else:
            valido = False
    return linhas, valido


def _bind_kit_forms(post):
    indices = {int(m.group(1)) for chave in post if (m := LINHA_KIT_RE.match(chave))}
    return [ItemKitForm(post, prefix=f"kit-{indice}") for indice in sorted(indices)]


def _kwp_kw_ca(linhas):
    kwp = sum(l["quantidade"] * (l["potencia_w"] or 0) for l in linhas if l["tipo"] == ItemKit.Tipo.MODULO)
    kw_ca = sum(l["quantidade"] * (l["potencia_w"] or 0) for l in linhas if l["tipo"] == ItemKit.Tipo.INVERSOR)
    return kwp / 1000, kw_ca / 1000


def _montar_entrada(uc, fatura, investimento, premissas, linhas):
    irradiacao = IrradiacaoMunicipio.objects.filter(municipio=uc.municipio, uf=uc.uf).first()
    if irradiacao is None:
        return None, f"Cadastre a irradiação de {uc.municipio}/{uc.uf} (Admin → Irradiação do município)."

    kwp, kw_ca = _kwp_kw_ca(linhas)
    if kwp == 0 or kw_ca == 0:
        return None, "Adicione ao menos um módulo e um inversor no kit para ver os resultados."

    fiob_informado = fatura.tusd_fiob_kwh is not None
    if fiob_informado:
        fiob_kwh = float(fatura.tusd_fiob_kwh)
    else:
        fiob_kwh = fiob_fallback(
            float(fatura.valor_distribuicao), float(fatura.kwh), float(fatura.valor_total), float(fatura.impostos)
        )

    fiob_pct_por_ano = {f.ano: float(f.percentual) / 100 for f in FioBEscalonamento.objects.all()}
    digitos_doc = re.sub(r"\D", "", uc.cliente.cpf_cnpj or "")
    cliente_pessoa_juridica = len(digitos_doc) > 11

    entrada = EntradaCalculo(
        kwp=kwp,
        kw_ca=kw_ca,
        irradiacao=irradiacao.valores,
        kwh_fatura=float(fatura.kwh),
        dias_ciclo=fatura.dias_ciclo,
        tarifa=float(fatura.tarifa_kwh),
        fiob_kwh=fiob_kwh,
        disponibilidade_kwh=uc.disponibilidade_kwh,
        investimento=float(investimento),
        fiob_pct_por_ano=fiob_pct_por_ano,
        premissas=premissas,
        classe=uc.classe,
        cliente_pessoa_juridica=cliente_pessoa_juridica,
        fiob_informado=fiob_informado,
    )
    return entrada, None


def _contexto_resultados(uc, fatura, investimento_bruto, premissas, linhas):
    if not uc or not fatura:
        return {"mensagem": "Selecione a UC e a fatura para ver os resultados."}
    try:
        investimento = float(str(investimento_bruto).replace(",", "."))
    except (TypeError, ValueError):
        return {"mensagem": "Informe o investimento para ver os resultados."}
    if not premissas:
        return {"mensagem": "Preencha as premissas para ver os resultados."}
    if not linhas:
        return {"mensagem": "Adicione ao menos um módulo e um inversor no kit para ver os resultados."}

    entrada, erro = _montar_entrada(uc, fatura, investimento, premissas, linhas)
    if erro:
        return {"mensagem": erro}

    resultado = calcular(entrada)
    return {
        "resultado": resultado,
        "kwp": entrada.kwp,
        "investimento": entrada.investimento,
        "geracao_media_mensal": resultado.geracao_anual / 12,
        "consumo_media_mensal": resultado.consumo_anual / 12,
    }


def _recalcular_e_salvar(proposta):
    linhas = [
        {
            "tipo": item.tipo, "descricao": item.descricao, "modelo": item.modelo,
            "quantidade": item.quantidade, "potencia_w": item.potencia_w,
        }
        for item in proposta.itens_kit.all()
    ]
    entrada, erro = _montar_entrada(proposta.uc, proposta.fatura, proposta.investimento, proposta.premissas, linhas)
    if erro:
        return
    resultado = calcular(entrada)
    Proposta.objects.filter(pk=proposta.pk).update(resultados={
        "geracao_anual": resultado.geracao_anual,
        "consumo_anual": resultado.consumo_anual,
        "cobertura": resultado.cobertura,
        "economia_mensal_ano1": resultado.economia_mensal_ano1,
        "payback_meses": resultado.payback_meses,
        "rs_por_wp": resultado.rs_por_wp,
        "alertas": resultado.alertas,
    })


def lista(request):
    propostas = Proposta.objects.select_related("uc", "uc__cliente").all()
    status = request.GET.get("status")
    if status:
        propostas = propostas.filter(status=status)
    busca = request.GET.get("busca")
    if busca:
        propostas = propostas.filter(uc__cliente__nome__icontains=busca)
    return render(request, "propostas/lista.html", {
        "propostas": propostas,
        "status_choices": Proposta.Status.choices,
    })


def formulario(request, pk=None):
    proposta = get_object_or_404(Proposta, pk=pk) if pk else None
    config = ConfigEmpresa.obter()

    if proposta and proposta.status != Proposta.Status.RASCUNHO:
        return render(request, "propostas/somente_rascunho.html", {"proposta": proposta})

    if request.method == "POST":
        proposta_form = PropostaForm(request.POST, instance=proposta)
        premissas_form = PremissasForm(request.POST)
        linhas, linhas_validas = _parse_kit_linhas(request.POST)

        if proposta_form.is_valid() and premissas_form.is_valid() and linhas_validas and linhas:
            salvo = proposta_form.save(commit=False)
            if not proposta:
                salvo.numero = Proposta.proximo_numero()
                salvo.versao = 1
                salvo.status = Proposta.Status.RASCUNHO
            salvo.premissas = premissas_form.cleaned_data
            salvo.save()
            salvo.itens_kit.all().delete()
            for ordem, linha in enumerate(linhas):
                ItemKit.objects.create(proposta=salvo, ordem=ordem, **linha)
            _recalcular_e_salvar(salvo)
            return redirect("propostas:editar", pk=salvo.pk)

        kit_forms = _bind_kit_forms(request.POST) or [ItemKitForm(prefix="kit-0")]
        contexto_resultados = {"mensagem": "Corrija os campos destacados e salve para ver os resultados."}

    else:
        if proposta:
            proposta_form = PropostaForm(instance=proposta)
            premissas_form = PremissasForm(initial=proposta.premissas)
            kit_forms = [
                ItemKitForm(initial={
                    "tipo": item.tipo, "descricao": item.descricao, "modelo": item.modelo,
                    "quantidade": item.quantidade, "potencia_w": item.potencia_w,
                }, prefix=f"kit-{indice}")
                for indice, item in enumerate(proposta.itens_kit.all())
            ]
            linhas_atuais = [
                {
                    "tipo": i.tipo, "descricao": i.descricao, "modelo": i.modelo,
                    "quantidade": i.quantidade, "potencia_w": i.potencia_w,
                }
                for i in proposta.itens_kit.all()
            ]
            contexto_resultados = _contexto_resultados(
                proposta.uc, proposta.fatura, proposta.investimento, proposta.premissas, linhas_atuais
            )
        else:
            proposta_form = PropostaForm(initial={
                "validade_dias": config.validade_padrao_dias if config else 15,
                "beneficios": config.beneficios_padrao if config else "",
                "escopo": config.escopo_padrao if config else "",
                "texto_sobre": config.texto_sobre if config else "",
                "uc": request.GET.get("uc"),
                "fatura": request.GET.get("fatura"),
            })
            premissas_form = PremissasForm(initial=config.premissas_padrao if config else {})
            kit_forms = []
            contexto_resultados = {
                "mensagem": "Selecione a UC e a fatura, informe o investimento e adicione o kit para ver os resultados."
            }

    contexto = {
        "proposta": proposta,
        "proposta_form": proposta_form,
        "premissas_form": premissas_form,
        "kit_forms": kit_forms,
        "proximo_indice_kit": len(kit_forms),
        "numero_previsto": proposta.numero if proposta else Proposta.proximo_numero(),
    }
    contexto.update(contexto_resultados)
    return render(request, "propostas/formulario.html", contexto)


def recalcular(request):
    post = request.POST
    uc = UnidadeConsumidora.objects.filter(pk=post.get("uc")).first()
    fatura = FaturaReferencia.objects.filter(pk=post.get("fatura")).first()
    premissas_form = PremissasForm(post)
    premissas = premissas_form.cleaned_data if premissas_form.is_valid() else {}
    linhas, _ = _parse_kit_linhas(post)

    contexto = _contexto_resultados(uc, fatura, post.get("investimento"), premissas, linhas)
    return render(request, "propostas/_resultados.html", contexto)


def kit_nova_linha(request):
    indice = int(request.GET.get("proximo_indice", 0))
    formulario_linha = ItemKitForm(prefix=f"kit-{indice}")
    return render(request, "propostas/_kit_linha.html", {
        "form": formulario_linha,
        "indice_seguinte": indice + 1,
    })


def fatura_novo(request):
    proximo = request.GET.get("next") or reverse("propostas:nova")
    if request.method == "POST":
        form = FaturaReferenciaForm(request.POST, request.FILES)
        if form.is_valid():
            fatura = form.save()
            return redirect(f"{proximo}?fatura={fatura.pk}")
    else:
        form = FaturaReferenciaForm(initial={"uc": request.GET.get("uc")})
    return render(request, "clientes/form_simples.html", {
        "form": form,
        "titulo": "Nova fatura de referência",
    })
