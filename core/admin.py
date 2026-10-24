from django.contrib import admin

from .models import ConfigEmpresa, Distribuidora, FaixaIluminacao, Municipio


@admin.register(ConfigEmpresa)
class ConfigEmpresaAdmin(admin.ModelAdmin):
    list_display = ["razao_social", "cnpj", "projetos_entregues", "anos_atuacao"]

    def has_add_permission(self, request):
        # Registro único.
        return not ConfigEmpresa.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class FaixaIluminacaoInline(admin.TabularInline):
    model = FaixaIluminacao
    extra = 0


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    inlines = [FaixaIluminacaoInline]
    list_display = ["nome", "uf", "distribuidora", "codigo_ibge", "fonte_irradiacao", "atualizado_em"]
    list_filter = ["uf", "distribuidora"]
    search_fields = ["nome", "codigo_ibge"]


@admin.register(Distribuidora)
class DistribuidoraAdmin(admin.ModelAdmin):
    list_display = ["nome", "sigla_aneel", "uf"]
