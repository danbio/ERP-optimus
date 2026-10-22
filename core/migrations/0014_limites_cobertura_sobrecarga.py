from django.db import migrations

LIMITES = {"cobertura_min": 0.80, "cobertura_max": 1.30, "sobrecarga_min": 0.80}


def incluir_limites(apps, schema_editor):
    """Limites que estavam fixos no código passam às premissas do gestor (A25)."""
    for config in apps.get_model("core", "ConfigEmpresa").objects.all():
        config.premissas_padrao = LIMITES | (config.premissas_padrao or {})
        config.save(update_fields=["premissas_padrao"])


def tirar_limites(apps, schema_editor):
    for config in apps.get_model("core", "ConfigEmpresa").objects.all():
        for chave in LIMITES:
            config.premissas_padrao.pop(chave, None)
        config.save(update_fields=["premissas_padrao"])


class Migration(migrations.Migration):
    dependencies = [("core", "0013_prazo_homologacao")]

    operations = [migrations.RunPython(incluir_limites, tirar_limites)]
