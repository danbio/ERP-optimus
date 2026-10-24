from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import ConfigEmpresa
from core.pdf import ErroPDF, html_para_pdf
from core.forms import AcompanhamentoForm
from core.permissoes import eh_gestor, so_gestor
from core.views import ABAS, gravar_acompanhamento

from .forms import ImportarTabelaForm, OrcamentoDadosForm, OrcamentoNovoForm, ParcelamentoForm
from .importacao import aplicar_importacao
from .models import (
    ItemOrcamento, ItemProprio, MarkupSegmento, Orcamento, ParametrosOrcamento, Produto, TabelaPreco,
)
from .services.calculo import (
    Linha, ler_decimal, markup_para, markup_por_preco, parcelamento, preco_por_markup, resumir,
)
from .services.tabela_intelbras import TabelaInvalida, ler_tabela

LIMITE_BUSCA = 25


# ---------------------------------------------------------------- auxiliares

def _markups():
    return {m.segmento: m.markup for m in MarkupSegmento.objects.all()}


def _linha_calculo(item):
    return Linha(
        tipo=item.tipo,
        descricao=item.descricao,
        quantidade=item.quantidade,
        custo_unitario=item.custo_unitario,
        preco_unitario=item.preco_unitario,
        pscf_unitario=item.pscf_unitario,
        ativo_na_tabela=item.ativo_na_tabela,
        em_encerramento=item.em_encerramento,
        substituto=item.substituto,
    )


def _itens_com_resumo(orcamento):
    itens = list(orcamento.itens.all())
    resumo = resumir([_linha_calculo(i) for i in itens], orcamento.desconto_pct)
    for item, alertas in zip(itens, resumo.alertas_por_linha):
        item.alertas = alertas
        item.markup = markup_por_preco(item.custo_unitario, item.preco_unitario)
    return itens, resumo


def _salvar_total(orcamento):
    _, resumo = _itens_com_resumo(orcamento)
    Orcamento.objects.filter(pk=orcamento.pk).update(total=resumo.total)
    orcamento.total = resumo.total
    return resumo


def _render_itens(request, orcamento):
    itens, resumo = _itens_com_resumo(orcamento)
    return render(request, "orcamentos/_itens.html", {
        "orcamento": orcamento, "itens": itens, "resumo": resumo,
    })


def _orcamento_rascunho(pk):
    orcamento = get_object_or_404(Orcamento, pk=pk)
    if not orcamento.editavel:
        raise Http404("Orçamento emitido não pode ser alterado. Use Revisar.")
    return orcamento


def _editor_com_erro(orcamento, mensagem):
    url = reverse("orcamentos:editor", kwargs={"pk": orcamento.pk})
    return redirect(f"{url}?{urlencode({'erro_pdf': mensagem})}")


def _proxima_ordem(orcamento):
    ultimo = orcamento.itens.order_by("-ordem").values_list("ordem", flat=True).first()
    return (ultimo or 0) + 1


def _referencia_tabela_atual():
    tabela = TabelaPreco.objects.first()
    return tabela.referencia if tabela else ""


# ---------------------------------------------------------------- orçamentos

def lista(request):
    """Lista de orçamentos com filtro de situação e busca (D40)."""
    orcamentos = Orcamento.objects.select_related("cliente").all()
    status = request.GET.get("status")
    if status:
        orcamentos = orcamentos.filter(status=status)
    busca = request.GET.get("busca", "").strip()
    if busca:
        orcamentos = orcamentos.filter(
            Q(cliente__nome__icontains=busca) | Q(titulo__icontains=busca) | Q(numero__icontains=busca)
        )
    return render(request, "orcamentos/lista.html", {
        "orcamentos": orcamentos,
        "status_choices": Orcamento.Status.choices,
    })


def novo(request):
    """Cria o orçamento com os padrões dos parâmetros e o vendedor que criou (D46)."""
    parametros = ParametrosOrcamento.obter()
    if request.method == "POST":
        form = OrcamentoNovoForm(request.POST)
        if form.is_valid():
            orcamento = form.save(commit=False)
            orcamento.numero = Orcamento.proximo_numero()
            orcamento.validade_dias = parametros.validade_padrao_dias
            orcamento.forma_pagamento = parametros.forma_pagamento_padrao
            orcamento.prazo_execucao = parametros.prazo_padrao
            orcamento.garantia = parametros.garantia_padrao
            orcamento.observacoes = parametros.observacoes_padrao
            orcamento.tabela_referencia = _referencia_tabela_atual()
            orcamento.vendedor = request.user if request.user.is_authenticated else None  # D46
            orcamento.save()
            return redirect("orcamentos:editor", pk=orcamento.pk)
    else:
        form = OrcamentoNovoForm(initial={"cliente": request.GET.get("cliente")})
    return render(request, "orcamentos/novo.html", {"form": form})


