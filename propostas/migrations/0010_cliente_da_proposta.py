"""D25: a proposta volta a ter cliente próprio. As antigas recebem o dono da UC.

As propostas antigas (fatia 4) têm fatura, então ficam como "confirmada", com a ligação da UC.
"""

import django.db.models.deletion
from django.db import migrations, models


def preencher(apps, schema_editor):
    Proposta = apps.get_model("propostas", "Proposta")
    for proposta in Proposta.objects.select_related("uc"):
        proposta.cliente_id = proposta.uc.cliente_id
        proposta.nivel = "confirmada"
        proposta.ligacao = proposta.uc.ligacao
        proposta.save(update_fields=["cliente", "nivel", "ligacao"])


class Migration(migrations.Migration):
    dependencies = [
        ("clientes", "0003_campos_cliente"),
        ("propostas", "0009_proposta_v2"),
    ]
    operations = [
        migrations.RunPython(preencher, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="proposta",
            name="cliente",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="propostas", to="clientes.cliente"
            ),
        ),
    ]
