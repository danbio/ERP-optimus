import re
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from clientes.models import UnidadeConsumidora
from core.models import ConfigEmpresa
from core.pdf import ErroPDF, html_para_pdf

from .forms import (
    CotacaoForm,
    EquipamentoForm,
    FaturaReferenciaForm,
    ItemKitForm,
    ItensCotadosFormSet,
    PremissasForm,
    PropostaForm,
)
from .models import Cotacao, Equipamento, FaturaReferencia, FioBEscalonamento, ItemKit, Proposta
from .services import graficos
from .services.calculo import EntradaCalculo, calcular, fiob_fallback
from .services.pdf import ErroAnexo, contar_paginas, ler_cores, mesclar_anexo

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
    if uc.municipio is None:
        return None, "Escolha o município da unidade consumidora (Clientes → ficha do cliente → UC)."
    if not uc.municipio.irradiacao:
        return None, f"Cadastre a irradiação de {uc.municipio} (Admin → Municípios)."

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
        irradiacao=uc.municipio.irradiacao,
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


def _linhas_do_kit(proposta):
    return [
        {
            "tipo": item.tipo, "descricao": item.descricao, "modelo": item.modelo,
            "quantidade": item.quantidade, "potencia_w": item.potencia_w,
        }
        for item in proposta.itens_kit.all()
    ]


def _recalcular_e_salvar(proposta):
    linhas = _linhas_do_kit(proposta)
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


# ---------------------------------------------------------------- PDF (fatia 5)

PAGINAS_FIXAS = 7  # capa, resumo, fatura, geração, financeiro, técnica, investimento
ANOS_DA_TABELA = [1, 2, 3, 5, 10, 15, 20, 25]
LIGACAO_POR_EXTENSO = {"mono": "monofásica", "bi": "bifásica", "tri": "trifásica"}


def _linhas_de_texto(texto):
    return [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]


def _etapas(texto):
    """'Título | descrição' por linha → [{"titulo": ..., "descricao": ...}]."""
    etapas = []
    for linha in _linhas_de_texto(texto):
        titulo, _, descricao = linha.partition("|")
        etapas.append({"titulo": titulo.strip(), "descricao": descricao.strip()})
    return etapas


def _texto_fiob(tabela, ano_conexao):
    """Ex.: '75% (2027), 90% (2028) e 100% (2029 em diante)'."""
    if not tabela:
        return ""
    ultimo_ano = max(tabela)
    partes = []
    ano = ano_conexao
    while ano < ultimo_ano and tabela.get(ano, 0) < tabela[ultimo_ano]:
        partes.append(f"{tabela.get(ano, 0) * 100:.0f}% ({ano})")
        ano += 1
    partes.append(f"{tabela[ultimo_ano] * 100:.0f}% ({max(ano, ano_conexao)} em diante)")
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " e " + partes[-1]


def _paginas_da_fatura(fatura):
    """Bytes e número de páginas do PDF da fatura, ou (None, 0) se não houver arquivo."""
    if not fatura.arquivo:
        return None, 0
    with fatura.arquivo.open("rb") as arquivo:
        conteudo = arquivo.read()
    return conteudo, contar_paginas(conteudo)


