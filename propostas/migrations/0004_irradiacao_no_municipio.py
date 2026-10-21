"""A irradiação passa de IrradiacaoMunicipio para core.Municipio (D21, D26)."""

from django.db import migrations

from core.municipios import chave_nome


def copiar(apps, schema_editor):
    Municipio = apps.get_model("core", "Municipio")
    IrradiacaoMunicipio = apps.get_model("propostas", "IrradiacaoMunicipio")

    por_nome = {(chave_nome(m.nome), m.uf): m for m in Municipio.objects.all()}
    registros = list(IrradiacaoMunicipio.objects.all())
    sem_par = [f"{r.municipio}/{r.uf}" for r in registros if (chave_nome(r.municipio), r.uf.upper()) not in por_nome]
    if sem_par:
        # Parar em vez de apagar: a tabela antiga só some quando todos os dados tiverem destino.
        raise RuntimeError(
            "Irradiação cadastrada para município fora da lista do IBGE: " + ", ".join(sem_par)
            + ". Anote esses valores (tabela propostas_irradiacaomunicipio), corrija o nome do município"
            " ou apague o registro, e rode o migrate de novo. Nada foi apagado."
        )
    for registro in registros:
        municipio = por_nome[(chave_nome(registro.municipio), registro.uf.upper())]
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
