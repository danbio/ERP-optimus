from django.db import migrations


def criar_grupo(apps, schema_editor):
    apps.get_model("auth", "Group").objects.get_or_create(name="gestor")


def apagar_grupo(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name="gestor").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_travas"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(criar_grupo, apagar_grupo)]
