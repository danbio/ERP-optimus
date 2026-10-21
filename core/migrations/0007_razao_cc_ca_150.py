"""D19: a sobrecarga máxima padrão do inversor passa de 1,30 para 1,50.

Só muda se o gestor ainda não tiver alterado o valor. Propostas antigas guardam as
próprias premissas (snapshot) e não mudam.
"""

from django.db import migrations


def para_150(apps, schema_editor):
    ConfigEmpresa = apps.get_model("core", "ConfigEmpresa")
    for config in ConfigEmpresa.objects.all():
        if config.premissas_padrao.get("razao_cc_ca_max") == 1.30:
            config.premissas_padrao["razao_cc_ca_max"] = 1.50
            config.save(update_fields=["premissas_padrao"])


def para_130(apps, schema_editor):
    ConfigEmpresa = apps.get_model("core", "ConfigEmpresa")
    for config in ConfigEmpresa.objects.all():
        if config.premissas_padrao.get("razao_cc_ca_max") == 1.50:
            config.premissas_padrao["razao_cc_ca_max"] = 1.30
            config.save(update_fields=["premissas_padrao"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_config_proposta_v2"),
    ]

    operations = [
        migrations.RunPython(para_150, para_130),
    ]
