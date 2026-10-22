"""Catálogo solar e memória de cotações (fatia v2.4, D28)."""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from django.views.decorators.http import require_POST

from core import ia
from core.models import ConfigEmpresa
from core.permissoes import so_gestor

from django import forms

from ..forms import CotacaoForm, EquipamentoForm, ItemCotadoForm, ItensCotadosFormSet
from ..models import Cotacao, Equipamento, ItemCotado
from ..services import leitura_ia


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


@so_gestor
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


CAMPOS_DA_COTACAO = ["distribuidor", "numero", "data", "validade", "kwp", "total_produtos", "frete", "total", "observacao"]


@require_POST
def ler_cotacao(request):
    """IA lê o PDF da cotação e preenche os dados e os itens (D35, D37). Não grava: o vendedor confere e salva."""
    valores = {campo: request.POST.get(campo, "") for campo in CAMPOS_DA_COTACAO}
    contexto = {}
    itens_lidos = None
    arquivo = request.FILES.get("arquivo")
    if not arquivo:
        contexto["leitura_erro"] = "Escolha o PDF da cotação antes de pedir a leitura."
    else:
        try:
            cabecalho, itens_lidos = leitura_ia.campos_da_cotacao(
                ia.ler_pdf(arquivo.read(), leitura_ia.INSTRUCAO_COTACAO, leitura_ia.ESQUEMA_COTACAO))
        except ia.ErroLeitura as erro:
            contexto["leitura_erro"] = str(erro)
        else:
            valores |= {campo: valor for campo, valor in cabecalho.items() if valor}
            contexto["leitura_ok"] = True
    contexto["form"] = CotacaoForm(initial=valores)
    if itens_lidos is None:  # sem leitura: mantém os itens que estavam na tela
        contexto["itens"] = ItensCotadosFormSet(request.POST, instance=Cotacao(), prefix="item")
        contexto["itens"].is_valid()  # só para mostrar os valores digitados
    else:
        contexto["itens"] = _itens_lidos(itens_lidos)
    return render(request, "propostas/catalogo/_dados_cotacao.html", contexto)


def _itens_lidos(itens):
    """Formset sem gravar, com uma linha por item lido e duas em branco."""
    formset_classe = forms.inlineformset_factory(
        Cotacao, ItemCotado, form=ItemCotadoForm, extra=len(itens) + 2, can_delete=True)
    return formset_classe(instance=Cotacao(), prefix="item", initial=itens)
