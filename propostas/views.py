import re
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from clientes.models import Cliente, UnidadeConsumidora
from core.models import ConfigEmpresa
from core.pdf import ErroPDF, html_para_pdf
from core.validacoes import formatar_reais, nomes_iguais

from .forms import (
    AceiteForm,
    CotacaoForm,
    DesfazerAceiteForm,
    EquipamentoForm,
    FaturaReferenciaForm,
    ItemKitForm,
    ItensCotadosFormSet,
    Passo1Form,
    Passo2Form,
    Passo3Form,
    PerdaForm,
    PremissasForm,
    PropostaForm,
)
from .models import Cotacao, Equipamento, FaturaReferencia, FioBEscalonamento, ItemKit, Proposta
from . import emissao
from .montagem import gravar_resultado, impedimentos_de_emissao, montar, premissas_da_proposta
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
    propostas = Proposta.objects.select_related("cliente").prefetch_related("itens_kit")
    situacao = request.GET.get("status", "")
    if situacao:
        propostas = propostas.filter(status="emitida" if situacao == "vencida" else situacao)
    busca = " ".join(request.GET.get("busca", "").split())
    if busca:
        filtro = Q(cliente__nome__icontains=busca) | Q(numero__icontains=busca)
        digitos = re.sub(r"\D", "", busca)
        if len(digitos) >= 4:
            filtro |= Q(cliente__telefone__contains=digitos)
        propostas = propostas.filter(filtro)
    propostas = propostas[:200]
    if situacao in ("emitida", "vencida"):  # "vencida" não é gravada: separa na hora (D31)
        propostas = [p for p in propostas if p.situacao == situacao]
    return render(request, "propostas/lista.html", {
        "propostas": propostas,
        "status_choices": Proposta.Status.choices[:2] + [("vencida", "Vencida")] + Proposta.Status.choices[2:],
        "busca": busca,
    })


def formulario(request, pk=None):
    proposta = get_object_or_404(Proposta, pk=pk) if pk else None
    config = ConfigEmpresa.obter()

    if proposta and proposta.status != Proposta.Status.RASCUNHO:
        return redirect("propostas:detalhe", pk=proposta.pk)

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
            salvo.cliente = salvo.uc.cliente
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
    if not fatura or not fatura.arquivo:
        return None, 0
    with fatura.arquivo.open("rb") as arquivo:
        conteudo = arquivo.read()
    return conteudo, contar_paginas(conteudo)


def _contexto_comum(proposta, resultado, premissas, para_pdf, n_paginas_anexo):
    """O que as páginas do PDF usam igual na proposta antiga e na v2."""
    estatico = Path(settings.BASE_DIR) / "static"
    cores = ler_cores(estatico / "css" / "tokens.css")
    emissao = proposta.emissao or timezone.localdate()
    empresa = ConfigEmpresa.obter()
    meses = [
        {"mes": mes, "geracao": g, "consumo": c, "saldo": g - c}
        for mes, g, c in zip(graficos.MESES, resultado.geracao_mensal, resultado.consumo_mensal)
    ]
    return {
        "proposta": proposta,
        "empresa": empresa,
        "cliente": proposta.cliente,
        "uc": proposta.uc,
        "fatura": proposta.fatura,
        "itens_kit": proposta.itens_kit.all(),
        "r": resultado,
        "geracao_media": resultado.geracao_anual / 12,
        "consumo_medio": resultado.consumo_anual / 12,
        "texto_fiob": _texto_fiob(
            {f.ano: float(f.percentual) / 100 for f in FioBEscalonamento.objects.all()}, premissas["ano_conexao"]
        ),
        "pct": {chave: valor * 100 for chave, valor in premissas.items() if isinstance(valor, float)},
        "premissas": premissas,
        "meses": meses,
        "fluxo_tabela": [linha for linha in resultado.fluxo if linha["ano"] in ANOS_DA_TABELA],
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
    }


def _contexto_antigo(proposta, para_pdf, n_paginas_anexo):
    """Proposta da fatia 4/5: tudo vem da UC, da fatura e do kit digitado."""
    linhas = _linhas_do_kit(proposta)
    entrada, erro = _montar_entrada(proposta.uc, proposta.fatura, proposta.investimento, proposta.premissas, linhas)
    if erro:
        return None, erro
    resultado = calcular(entrada)
    fatura = proposta.fatura
    modulos = [l for l in linhas if l["tipo"] == ItemKit.Tipo.MODULO]
    contexto = _contexto_comum(proposta, resultado, proposta.premissas, para_pdf, n_paginas_anexo)
    contexto |= {
        "v2": False,
        "municipio": proposta.uc.municipio,
        "kwp": entrada.kwp,
        "kw_ca": entrada.kw_ca,
        "razao_cc_ca": entrada.kwp / entrada.kw_ca,
        "qtd_modulos": sum(l["quantidade"] for l in modulos),
        "potencia_modulo": modulos[0]["potencia_w"] if modulos else None,
        "media_diaria": fatura.kwh / fatura.dias_ciclo,
        "tarifa_kwh": fatura.tarifa_kwh,
        "base_tarifa": f"fatura {date_format(fatura.competencia, 'b/Y')}",
        "fiob_kwh": entrada.fiob_kwh,
        "fiob_informado": entrada.fiob_informado,
        "texto_fiob": _texto_fiob(entrada.fiob_pct_por_ano, proposta.premissas["ano_conexao"]),
        "ligacao": LIGACAO_POR_EXTENSO.get(proposta.uc.ligacao, ""),
        "disponibilidade_kwh": entrada.disponibilidade_kwh,
        "fonte_irradiacao": proposta.uc.municipio.fonte_irradiacao,
    }
    return contexto, None