def editor(request, pk):
    """Tela do orçamento: itens, totais, dados e acompanhamento."""
    orcamento = get_object_or_404(Orcamento.objects.select_related("cliente"), pk=pk)
    salvo = False
    if request.method == "POST" and orcamento.editavel:
        form = OrcamentoDadosForm(request.POST, instance=orcamento)
        if form.is_valid():
            form.save()
            salvo = True
    else:
        form = OrcamentoDadosForm(instance=orcamento)

    itens, resumo = _itens_com_resumo(orcamento)
    return render(request, "orcamentos/editor.html", {
        "orcamento": orcamento,
        "form": form,
        "salvo": salvo,
        "itens": itens,
        "resumo": resumo,
        "versoes": Orcamento.objects.filter(numero=orcamento.numero).order_by("versao"),
        "erro_pdf": request.GET.get("erro_pdf", ""),
        "acompanhamento_form": AcompanhamentoForm(objeto=orcamento, gestor=eh_gestor(request.user)),
    })


@require_POST
def acompanhamento(request, pk):
    """Grava próximo contato e vendedor responsável do orçamento (A20, D46)."""
    orcamento = get_object_or_404(Orcamento, pk=pk)
    return gravar_acompanhamento(request, orcamento, reverse("orcamentos:editor", args=[pk]))


def buscar_produtos(request, pk):
    """Busca na tabela Intelbras para incluir no orçamento (HTMX)."""
    termo = request.GET.get("q", "").strip()
    produtos = []
    if len(termo) >= 2:
        filtro = Q()
        for palavra in termo.split():
            filtro &= Q(descricao__icontains=palavra) | Q(resumo__icontains=palavra) | Q(codigo__startswith=palavra)
        produtos = Produto.objects.filter(filtro, ativo=True).order_by("resumo")[:LIMITE_BUSCA]
    return render(request, "orcamentos/_busca_produtos.html", {
        "orcamento_pk": pk, "produtos": produtos, "termo": termo,
    })


def buscar_itens_proprios(request, pk):
    """Busca nos materiais e serviços próprios (HTMX)."""
    termo = request.GET.get("q", "").strip()
    itens = ItemProprio.objects.filter(ativo=True)
    if termo:
        itens = itens.filter(descricao__icontains=termo)
    return render(request, "orcamentos/_busca_proprios.html", {
        "orcamento_pk": pk, "itens": itens[:LIMITE_BUSCA],
    })


@require_POST
def adicionar_produto(request, pk, produto_pk):
    """Inclui um produto Intelbras com o preço pelo markup do segmento (sem PSD, usa o PSCF)."""
    orcamento = _orcamento_rascunho(pk)
    produto = get_object_or_404(Produto, pk=produto_pk)
    parametros = ParametrosOrcamento.obter()
    markup = markup_para(produto.segmento, _markups(), parametros.markup_padrao)
    preco = preco_por_markup(produto.psd, markup) if produto.psd else produto.pscf
    ItemOrcamento.objects.create(
        orcamento=orcamento,
        tipo=ItemOrcamento.Tipo.INTELBRAS,
        produto=produto,
        codigo=produto.codigo,
        descricao=produto.nome,
        quantidade=Decimal("1"),
        custo_unitario=produto.psd,
        preco_unitario=preco,
        pscf_unitario=produto.pscf or None,
        qtd_multipla=produto.qtd_multipla,
        ativo_na_tabela=produto.ativo,
        em_encerramento=produto.em_encerramento,
        substituto=produto.substituto,
        ordem=_proxima_ordem(orcamento),
    )
    _salvar_total(orcamento)
    return _render_itens(request, orcamento)


@require_POST
def adicionar_item_proprio(request, pk, item_pk):
    """Inclui um material ou serviço próprio com o preço cadastrado."""
    orcamento = _orcamento_rascunho(pk)
    proprio = get_object_or_404(ItemProprio, pk=item_pk)
    ItemOrcamento.objects.create(
        orcamento=orcamento,
        tipo=proprio.tipo,
        descricao=proprio.descricao,
        unidade=proprio.unidade,
        quantidade=Decimal("1"),
        custo_unitario=proprio.custo,
        preco_unitario=proprio.preco,
        ordem=_proxima_ordem(orcamento),
    )
    _salvar_total(orcamento)
    return _render_itens(request, orcamento)