def _contexto_documento(proposta, para_pdf, n_paginas_anexo):
    linhas = _linhas_do_kit(proposta)
    entrada, erro = _montar_entrada(proposta.uc, proposta.fatura, proposta.investimento, proposta.premissas, linhas)
    if erro:
        return None, erro
    resultado = calcular(entrada)

    estatico = Path(settings.BASE_DIR) / "static"
    cores = ler_cores(estatico / "css" / "tokens.css")
    premissas = proposta.premissas
    fatura = proposta.fatura
    emissao = proposta.emissao or timezone.localdate()
    empresa = ConfigEmpresa.obter()

    meses = [
        {"mes": mes, "geracao": g, "consumo": c, "saldo": g - c}
        for mes, g, c in zip(graficos.MESES, resultado.geracao_mensal, resultado.consumo_mensal)
    ]
    fluxo_tabela = [linha for linha in resultado.fluxo if linha["ano"] in ANOS_DA_TABELA]
    modulos = [l for l in linhas if l["tipo"] == ItemKit.Tipo.MODULO]

    return {
        "proposta": proposta,
        "empresa": empresa,
        "cliente": proposta.cliente,
        "uc": proposta.uc,
        "fatura": fatura,
        "itens_kit": proposta.itens_kit.all(),
        "r": resultado,
        "kwp": entrada.kwp,
        "kw_ca": entrada.kw_ca,
        "razao_cc_ca": entrada.kwp / entrada.kw_ca,
        "qtd_modulos": sum(l["quantidade"] for l in modulos),
        "potencia_modulo": modulos[0]["potencia_w"] if modulos else None,
        "geracao_media": resultado.geracao_anual / 12,
        "consumo_medio": resultado.consumo_anual / 12,
        "media_diaria": fatura.kwh / fatura.dias_ciclo,
        "fiob_kwh": entrada.fiob_kwh,
        "fiob_informado": entrada.fiob_informado,
        "texto_fiob": _texto_fiob(entrada.fiob_pct_por_ano, premissas["ano_conexao"]),
        "ligacao": LIGACAO_POR_EXTENSO.get(proposta.uc.ligacao, ""),
        "disponibilidade_kwh": entrada.disponibilidade_kwh,
        "fonte_irradiacao": proposta.uc.municipio.fonte_irradiacao,
        "pct": {chave: valor * 100 for chave, valor in premissas.items() if isinstance(valor, float)},
        "premissas": premissas,
        "meses": meses,
        "fluxo_tabela": fluxo_tabela,
        "fluxo_final": resultado.fluxo[-1],
        "economia_total": sum(linha["economia"] for linha in resultado.fluxo),
        "grafico_geracao": graficos.grafico_geracao_consumo(resultado.geracao_mensal, resultado.consumo_mensal, cores),
        "grafico_fluxo": graficos.grafico_fluxo_acumulado(resultado.fluxo, cores),
        "beneficios": _linhas_de_texto(proposta.beneficios),
        "escopo": _linhas_de_texto(proposta.escopo),
        "etapas": _etapas(empresa.etapas_padrao if empresa else ""),
        "emissao": emissao,
        "validade_ate": emissao + timezone.timedelta(days=proposta.validade_dias),
        "paginas_anexo": range(1, n_paginas_anexo + 1),
        "n_paginas_anexo": n_paginas_anexo,
        "total_paginas": PAGINAS_FIXAS + n_paginas_anexo,
        "base_estatico": estatico.as_uri() if para_pdf else "/" + settings.STATIC_URL.strip("/"),
        "para_pdf": para_pdf,
    }, None


