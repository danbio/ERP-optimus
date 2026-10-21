from django.urls import path

from . import views

app_name = "clientes"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.cliente_novo, name="cliente_novo"),
    path("<int:pk>/", views.ficha, name="ficha"),
    path("<int:pk>/editar/", views.cliente_editar, name="cliente_editar"),
    path("uc/novo/", views.uc_novo, name="uc_novo"),
]