@require_POST
def adicionar_avulso(request, pk):
    """Inclui uma linha avulsa de material ou serviço, para o vendedor preencher."""
    orcamento = _orcamento_rascunho(pk)
    tipo = request.POST.get("tipo")
    if tipo not in (ItemOrcamento.Tipo.MATERIAL, ItemOrcamento.Tipo.SERVICO):
        tipo = ItemOrcamento.Tipo.SERVICO
    ItemOrcamento.objects.create(
        orcamento=orcamento,
        tipo=tipo,
        descricao="Novo serviço" if tipo == ItemOrcamento.Tipo.SERVICO else "Novo material",
        unidade="un" if tipo == ItemOrcamento.Tipo.MATERIAL else "vb",
        ordem=_proxima_ordem(orcamento),
    )
    _salvar_total(orcamento)
    return _render_itens(request, orcamento)


@require_POST
def atualizar_item(request, item_pk):
    """Altera um campo do item (descrição, quantidade, preço ou markup) e recalcula os totais (HTMX)."""
    item = get_object_or_404(ItemOrcamento.objects.select_related("orcamento"), pk=item_pk)
    orcamento = _orcamento_rascunho(item.orcamento_id)
    campo = request.POST.get("campo")
    valor = request.POST.get("valor", "")

    if campo == "descricao" and valor.strip():
        item.descricao = valor.strip()[:500]
    elif campo == "unidade" and valor.strip():
        item.unidade = valor.strip()[:10]
    elif campo == "quantidade":
        numero = ler_decimal(valor)
        if numero is not None and numero > 0:
            item.quantidade = numero
    elif campo == "custo":
        numero = ler_decimal(valor)
        if numero is not None and numero >= 0:
            item.custo_unitario = numero
    elif campo == "preco":
        numero = ler_decimal(valor)
        if numero is not None and numero >= 0:
            item.preco_unitario = numero
    elif campo == "markup":
        numero = ler_decimal(valor)
        if numero is not None and item.custo_unitario:
            item.preco_unitario = preco_por_markup(item.custo_unitario, numero)
    item.save()
    _salvar_total(orcamento)
    return _render_itens(request, orcamento)


@require_POST
def remover_item(request, item_pk):
    """Remove o item e recalcula os totais (HTMX)."""
    item = get_object_or_404(ItemOrcamento, pk=item_pk)
    orcamento = _orcamento_rascunho(item.orcamento_id)
    item.delete()
    _salvar_total(orcamento)
    return _render_itens(request, orcamento)


@require_POST
def atualizar_desconto(request, pk):
    """Grava o desconto (% de 0 a 100) e recalcula os totais (HTMX)."""
    orcamento = _orcamento_rascunho(pk)
    numero = ler_decimal(request.POST.get("desconto_pct"))
    if numero is not None and 0 <= numero <= 100:
        orcamento.desconto_pct = numero
        orcamento.save(update_fields=["desconto_pct"])
    _salvar_total(orcamento)
    return _render_itens(request, orcamento)


@require_POST
def atualizar_precos(request, pk):
    """Traz custo/PSCF da tabela atual para os itens Intelbras, mantendo o markup de cada item."""
    orcamento = _orcamento_rascunho(pk)
    for item in orcamento.itens.filter(tipo=ItemOrcamento.Tipo.INTELBRAS).select_related("produto"):
        produto = item.produto
        if produto is None:
            continue
        markup = markup_por_preco(item.custo_unitario, item.preco_unitario)
        item.custo_unitario = produto.psd
        item.pscf_unitario = produto.pscf or None
        item.qtd_multipla = produto.qtd_multipla
        item.ativo_na_tabela = produto.ativo
        item.em_encerramento = produto.em_encerramento
        item.substituto = produto.substituto
        if markup is not None and produto.psd:
            item.preco_unitario = preco_por_markup(produto.psd, markup)
        item.save()
    orcamento.tabela_referencia = _referencia_tabela_atual()
    orcamento.save(update_fields=["tabela_referencia"])
    return redirect("orcamentos:editor", pk=pk)


