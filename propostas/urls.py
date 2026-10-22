from django.urls import path

from . import views

app_name = "propostas"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nova/", views.proposta_nova, name="nova"),
    path("<int:pk>/", views.proposta_abrir, name="editar"),
    path("<int:pk>/passo/<int:n>/", views.proposta_passo, name="passo"),
    path("<int:pk>/passo/<int:n>/previa/", views.proposta_previa, name="previa"),
    path("modo-cliente/", views.alternar_modo_cliente, name="modo_cliente"),
    path("antiga/nova/", views.formulario, name="legado_nova"),
    path("antiga/<int:pk>/editar/", views.formulario, name="legado_editar"),
    path("<int:pk>/preview/", views.preview, name="preview"),
    path("<int:pk>/pdf/", views.pdf, name="pdf"),
    path("<int:pk>/detalhe/", views.proposta_detalhe, name="detalhe"),
    path("<int:pk>/emitir/", views.proposta_emitir, name="emitir"),
    path("<int:pk>/revisar/", views.proposta_revisar, name="revisar"),
    path("<int:pk>/aceitar/", views.proposta_aceitar, name="aceitar"),
    path("<int:pk>/perdida/", views.proposta_perdida, name="perdida"),
    path("<int:pk>/desfazer-aceite/", views.proposta_desfazer_aceite, name="desfazer_aceite"),
    path("<int:pk>/descartar/", views.proposta_descartar, name="descartar"),
    path("recalcular/", views.recalcular, name="recalcular"),
    path("kit/nova-linha/", views.kit_nova_linha, name="kit_nova_linha"),
    path("fatura/nova/", views.fatura_novo, name="fatura_novo"),
    path("catalogo/", views.solar_equipamentos, name="solar_equipamentos"),
    path("catalogo/novo/", views.solar_equipamento, name="solar_equipamento_novo"),
    path("catalogo/<int:pk>/", views.solar_equipamento, name="solar_equipamento"),
    path("cotacoes/", views.solar_cotacoes, name="solar_cotacoes"),
    path("cotacoes/nova/", views.solar_cotacao, name="solar_cotacao_nova"),
    path("cotacoes/<int:pk>/", views.solar_cotacao, name="solar_cotacao"),
]