def preview(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        _, n_paginas_anexo = _paginas_da_fatura(proposta.fatura)
    except ErroAnexo as erro:
        return HttpResponse(str(erro), status=422, content_type="text/plain; charset=utf-8")
    contexto, erro = _contexto_documento(proposta, para_pdf=False, n_paginas_anexo=n_paginas_anexo)
    if erro:
        return HttpResponse(erro, status=422, content_type="text/plain; charset=utf-8")
    return render(request, "propostas/pdf/proposta.html", contexto)


def gerar_pdf(proposta):
    """Bytes do PDF completo (proposta + Anexo I). Usado pela view e, na fatia 6, pela emissão."""
    pdf_fatura, n_paginas_anexo = _paginas_da_fatura(proposta.fatura)
    contexto, erro = _contexto_documento(proposta, para_pdf=True, n_paginas_anexo=n_paginas_anexo)
    if erro:
        raise ErroPDF(erro)
    pdf = html_para_pdf(render_to_string("propostas/pdf/proposta.html", contexto))
    if pdf_fatura:
        pdf = mesclar_anexo(pdf, pdf_fatura)
    return pdf


def pdf(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        conteudo = gerar_pdf(proposta)
    except (ErroPDF, ErroAnexo) as erro:
        return HttpResponse(str(erro), status=422, content_type="text/plain; charset=utf-8")
    nome = f"Proposta_{proposta.numero}_v{proposta.versao}_{proposta.cliente.nome}.pdf".replace(" ", "_")
    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="{nome}"'
    return resposta


# ---------- Catálogo solar e memória de cotações (fatia v2.4, D28) ----------

ABAS_CATALOGO = [
    ("propostas:solar_equipamentos", "Equipamentos"),
    ("propostas:solar_cotacoes", "Cotações de kit"),
]


def solar_equipamentos(request):
    tipo = request.GET.get("tipo", Equipamento.Tipo.MODULO)
    distribuidor = request.GET.get("distribuidor", "")
    busca = " ".join(request.GET.get("busca", "").split())
    equipamentos = Equipamento.objects.all()
    if tipo:
        equipamentos = equipamentos.filter(tipo=tipo)
    if distribuidor:
        equipamentos = equipamentos.filter(distribuidor=distribuidor)
    for palavra in busca.split():
        equipamentos = equipamentos.filter(
            Q(descricao__icontains=palavra) | Q(codigo__icontains=palavra) | Q(fabricante__icontains=palavra)
        )
    return render(request, "propostas/catalogo/equipamentos.html", {
        "abas": ABAS_CATALOGO,
        "equipamentos": equipamentos,
        "tipos": Equipamento.Tipo.choices,
        "distribuidores": Equipamento.objects.order_by("distribuidor").values_list("distribuidor", flat=True).distinct(),
        "tipo": tipo, "distribuidor": distribuidor, "busca": busca,
    })


def solar_equipamento(request, pk=None):
    equipamento = get_object_or_404(Equipamento, pk=pk) if pk else None
    form = EquipamentoForm(request.POST or None, request.FILES or None, instance=equipamento)
    if request.method == "POST" and form.is_valid():
        equipamento = form.save()
        messages.success(request, f"{equipamento.descricao} salvo.")
        return redirect(f"{reverse('propostas:solar_equipamentos')}?tipo={equipamento.tipo}")
    return render(request, "propostas/catalogo/equipamento.html", {
        "abas": ABAS_CATALOGO, "form": form, "equipamento": equipamento,
    })


def solar_cotacoes(request):
    dias_velho = ConfigEmpresa.obter().dias_preco_velho
    return render(request, "propostas/catalogo/cotacoes.html", {
        "abas": ABAS_CATALOGO,
        "referencias": Cotacao.referencias(),
        "cotacoes": Cotacao.objects.all()[:200],
        "dias_velho": dias_velho,
    })


def _ligar_itens_ao_catalogo(cotacao):
    """Cada item fica ligado ao equipamento do mesmo distribuidor e código; sem correspondência, sem vínculo."""
    for item in cotacao.itens.all():
        equipamento = None
        if item.codigo:
            equipamento = Equipamento.objects.filter(
                distribuidor__iexact=cotacao.distribuidor, codigo__iexact=item.codigo,
            ).first()
        if item.equipamento_id != (equipamento.pk if equipamento else None):
            item.equipamento = equipamento
            item.save(update_fields=["equipamento"])


def solar_cotacao(request, pk=None):
    cotacao = get_object_or_404(Cotacao, pk=pk) if pk else None
    form = CotacaoForm(request.POST or None, request.FILES or None, instance=cotacao,
                       initial=None if cotacao else {"data": timezone.localdate()})
    itens = ItensCotadosFormSet(request.POST or None, instance=cotacao or Cotacao(), prefix="item")
    if request.method == "POST" and form.is_valid() and itens.is_valid():
        cotacao = form.save()
        itens.instance = cotacao
        itens.save()
        _ligar_itens_ao_catalogo(cotacao)
        rs_wp = f"{cotacao.rs_por_wp:.2f}".replace(".", ",")
        messages.success(request, f"Cotação salva: R$ {rs_wp}/Wp com frete.")
        return redirect("propostas:solar_cotacoes")
    return render(request, "propostas/catalogo/cotacao.html", {
        "abas": ABAS_CATALOGO, "form": form, "itens": itens, "cotacao": cotacao,
    })
