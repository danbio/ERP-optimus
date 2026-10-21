"""UC e cliente passam a apontar para core.Municipio (D21, D26).

O município digitado como texto é procurado pelo nome, sem acento e sem diferença
de maiúsculas. Se não for achado, a UC fica sem município e o formulário pede de novo.
Telefone e CPF/CNPJ antigos passam a ser guardados só com os números (D24).
"""

import re

import django.db.models.deletion
from django.db import migrations, models

from core.municipios import chave_nome


def converter(apps, schema_editor):
    Municipio = apps.get_model("core", "Municipio")
    UnidadeConsumidora = apps.get_model("clientes", "UnidadeConsumidora")
    Cliente = apps.get_model("clientes", "Cliente")

    por_nome = {(chave_nome(m.nome), m.uf): m for m in Municipio.objects.all()}
    for uc in UnidadeConsumidora.objects.all():
        uc.municipio_ibge = por_nome.get((chave_nome(uc.municipio), (uc.uf or "").upper()))
        uc.save(update_fields=["municipio_ibge"])

    for cliente in Cliente.objects.all():
        cliente.cpf_cnpj = re.sub(r"\D", "", cliente.cpf_cnpj or "")
        cliente.telefone = re.sub(r"\D", "", cliente.telefone or "")
        cliente.save(update_fields=["cpf_cnpj", "telefone"])


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0001_initial"),
        ("core", "0005_carga_municipios_to"),
    ]

    operations = [
        migrations.AddField(
            model_name="unidadeconsumidora",
            name="municipio_ibge",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, to="core.municipio", related_name="+"
            ),
        ),
        migrations.RunPython(converter, migrations.RunPython.noop),
        migrations.RemoveField(model_name="unidadeconsumidora", name="municipio"),
        migrations.RemoveField(model_name="unidadeconsumidora", name="uf"),
        migrations.RenameField(model_name="unidadeconsumidora", old_name="municipio_ibge", new_name="municipio"),
    ]
