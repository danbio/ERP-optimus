"""Carga inicial de tarifas (Energisa TO, Grupo B) e bandeiras, como a ANEEL publicava em 21/10/2026.

Depois disso, o botão "Atualizar da ANEEL" em Configurações → Tarifas mantém em dia (D21, D27).
Tributos e Fio B começam vazios: são do gestor.
"""

from datetime import date
from decimal import Decimal

from django.db import migrations

REH = "ANEEL, dados abertos (REH nº 3.323, de 24/08/2026)"
VIGENCIA = date(2026, 8, 26)
TARIFAS = {  # R$/kWh sem tributos: TUSD, TE
    "B1": ("0.683270", "0.309510"),
    "B1_BAIXA_RENDA": ("0.574030", "0.309640"),
    "B2": ("0.683270", "0.309510"),
    "B3": ("0.683270", "0.309510"),
}
BANDEIRAS = [  # nome, R$/kWh, vigência (REH nº 3.306/2024)
    ("Verde", "0", date(2024, 4, 1)),
    ("Amarela", "0.01885", date(2024, 4, 1)),
    ("Vermelha patamar 1", "0.04463", date(2024, 4, 1)),
    ("Vermelha patamar 2", "0.07877", date(2024, 4, 1)),
]


def carregar(apps, schema_editor):
    TarifaVigente = apps.get_model("propostas", "TarifaVigente")
    Bandeira = apps.get_model("propostas", "Bandeira")
    for tipo, (tusd, te) in TARIFAS.items():
        TarifaVigente.objects.get_or_create(
            distribuidora="Energisa TO", tipo=tipo, vigencia_inicio=VIGENCIA,
            defaults={"tusd": Decimal(tusd), "te": Decimal(te), "fonte": REH, "atualizado_em": date(2026, 10, 21)},
        )
    for ordem, (nome, valor, vigencia) in enumerate(BANDEIRAS):
        Bandeira.objects.get_or_create(nome=nome, defaults={"adicional_kwh": Decimal(valor), "vigencia": vigencia, "ordem": ordem})


def remover(apps, schema_editor):
    apps.get_model("propostas", "TarifaVigente").objects.filter(vigencia_inicio=VIGENCIA).delete()
    apps.get_model("propostas", "Bandeira").objects.filter(nome__in=[b[0] for b in BANDEIRAS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("propostas", "0005_bandeira_tarifavigente_taxafinanciamento"),
    ]

    operations = [
        migrations.RunPython(carregar, remover),
    ]
