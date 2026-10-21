from django.contrib import admin

from .models import FaturaReferencia, FioBEscalonamento, ItemKit, Proposta


class ItemKitInline(admin.TabularInline):
    model = ItemKit
    extra = 0


@admin.register(Proposta)
class PropostaAdmin(admin.ModelAdmin):
    list_display = ["numero", "versao", "cliente", "status", "investimento", "emissao"]
    list_filter = ["status"]
    search_fields = ["numero", "uc__cliente__nome"]

    @admin.display(description="Cliente")
    def cliente(self, obj):
        return obj.cliente
    inlines = [ItemKitInline]


@admin.register(FaturaReferencia)
class FaturaReferenciaAdmin(admin.ModelAdmin):
    list_display = ["uc", "competencia", "kwh", "valor_total"]
    list_filter = ["uc__municipio"]


@admin.register(FioBEscalonamento)
class FioBEscalonamentoAdmin(admin.ModelAdmin):
    list_display = ["ano", "percentual"]
