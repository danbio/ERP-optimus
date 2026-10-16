from django.contrib import admin

from .models import Cliente, UnidadeConsumidora


class UnidadeConsumidoraInline(admin.TabularInline):
    model = UnidadeConsumidora
    extra = 0


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nome", "cpf_cnpj", "telefone", "criado_em"]
    search_fields = ["nome", "razao_social", "cpf_cnpj"]
    inlines = [UnidadeConsumidoraInline]


@admin.register(UnidadeConsumidora)
class UnidadeConsumidoraAdmin(admin.ModelAdmin):
    list_display = ["numero_uc", "cliente", "municipio", "uf", "classe", "ligacao"]
    list_filter = ["uf", "classe", "ligacao"]
    search_fields = ["numero_uc", "cliente__nome"]
