from django.urls import path

from . import views

app_name = "propostas"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nova/", views.formulario, name="nova"),
    path("<int:pk>/editar/", views.formulario, name="editar"),
    path("<int:pk>/preview/", views.preview, name="preview"),
    path("<int:pk>/pdf/", views.pdf, name="pdf"),
    path("recalcular/", views.recalcular, name="recalcular"),
    path("kit/nova-linha/", views.kit_nova_linha, name="kit_nova_linha"),
    path("fatura/nova/", views.fatura_novo, name="fatura_novo"),
]
