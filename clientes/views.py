from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import ClienteForm, UnidadeConsumidoraForm


def cliente_novo(request):
    proximo = request.GET.get("next") or reverse("propostas:nova")
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            cliente = form.save()
            return redirect(f"{proximo}?cliente={cliente.pk}")
    else:
        form = ClienteForm()
    return render(request, "clientes/form_simples.html", {
        "form": form,
        "titulo": "Novo cliente",
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
