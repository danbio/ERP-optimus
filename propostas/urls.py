from django.urls import path

from .views import catalogo, documento, passos, versoes

app_name = "propostas"

urlpatterns = [
    # Lista, detalhe e ações (views/versoes.py)
    path("", versoes.lista, name="lista"),
    path("<int:pk>/detalhe/", versoes.proposta_detalhe, name="detalhe"),
    path("<int:pk>/emitir/", versoes.proposta_emitir, name="emitir"),
    path("<int:pk>/revisar/", versoes.proposta_revisar, name="revisar"),
    path("<int:pk>/aceitar/", versoes.proposta_aceitar, name="aceitar"),
    path("<int:pk>/perdida/", versoes.proposta_perdida, name="perdida"),
    path("<int:pk>/desfazer-aceite/", versoes.proposta_desfazer_aceite, name="desfazer_aceite"),
    path("<int:pk>/descartar/", versoes.proposta_descartar, name="descartar"),
    # Os 4 passos (views/passos.py)
    path("nova/", passos.proposta_nova, name="nova"),
    path("<int:pk>/", passos.proposta_abrir, name="editar"),
    path("<int:pk>/passo/<int:n>/", passos.proposta_passo, name="passo"),
    path("<int:pk>/passo/<int:n>/previa/", passos.proposta_previa, name="previa"),
    path("<int:pk>/ler-fatura/", passos.ler_fatura, name="ler_fatura"),
    path("modo-cliente/", passos.alternar_modo_cliente, name="modo_cliente"),
    # PDF (views/documento.py)
    path("<int:pk>/preview/", documento.preview, name="preview"),
    path("<int:pk>/pdf/", documento.pdf, name="pdf"),
    # Catálogo solar e cotações (views/catalogo.py)
    path("catalogo/", catalogo.solar_equipamentos, name="solar_equipamentos"),
    path("catalogo/novo/", catalogo.solar_equipamento, name="solar_equipamento_novo"),
    path("catalogo/<int:pk>/", catalogo.solar_equipamento, name="solar_equipamento"),
    path("cotacoes/", catalogo.solar_cotacoes, name="solar_cotacoes"),
    path("cotacoes/nova/", catalogo.solar_cotacao, name="solar_cotacao_nova"),
    path("cotacoes/ler/", catalogo.ler_cotacao, name="ler_cotacao"),
    path("cotacoes/<int:pk>/", catalogo.solar_cotacao, name="solar_cotacao"),
]
