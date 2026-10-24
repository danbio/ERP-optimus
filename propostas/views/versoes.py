"""Lista, detalhe e ações da proposta: emitir, revisar, aceitar, perder, descartar (D31, D33, D36)."""

import re

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.forms import AcompanhamentoForm
from core.pdf import ErroPDF
from core.permissoes import eh_gestor
from core.views import gravar_acompanhamento

from .. import emissao
from ..forms import AceiteForm, DesfazerAceiteForm, PerdaForm
from ..models import Proposta
from ..services.pdf import ErroAnexo
from .documento import gerar_pdf


POR_PAGINA = 50


def lista(request):
    propostas = Proposta.objects.select_related("cliente")
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
    mes = request.GET.get("mes", "")  # "2026-10": propostas emitidas no mês (A28)
    if re.fullmatch(r"\d{4}-\d{2}", mes):
        ano, numero_mes = (int(parte) for parte in mes.split("-"))
        propostas = propostas.filter(emissao__year=ano, emissao__month=numero_mes)
    if situacao in ("emitida", "vencida"):  # "vencida" não é gravada: separa na hora (D31)
        propostas = [p for p in propostas if p.situacao == situacao]
    pagina = Paginator(propostas, POR_PAGINA).get_page(request.GET.get("pagina"))
    filtros = request.GET.copy()
    filtros.pop("pagina", None)
    return render(request, "propostas/lista.html", {
        "pagina": pagina,
        "status_choices": Proposta.Status.choices[:2] + [("vencida", "Vencida")] + Proposta.Status.choices[2:],
        "busca": busca,
        "mes": mes,
        "filtros": filtros.urlencode(),
    })


def proposta_detalhe(request, pk):
    proposta = get_object_or_404(Proposta.objects.select_related("cliente"), pk=pk)
    return render(request, "propostas/detalhe.html", {
        "proposta": proposta,
        "versoes": emissao.versoes(proposta),
        "rascunho_aberto": emissao.rascunho_aberto(proposta),
        "aceite_form": AceiteForm(initial={"data_aceite": timezone.localdate()}),
        "perda_form": PerdaForm(),
        "desfazer_form": DesfazerAceiteForm(),
        "acompanhamento_form": AcompanhamentoForm(objeto=proposta, gestor=eh_gestor(request.user)),
    })


@require_POST
def proposta_acompanhamento(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    return gravar_acompanhamento(request, proposta, reverse("propostas:detalhe", args=[pk]))


@require_POST
def proposta_emitir(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        with transaction.atomic():
            emissao.preparar_emissao(proposta, request.user)
            emissao.concluir_emissao(proposta, gerar_pdf(proposta))
    except (emissao.ErroEmissao, ErroPDF, ErroAnexo) as erro:
        messages.error(request, f"Não foi possível emitir: {erro}")
        return redirect("propostas:passo", pk=pk, n=4)  # volta para onde estão os motivos (A15)
    messages.success(request, f"Proposta {proposta.identificacao} emitida.")
    return redirect("propostas:detalhe", pk=pk)


@require_POST
def proposta_revisar(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        nova = emissao.revisar(proposta)
    except emissao.ErroEmissao as erro:
        messages.error(request, str(erro))
        return redirect("propostas:detalhe", pk=pk)
    passo = 2 if request.POST.get("para") == "fatura" else 4
    return redirect("propostas:passo", pk=nova.pk, n=passo)


@require_POST
def proposta_aceitar(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    form = AceiteForm(request.POST)
    if form.is_valid():
        try:
            emissao.aceitar(proposta, form.cleaned_data["data_aceite"], request.user)
            messages.success(request, f"Proposta {proposta.identificacao} aceita.")
        except emissao.ErroEmissao as erro:
            messages.error(request, str(erro))
    else:
        messages.error(request, "Informe a data do aceite.")
    return redirect("propostas:detalhe", pk=pk)


@require_POST
def proposta_descartar(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        identificacao = proposta.identificacao
        emissao.descartar(proposta)
    except emissao.ErroEmissao as erro:
        messages.error(request, str(erro))
        return redirect("propostas:detalhe", pk=pk)
    messages.success(request, f"{identificacao} descartado.")
    return redirect("propostas:lista")


@require_POST
def proposta_desfazer_aceite(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    form = DesfazerAceiteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe por que o aceite foi desfeito.")
        return redirect("propostas:detalhe", pk=pk)
    try:
        emissao.desfazer_aceite(proposta, form.cleaned_data["motivo"], request.user)
        messages.success(request, f"Aceite da {proposta.identificacao} desfeito.")
    except emissao.ErroEmissao as erro:
        messages.error(request, str(erro))
    return redirect("propostas:detalhe", pk=pk)


@require_POST
def proposta_perdida(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    form = PerdaForm(request.POST)
    if form.is_valid():
        try:
            emissao.marcar_perdida(proposta, form.cleaned_data["motivo_perda"], form.cleaned_data["obs_perda"],
                                   request.user)
            messages.success(request, f"Proposta {proposta.identificacao} marcada como perdida.")
        except emissao.ErroEmissao as erro:
            messages.error(request, str(erro))
    else:
        messages.error(request, "Escolha o motivo da perda.")
    return redirect("propostas:detalhe", pk=pk)
