"""A irradiação passa de IrradiacaoMunicipio para core.Municipio (D21, D26)."""

from django.db import migrations

from core.municipios import chave_nome


def copiar(apps, schema_editor):
    Municipio = apps.get_model("core", "Municipio")
    IrradiacaoMunicipio = apps.get_model("propostas", "IrradiacaoMunicipio")

    por_nome = {(chave_nome(m.nome), m.uf): m for m in Municipio.objects.all()}
    for registro in IrradiacaoMunicipio.objects.all():
        municipio = por_nome.get((chave_nome(registro.municipio), registro.uf.upper()))
        if municipio is None:
            continue
        municipio.irradiacao = registro.valores
        municipio.fonte_irradiacao = registro.fonte
        municipio.save(update_fields=["irradiacao", "fonte_irradiacao"])


class Migration(migrations.Migration):

    dependencies = [
        ("propostas", "0003_remove_proposta_cliente"),
        ("core", "0005_carga_municipios_to"),
    ]

    operations = [
        migrations.RunPython(copiar, migrations.RunPython.noop),
        migrations.DeleteModel(name="IrradiacaoMunicipio"),
    ]
