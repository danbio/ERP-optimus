from django.contrib import admin

from .models import ConfigEmpresa, Municipio


@admin.register(ConfigEmpresa)
class ConfigEmpresaAdmin(admin.ModelAdmin):
    list_display = ["razao_social", "cnpj", "projetos_entregues", "anos_atuacao"]

    def has_add_permission(self, request):
        # Registro único.
        return not ConfigEmpresa.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ["nome", "uf", "codigo_ibge", "fonte_irradiacao", "atualizado_em"]
    list_filter = ["uf"]
    search_fields = ["nome", "codigo_ibge"]