# ---------------------------------------------------------------- PDF e ciclo de vida

def _contexto_documento(orcamento, para_pdf):
    itens, resumo = _itens_com_resumo(orcamento)
    grupos = []
    rotulos = {
        ItemOrcamento.Tipo.INTELBRAS: "Equipamentos Intelbras",
        ItemOrcamento.Tipo.MATERIAL: "Materiais",
        ItemOrcamento.Tipo.SERVICO: "Serviços",
    }
    subtotais = {
        ItemOrcamento.Tipo.INTELBRAS: resumo.total_intelbras,
        ItemOrcamento.Tipo.MATERIAL: resumo.total_materiais,
        ItemOrcamento.Tipo.SERVICO: resumo.total_servicos,
    }
    for tipo, rotulo in rotulos.items():
        do_grupo = [i for i in itens if i.tipo == tipo]
        if do_grupo:
            grupos.append({"rotulo": rotulo, "itens": do_grupo, "tipo": tipo, "subtotal": subtotais[tipo]})
    emissao = orcamento.emissao or timezone.localdate()
    parcelas = parcelamento(resumo.total, ParametrosOrcamento.obter().parcelamento) \
        if orcamento.mostrar_parcelamento else []
    return {
        "parcelas": parcelas,
        "orcamento": orcamento,
        "empresa": ConfigEmpresa.obter(),
        "grupos": grupos,
        "resumo": resumo,
        "emissao": emissao,
        "validade_ate": emissao + timezone.timedelta(days=orcamento.validade_dias),
        "base_estatico": (Path(settings.BASE_DIR) / "static").as_uri() if para_pdf else "/" + settings.STATIC_URL.strip("/"),
        "para_pdf": para_pdf,
    }


def preview(request, pk):
    """Pré-visualização do PDF no navegador."""
    orcamento = get_object_or_404(Orcamento, pk=pk)
    return render(request, "orcamentos/pdf/orcamento.html", _contexto_documento(orcamento, para_pdf=False))


def _gerar_pdf(orcamento):
    contexto = _contexto_documento(orcamento, para_pdf=True)
    html = render_to_string("orcamentos/pdf/orcamento.html", contexto)
    rodape = render_to_string("orcamentos/pdf/_rodape.html", contexto)
    return html_para_pdf(html, rodape)


@require_POST
def emitir(request, pk):
    """Emite: congela a data e o total, gera e guarda o PDF."""
    orcamento = _orcamento_rascunho(pk)
    if not orcamento.itens.exists():
        return _editor_com_erro(orcamento, "Adicione itens antes de emitir.")
    orcamento.emissao = timezone.localdate()
    _salvar_total(orcamento)
    try:
        conteudo = _gerar_pdf(orcamento)
    except ErroPDF as erro:
        return _editor_com_erro(orcamento, str(erro))
    nome = f"{orcamento.numero}_v{orcamento.versao}.pdf"
    orcamento.pdf.save(nome, ContentFile(conteudo), save=False)
    orcamento.status = Orcamento.Status.EMITIDO
    orcamento.save()
    return redirect("orcamentos:editor", pk=pk)


def baixar_pdf(request, pk):
    """Abre o PDF guardado na emissão."""
    orcamento = get_object_or_404(Orcamento, pk=pk)
    if not orcamento.pdf:
        raise Http404("PDF ainda não gerado.")
    nome = f"Orcamento_{orcamento.numero}_v{orcamento.versao}_{orcamento.cliente.nome}.pdf".replace(" ", "_")
    return FileResponse(orcamento.pdf.open("rb"), filename=nome, as_attachment=False, content_type="application/pdf")


@require_POST
@transaction.atomic
def revisar(request, pk):
    """Cria a versão seguinte em rascunho, com os mesmos itens (D07)."""
    original = get_object_or_404(Orcamento, pk=pk)
    ultima = Orcamento.objects.filter(numero=original.numero).order_by("-versao").first()
    if ultima.status == Orcamento.Status.RASCUNHO:
        return redirect("orcamentos:editor", pk=ultima.pk)
    itens = list(original.itens.all())
    nova = Orcamento.objects.get(pk=original.pk)
    nova.pk = None
    nova.versao = ultima.versao + 1
    nova.origem = original
    nova.status = Orcamento.Status.RASCUNHO
    nova.emissao = None
    nova.pdf = ""
    nova.save()
    for item in itens:
        item.pk = None
        item.orcamento = nova
        item.save()
    return redirect("orcamentos:editor", pk=nova.pk)


