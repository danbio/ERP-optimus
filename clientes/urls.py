from django.urls import path

from . import views

app_name = "clientes"

urlpatterns = [
    path("novo/", views.cliente_novo, name="cliente_novo"),
    path("uc/novo/", views.uc_novo, name="uc_novo"),
]