def _contexto_v2(proposta, para_pdf, n_paginas_anexo):
    """Proposta dos 4 passos (D30): os números são os mesmos da tela, vindos de montar()."""
    config = ConfigEmpresa.obter()
    m = montar(proposta, config)
    if not m.resultado:
        return None, m.mensagem or "Complete os passos da proposta antes de gerar o PDF."
    tarifa = proposta.tipo_tarifa
    fatura = proposta.fatura
    contexto = _contexto_comum(proposta, m.resultado, premissas_da_proposta(proposta, config), para_pdf, n_paginas_anexo)
    contexto |= {
        "v2": True,
        "m": m,
        "estimativa": proposta.nivel == Proposta.Nivel.ESTIMATIVA,
        "aviso_estimativa": config.aviso_estimativa,
        "municipio": m.municipio,
        "kwp": m.kwp,
        "kw_ca": m.kw_ca,
        "razao_cc_ca": m.sobrecarga,
        "qtd_modulos": m.qtd_modulos,
        "potencia_modulo": m.modulo.potencia_w,
        "media_diaria": fatura.kwh / fatura.dias_ciclo if fatura else m.consumo / 30,
        "tarifa_kwh": m.tarifa_kwh,
        "base_tarifa": f"tarifa {tarifa.get_tipo_display()} vigente da Energisa TO, ANEEL",
        "fiob_kwh": float(tarifa.fiob_kwh),
        "fiob_informado": True,
        "ligacao": LIGACAO_POR_EXTENSO.get(proposta.ligacao, ""),
        "disponibilidade_kwh": m.disponibilidade,
        "fonte_irradiacao": m.municipio.fonte_irradiacao,
        "financiamento": m.financiamento,
        "folga_pct": float(proposta.folga or 0) * 100,
    }
    return contexto, None


def _contexto_documento(proposta, para_pdf, n_paginas_anexo):
    if proposta.eh_antiga:
        return _contexto_antigo(proposta, para_pdf, n_paginas_anexo)
    return _contexto_v2(proposta, para_pdf, n_paginas_anexo)