@require_POST
def marcar_status(request, pk):
    """Marca um orçamento já emitido como emitido, aceito ou perdido."""
    orcamento = get_object_or_404(Orcamento, pk=pk)
    novo_status = request.POST.get("status")
    if orcamento.status != Orcamento.Status.RASCUNHO and novo_status in (
        Orcamento.Status.EMITIDO, Orcamento.Status.ACEITO, Orcamento.Status.PERDIDO
    ):
        orcamento.status = novo_status
        orcamento.save(update_fields=["status"])
    return redirect("orcamentos:editor", pk=pk)


# ---------------------------------------------------------------- configurações

@so_gestor
def config_parcelamento(request):
    """Configurações → Parcelamento do orçamento Intelbras (só o gestor, D44)."""
    parametros = ParametrosOrcamento.obter()
    form = ParcelamentoForm(request.POST or None, opcoes=parametros.parcelamento)
    if request.method == "POST" and form.is_valid():
        parametros.parcelamento = form.opcoes()
        parametros.save(update_fields=["parcelamento"])
        messages.success(request, "Parcelamento salvo.")
        return redirect("orcamentos:config_parcelamento")
    return render(request, "orcamentos/config_parcelamento.html", {"abas": ABAS, "form": form})


# ---------------------------------------------------------------- catálogo

def catalogo(request):
    """Catálogo Intelbras com busca e filtro por segmento."""
    termo = request.GET.get("q", "").strip()
    segmento = request.GET.get("segmento", "")
    so_ativos = request.GET.get("inativos") != "1"
    produtos = Produto.objects.all()
    if so_ativos:
        produtos = produtos.filter(ativo=True)
    if segmento:
        produtos = produtos.filter(segmento=segmento)
    for palavra in termo.split():
        produtos = produtos.filter(
            Q(descricao__icontains=palavra) | Q(resumo__icontains=palavra) | Q(codigo__startswith=palavra)
        )
    parametros = ParametrosOrcamento.obter()
    markups = _markups()
    produtos = list(produtos.order_by("segmento", "resumo")[:200])
    for produto in produtos:
        produto.markup = markup_para(produto.segmento, markups, parametros.markup_padrao)
        produto.preco_venda = preco_por_markup(produto.psd, produto.markup) if produto.psd else produto.pscf
    return render(request, "orcamentos/catalogo.html", {
        "produtos": produtos,
        "termo": termo,
        "segmento": segmento,
        "segmentos": Produto.objects.filter(ativo=True).values_list("segmento", flat=True).distinct().order_by("segmento"),
        "total_ativos": Produto.objects.filter(ativo=True).count(),
        "ultima_tabela": TabelaPreco.objects.first(),
    })


@so_gestor
def importar_tabela(request):
    """Importa a tabela .xlsb da Intelbras e mostra o que mudou (só o gestor, D13, H17)."""
    parametros = ParametrosOrcamento.obter()
    resumo, erro, tabela = None, "", None
    if request.method == "POST":
        form = ImportarTabelaForm(request.POST, request.FILES)
        if form.is_valid():
            tabela = TabelaPreco(uf_destino=parametros.uf_destino, referencia="(lendo)")
            tabela.arquivo.save(form.cleaned_data["arquivo"].name, form.cleaned_data["arquivo"], save=False)
            try:
                leitura = ler_tabela(tabela.arquivo.path, parametros.uf_destino)
            except TabelaInvalida as e:
                tabela.arquivo.delete(save=False)
                erro = str(e)
            else:
                ano = timezone.localdate().year
                tabela.referencia = f"{leitura.referencia}/{ano}" if leitura.referencia else f"{timezone.localdate():%m/%Y}"
                tabela.save()
                resumo = aplicar_importacao(leitura, tabela)
    else:
        form = ImportarTabelaForm()
    listas_resumo = []
    if resumo:
        listas_resumo = [
            ("Produtos novos", resumo["lista_novos"], resumo["novos"]),
            ("Saíram da tabela (ficaram inativos)", resumo["lista_sairam"], resumo["sairam"]),
        ]
    return render(request, "orcamentos/importar.html", {
        "form": form, "resumo": resumo, "erro": erro, "tabela": tabela, "listas_resumo": listas_resumo,
        "uf_destino": parametros.uf_destino,
        "historico": TabelaPreco.objects.all()[:10],
    })
