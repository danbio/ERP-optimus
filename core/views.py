from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from propostas.models import Bandeira, TarifaVigente, TaxaFinanciamento

from . import dados_oficiais
from .forms import BandeirasFormSet, EmpresaForm, PerfisFormSet, PremissasForm, TarifaForm, TaxasForm
from .models import ConfigEmpresa, Municipio
from .permissoes import so_gestor


def inicio(request):
    return render(request, "core/inicio.html")


# ---------- Configurações (fatia v2.2): só o gestor usa ----------

ABAS = [
    ("core:config_empresa", "Empresa e textos"),
    ("core:config_premissas", "Premissas e mão de obra"),
    ("core:config_tarifas", "Tarifas e bandeiras"),
    ("core:config_financiamento", "Financiamento"),
    ("core:config_municipios", "Municípios e irradiação"),
]


def _render_config(request, template, contexto):
    return render(request, template, {"abas": ABAS, **contexto})


@so_gestor
def config_empresa(request):
    config = ConfigEmpresa.obter()
    form = EmpresaForm(request.POST or None, request.FILES or None, instance=config)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dados da empresa salvos.")
        return redirect("core:config_empresa")
    return _render_config(request, "core/config_empresa.html", {"form": form})


@so_gestor
def config_premissas(request):
    config = ConfigEmpresa.obter()
    if request.method == "POST":
        form = PremissasForm(request.POST)
        perfis = PerfisFormSet(request.POST, prefix="perfil")
        if form.is_valid() and perfis.is_valid():
            form.gravar(config)
            config.perfis_simultaneidade = [
                {"nome": p["nome"].strip(), "simultaneidade": p["simultaneidade"]}
                for p in perfis.cleaned_data if p.get("nome", "").strip()
            ]
            config.save()
            messages.success(request, "Premissas salvas. Valem para as próximas propostas.")
            return redirect("core:config_premissas")
    else:
        form = PremissasForm.da_config(config)
        perfis = PerfisFormSet(initial=config.perfis_simultaneidade, prefix="perfil")
    return _render_config(request, "core/config_premissas.html", {"form": form, "perfis": perfis})


@so_gestor
def config_tarifas(request):
    tarifas = TarifaVigente.vigentes()
    ultima_atualizacao = max((t.atualizado_em for t in tarifas), default=None)
    if request.method == "POST":
        forms_tarifa = [TarifaForm(request.POST, instance=t, prefix=f"tarifa-{t.pk}") for t in tarifas]
        bandeiras = BandeirasFormSet(request.POST, queryset=Bandeira.objects.all(), prefix="bandeira")
        if all(f.is_valid() for f in forms_tarifa) and bandeiras.is_valid():
            for f in forms_tarifa:
                f.save()
            bandeiras.save()
            messages.success(request, "Tarifas e bandeiras salvas.")
            return redirect("core:config_tarifas")
    else:
        forms_tarifa = [TarifaForm(instance=t, prefix=f"tarifa-{t.pk}") for t in tarifas]
        bandeiras = BandeirasFormSet(queryset=Bandeira.objects.all(), prefix="bandeira")
    return _render_config(request, "core/config_tarifas.html", {
        "forms_tarifa": forms_tarifa, "bandeiras": bandeiras, "ultima_atualizacao": ultima_atualizacao,
    })


@so_gestor
def config_financiamento(request):
    config = ConfigEmpresa.obter()
    form = TaxasForm(request.POST or None, taxas=TaxaFinanciamento.objects.all(), config=config)
    if request.method == "POST" and form.is_valid():
        form.gravar(config)
        messages.success(request, "Taxas de financiamento salvas.")
        return redirect("core:config_financiamento")
    return _render_config(request, "core/config_financiamento.html", {"form": form, "prazos": TaxaFinanciamento.PRAZOS})


@so_gestor
def config_municipios(request):
    municipios = Municipio.objects.filter(uf="TO")
    return _render_config(request, "core/config_municipios.html", {
        "municipios": municipios,
        "com_iluminacao": Municipio.objects.filter(faixas_iluminacao__isnull=False).distinct(),
        "pendentes": dados_oficiais.municipios_para_atualizar("TO").count(),
    })


# Quantos municípios por clique: cada um é uma consulta à NASA POWER (~1 s).
IRRADIACAO_POR_VEZ = 20


@require_POST
@so_gestor
def config_tarifas_atualizar(request):
    try:
        messages.success(request, dados_oficiais.atualizar_tarifas())
        messages.success(request, dados_oficiais.atualizar_bandeiras())
    except Exception as erro:
        messages.error(request, f"Não consegui falar com a ANEEL ({erro}). Os dados antigos continuam valendo.")
    return redirect("core:config_tarifas")


@require_POST
@so_gestor
def config_municipios_atualizar(request):
    pendentes = dados_oficiais.municipios_para_atualizar("TO")
    lote = list(pendentes[:IRRADIACAO_POR_VEZ])
    atualizados, erros = dados_oficiais.atualizar_irradiacao(lote)
    faltam = dados_oficiais.municipios_para_atualizar("TO").count()
    texto = f"{atualizados} municípios atualizados pela NASA POWER."
    if faltam:
        texto += f" Faltam {faltam}: clique de novo."
    messages.success(request, texto)
    if erros:
        messages.error(request, "Sem resposta para: " + "; ".join(erros[:5]))
    return redirect("core:config_municipios")