def preview(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        _, n_paginas_anexo = _paginas_da_fatura(proposta.fatura)
    except ErroAnexo as erro:
        return HttpResponse(str(erro), status=422, content_type="text/plain; charset=utf-8")
    contexto, erro = _contexto_documento(proposta, para_pdf=False, n_paginas_anexo=n_paginas_anexo)
    if erro:
        return HttpResponse(erro, status=422, content_type="text/plain; charset=utf-8")
    contexto["rascunho"] = proposta.status == Proposta.Status.RASCUNHO and not proposta.eh_antiga  # A09
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
    if proposta.status == Proposta.Status.RASCUNHO and not proposta.eh_antiga:
        # A09: o PDF que vai para o cliente é só o da emitida; o rascunho tem a pré-visualização.
        return HttpResponse("Emita a proposta para baixar o PDF. Antes disso, use Pré-visualizar.",
                            status=409, content_type="text/plain; charset=utf-8")
    try:
        if proposta.status != Proposta.Status.RASCUNHO and proposta.pdf:
            with proposta.pdf.open("rb") as arquivo:  # emitida: sempre o PDF guardado na emissão (D31)
                conteudo = arquivo.read()
        else:
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
    if n == 4 and contexto["m"]:
        contexto["impedimentos"] = impedimentos_de_emissao(contexto["m"])
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
    if mudou and cliente.propostas.exclude(numero=proposta.numero).exists():
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
    if proposta and proposta.eh_antiga:
        return redirect("propostas:legado_editar", pk=proposta.pk)
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
            numero=Proposta.proximo_numero(), versao=1, status=Proposta.Status.RASCUNHO,
            validade_dias=config.validade_padrao_dias, beneficios=config.beneficios_padrao,
            escopo=config.escopo_padrao, texto_sobre=config.texto_sobre,
            perfil_simultaneidade=(config.perfis_simultaneidade[0]["nome"] if config.perfis_simultaneidade else ""),
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
    dono = Cliente.objects.filter(cpf_cnpj=dados["cpf_cnpj"]).exclude(pk=cliente.pk).first()
    if dono:
        return proposta, [("cpf_cnpj", f"Este CPF/CNPJ já é de {dono.nome}.")]
    cliente.cpf_cnpj = dados["cpf_cnpj"]
    cliente.save(update_fields=["cpf_cnpj"])
    uc = UnidadeConsumidora.objects.filter(cliente=cliente, numero_uc=dados["numero_uc"]).first() or UnidadeConsumidora(
        cliente=cliente, numero_uc=dados["numero_uc"])
    uc.endereco = dados["endereco"]
    uc.municipio = proposta.municipio or cliente.municipio
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
    if n in (2, 3) and form.is_valid():
        proposta = form.save(commit=False)
        if n == 2 and proposta.origem_consumo == Proposta.OrigemConsumo.FATURA:
            proposta.fatura = FaturaReferencia(
                kwh=form.cleaned_data.get("fatura_kwh") or 0, dias_ciclo=form.cleaned_data.get("dias_ciclo") or 0,
            )
    else:
        proposta = get_object_or_404(Proposta, pk=pk)
    return render(request, "propostas/v2/_previa.html", _contexto_passos(request, proposta, n))


@require_POST
def alternar_modo_cliente(request):
    request.session["modo_cliente"] = not _modo_cliente(request)
    destino = request.POST.get("voltar", "")
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = reverse("propostas:lista")  # A23: só volta para página do próprio ERP
    return redirect(destino)


def proposta_abrir(request, pk):
    """Rascunho abre para editar (antiga no formulário antigo, v2 no passo em que parou); as outras, no detalhe."""
    proposta = get_object_or_404(Proposta, pk=pk)
    if proposta.status != Proposta.Status.RASCUNHO:
        return redirect("propostas:detalhe", pk=pk)
    if proposta.eh_antiga:
        return redirect("propostas:legado_editar", pk=pk)
    return redirect("propostas:passo", pk=pk, n=min(proposta.passo_atual, 4))


# ---------- Emissão e versões (fatia v2.7, D31)

def proposta_detalhe(request, pk):
    proposta = get_object_or_404(Proposta.objects.select_related("cliente"), pk=pk)
    return render(request, "propostas/detalhe.html", {
        "proposta": proposta,
        "versoes": Proposta.objects.filter(numero=proposta.numero).order_by("-versao"),
        "rascunho_aberto": emissao.rascunho_aberto(proposta),
        "aceite_form": AceiteForm(initial={"data_aceite": timezone.localdate()}),
        "perda_form": PerdaForm(),
        "desfazer_form": DesfazerAceiteForm(),
    })


@require_POST
def proposta_emitir(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        with transaction.atomic():
            emissao.preparar_emissao(proposta)
            emissao.concluir_emissao(proposta, gerar_pdf(proposta))
    except (emissao.ErroEmissao, ErroPDF, ErroAnexo) as erro:
        messages.error(request, f"Não foi possível emitir: {erro}")
        if proposta.eh_antiga:
            return redirect("propostas:detalhe", pk=pk)
        return redirect("propostas:passo", pk=pk, n=4)  # volta para onde estão os motivos (A15)
    messages.success(request, f"Proposta {proposta.numero} v{proposta.versao} emitida.")
    return redirect("propostas:detalhe", pk=pk)


@require_POST
def proposta_revisar(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        nova = emissao.revisar(proposta)
    except emissao.ErroEmissao as erro:
        messages.error(request, str(erro))
        return redirect("propostas:detalhe", pk=pk)
    if nova.eh_antiga:
        return redirect("propostas:legado_editar", pk=nova.pk)
    passo = 2 if request.POST.get("para") == "fatura" else 4
    return redirect("propostas:passo", pk=nova.pk, n=passo)


@require_POST
def proposta_aceitar(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    form = AceiteForm(request.POST)
    if form.is_valid():
        try:
            emissao.aceitar(proposta, form.cleaned_data["data_aceite"])
            messages.success(request, f"Proposta {proposta.numero} v{proposta.versao} aceita.")
        except emissao.ErroEmissao as erro:
            messages.error(request, str(erro))
    else:
        messages.error(request, "Informe a data do aceite.")
    return redirect("propostas:detalhe", pk=pk)


@require_POST
def proposta_desfazer_aceite(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    form = DesfazerAceiteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe por que o aceite foi desfeito.")
        return redirect("propostas:detalhe", pk=pk)
    try:
        emissao.desfazer_aceite(proposta, form.cleaned_data["motivo"])
        messages.success(request, f"Aceite da {proposta.numero} v{proposta.versao} desfeito.")
    except emissao.ErroEmissao as erro:
        messages.error(request, str(erro))
    return redirect("propostas:detalhe", pk=pk)


@require_POST
def proposta_perdida(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    form = PerdaForm(request.POST)
    if form.is_valid():
        try:
            emissao.marcar_perdida(proposta, form.cleaned_data["motivo_perda"], form.cleaned_data["obs_perda"])
            messages.success(request, f"Proposta {proposta.numero} v{proposta.versao} marcada como perdida.")
        except emissao.ErroEmissao as erro:
            messages.error(request, str(erro))
    else:
        messages.error(request, "Escolha o motivo da perda.")
    return redirect("propostas:detalhe", pk=pk)
