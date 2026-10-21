"""Carga dos 139 municípios do Tocantins a partir de core/dados/municipios_to.csv (D26)."""

import csv
from pathlib import Path

from django.db import migrations

ARQUIVO = Path(__file__).resolve().parent.parent / "dados" / "municipios_to.csv"


def carregar(apps, schema_editor):
    Municipio = apps.get_model("core", "Municipio")
    with ARQUIVO.open(encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            Municipio.objects.update_or_create(
                codigo_ibge=int(linha["codigo_ibge"]),
                defaults={
                    "nome": linha["nome"],
                    "uf": linha["uf"],
                    "latitude": float(linha["latitude"]),
                    "longitude": float(linha["longitude"]),
                },
            )


def remover(apps, schema_editor):
    apps.get_model("core", "Municipio").objects.filter(uf="TO").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_municipio"),
    ]

    operations = [
        migrations.RunPython(carregar, remover),
    ]
