from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("configuracoes/", views.config_empresa, name="config_empresa"),
    path("configuracoes/premissas/", views.config_premissas, name="config_premissas"),
    path("configuracoes/tarifas/", views.config_tarifas, name="config_tarifas"),
    path("configuracoes/financiamento/", views.config_financiamento, name="config_financiamento"),
    path("configuracoes/tarifas/atualizar/", views.config_tarifas_atualizar, name="config_tarifas_atualizar"),
    path("configuracoes/municipios/", views.config_municipios, name="config_municipios"),
    path("configuracoes/municipios/atualizar/", views.config_municipios_atualizar, name="config_municipios_atualizar"),
]
