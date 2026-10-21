from django.contrib import admin

from .models import (
    ItemOrcamento, ItemProprio, MarkupSegmento, Orcamento, ParametrosOrcamento, Produto, TabelaPreco,
)


@admin.register(ParametrosOrcamento)
class ParametrosOrcamentoAdmin(admin.ModelAdmin):
    list_display = ["__str__", "uf_destino", "markup_padrao", "validade_padrao_dias"]

    def has_add_permission(self, request):
        return not ParametrosOrcamento.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MarkupSegmento)
class MarkupSegmentoAdmin(admin.ModelAdmin):
    list_display = ["segmento", "markup"]
    list_editable = ["markup"]


@admin.register(ItemProprio)
class ItemProprioAdmin(admin.ModelAdmin):
    list_display = ["descricao", "tipo", "unidade", "custo", "preco", "ativo"]
    list_filter = ["tipo", "ativo"]
    list_editable = ["custo", "preco", "ativo"]
    search_fields = ["descricao"]


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "resumo", "segmento", "psd", "pscf", "qtd_multipla", "ativo", "em_encerramento"]
    list_filter = ["ativo", "em_encerramento", "bu", "segmento"]
    search_fields = ["codigo", "descricao", "resumo"]


@admin.register(TabelaPreco)
class TabelaPrecoAdmin(admin.ModelAdmin):
    list_display = ["referencia", "uf_destino", "importada_em"]


class ItemOrcamentoInline(admin.TabularInline):
    model = ItemOrcamento
    extra = 0
    raw_id_fields = ["produto"]


@admin.register(Orcamento)
class OrcamentoAdmin(admin.ModelAdmin):
    list_display = ["numero", "versao", "cliente", "titulo", "status", "total", "emissao"]
    list_filter = ["status"]
    search_fields = ["numero", "cliente__nome", "titulo"]
    inlines = [ItemOrcamentoInline]
