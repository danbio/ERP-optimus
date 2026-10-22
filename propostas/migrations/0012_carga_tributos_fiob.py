"""Tributos e Fio B da Energisa TO conferidos em faturas e na ANEEL (D32).

Grava só onde o gestor ainda não preencheu, na tarifa de vigência 26/08/2026 (REH 3.323/2026).
"""

from datetime import date
from decimal import Decimal

from django.db import migrations

VIGENCIA = date(2026, 8, 26)
TRIBUTOS = Decimal("0.2740")  # ICMS 20% + PIS/COFINS 9,25% sobre base sem ICMS
FIOB = Decimal("0.441478")    # ANEEL, Componentes Tarifárias, REH 3.323/2026
CONFERIDO = date(2026, 10, 22)


def carregar(apps, schema_editor):
    TarifaVigente = apps.get_model("propostas", "TarifaVigente")
    tarifas = TarifaVigente.objects.filter(distribuidora="Energisa TO", vigencia_inicio=VIGENCIA)
    tarifas.filter(aliquota_tributos=0).update(aliquota_tributos=TRIBUTOS)
    tarifas.filter(fiob_kwh__isnull=True).update(fiob_kwh=FIOB, fiob_conferido_em=CONFERIDO)


class Migration(migrations.Migration):
    dependencies = [("propostas", "0011_emissao_versoes")]
    operations = [migrations.RunPython(carregar, migrations.RunPython.noop)]
