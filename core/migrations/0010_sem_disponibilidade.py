"""D33: o custo de disponibilidade não entra na economia da proposta.

Propostas emitidas guardam as próprias premissas (snapshot) e não mudam.
"""

from django.db import migrations


def desligar(apps, schema_editor):
    ConfigEmpresa = apps.get_model("core", "ConfigEmpresa")
    for config in ConfigEmpresa.objects.all():
        config.premissas_padrao["cobrar_disponibilidade"] = False
        config.save(update_fields=["premissas_padrao"])


def ligar(apps, schema_editor):
    ConfigEmpresa = apps.get_model("core", "ConfigEmpresa")
    for config in ConfigEmpresa.objects.all():
        config.premissas_padrao["cobrar_disponibilidade"] = True
        config.save(update_fields=["premissas_padrao"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_carga_iluminacao_gurupi"),
    ]

    operations = [
        migrations.RunPython(desligar, ligar),
    ]
