from django.urls import path

from . import views

app_name = "orcamentos"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.novo, name="novo"),
    path("<int:pk>/", views.editor, name="editor"),
    path("<int:pk>/buscar-produtos/", views.buscar_produtos, name="buscar_produtos"),
    path("<int:pk>/buscar-proprios/", views.buscar_itens_proprios, name="buscar_proprios"),
    path("<int:pk>/adicionar/produto/<int:produto_pk>/", views.adicionar_produto, name="adicionar_produto"),
    path("<int:pk>/adicionar/proprio/<int:item_pk>/", views.adicionar_item_proprio, name="adicionar_proprio"),
    path("<int:pk>/adicionar/avulso/", views.adicionar_avulso, name="adicionar_avulso"),
    path("<int:pk>/desconto/", views.atualizar_desconto, name="desconto"),
    path("<int:pk>/atualizar-precos/", views.atualizar_precos, name="atualizar_precos"),
    path("<int:pk>/preview/", views.preview, name="preview"),
    path("<int:pk>/emitir/", views.emitir, name="emitir"),
    path("<int:pk>/pdf/", views.baixar_pdf, name="pdf"),
    path("<int:pk>/revisar/", views.revisar, name="revisar"),
    path("<int:pk>/status/", views.marcar_status, name="status"),
    path("item/<int:item_pk>/atualizar/", views.atualizar_item, name="item_atualizar"),
    path("item/<int:item_pk>/remover/", views.remover_item, name="item_remover"),
    path("catalogo/", views.catalogo, name="catalogo"),
    path("catalogo/importar/", views.importar_tabela, name="importar"),
]
