from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from core.validacoes import so_digitos
from propostas.models import Proposta

from .forms import ClienteForm, UnidadeConsumidoraForm
from .models import Cliente, UnidadeConsumidora


def lista(request):
    clientes = Cliente.objects.select_related("municipio")
    busca = " ".join(request.GET.get("busca", "").split())
    if busca:
        filtro = Q(nome__icontains=busca) | Q(razao_social__icontains=busca)
        digitos = so_digitos(busca)
        if len(digitos) >= 4:
            filtro |= Q(telefone__contains=digitos) | Q(cpf_cnpj__contains=digitos)
        clientes = clientes.filter(filtro)
    return render(request, "clientes/lista.html", {"clientes": clientes[:200], "busca": busca})


def ficha(request, pk):
    cliente = get_object_or_404(Cliente.objects.select_related("municipio"), pk=pk)
    return render(request, "clientes/ficha.html", {
        "cliente": cliente,
        "ucs": cliente.unidades_consumidoras.select_related("municipio"),
        "propostas": Proposta.objects.filter(cliente=cliente).order_by("-pk"),
    })


def cliente_novo(request):
    """Cadastro de cliente. Com ?next= (vindo da proposta) volta para lá com ?cliente=<id>."""
    proximo = request.GET.get("next")
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            cliente = form.save()
            if proximo:
                return redirect(f"{proximo}?cliente={cliente.pk}")
            return redirect("clientes:ficha", pk=cliente.pk)
    else:
        form = ClienteForm()
    return render(request, "clientes/form_cliente.html", {"form": form, "titulo": "Novo cliente"})


def cliente_editar(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            return redirect("clientes:ficha", pk=cliente.pk)
    else:
        form = ClienteForm(instance=cliente)
    return render(request, "clientes/form_cliente.html", {
        "form": form, "titulo": f"Editar {cliente.nome}", "cliente": cliente,
    })


def uc_novo(request):
    proximo = request.GET.get("next") or reverse("propostas:nova")
    if request.method == "POST":
        form = UnidadeConsumidoraForm(request.POST)
        if form.is_valid():
            uc = form.save()
            return redirect(f"{proximo}?uc={uc.pk}")
    else:
        form = UnidadeConsumidoraForm(initial={"cliente": request.GET.get("cliente")})
    return render(request, "clientes/form_simples.html", {
        "form": form,
        "titulo": "Nova unidade consumidora",
    })


def uc_editar(request, pk):
    uc = get_object_or_404(UnidadeConsumidora, pk=pk)
    if request.method == "POST":
        form = UnidadeConsumidoraForm(request.POST, instance=uc)
        if form.is_valid():
            form.save()
            return redirect("clientes:ficha", pk=uc.cliente_id)
    else:
        form = UnidadeConsumidoraForm(instance=uc)
    return render(request, "clientes/form_simples.html", {"form": form, "titulo": f"Editar UC {uc.numero_uc}"})
