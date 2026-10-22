"""Tabela de iluminação pública de Gurupi (D32).

LC 38/2022 (Código Tributário de Gurupi), arts. 113–125 e Anexo VII: valor fixo por faixa de consumo,
em UFIRG. UFIRG 2026 = R$ 4,61. Conferido em faturas: 380 kWh → R$ 29,50; 897 kWh → R$ 54,17.
"""

from decimal import Decimal

from django.db import migrations

GURUPI = 1709500
LEI = "LC 38/2022 de Gurupi, arts. 113–125 e Anexo VII (UFIRG 2026 = R$ 4,61)"
UFIRG_2026 = Decimal("4.61")
# (até quantos kWh, UFIRG); None = sem limite. A primeira faixa é isenta.
RESIDENCIAL = [
    (100, "0"), (150, "1.83"), (200, "2.74"), (250, "3.66"), (300, "4.57"), (350, "5.48"), (400, "6.40"),
    (450, "7.31"), (500, "8.22"), (800, "9.14"), (1500, "11.75"), (None, "14.36"),
]
NAO_RESIDENCIAL = [
    (50, "0"), (100, "2.61"), (150, "3.52"), (200, "4.44"), (250, "5.35"), (300, "6.27"), (350, "7.18"),
    (400, "8.09"), (450, "9.01"), (500, "9.92"), (800, "10.84"), (1500, "13.45"), (None, "16.06"),
]


def carregar(apps, schema_editor):
    Municipio = apps.get_model("core", "Municipio")
    FaixaIluminacao = apps.get_model("core", "FaixaIluminacao")
    gurupi = Municipio.objects.filter(codigo_ibge=GURUPI).first()
    if not gurupi:
        return
    gurupi.valor_unidade_fiscal = UFIRG_2026
    gurupi.lei_iluminacao = LEI
    gurupi.save(update_fields=["valor_unidade_fiscal", "lei_iluminacao"])
    faixas = {"residencial": RESIDENCIAL, "nao_residencial": NAO_RESIDENCIAL}
    for classe, linhas in faixas.items():
        for ate, unidades in linhas:
            FaixaIluminacao.objects.get_or_create(
                municipio=gurupi, classe=classe, ate_kwh=ate, defaults={"unidades": Decimal(unidades)}
            )


def desfazer(apps, schema_editor):
    apps.get_model("core", "FaixaIluminacao").objects.filter(municipio__codigo_ibge=GURUPI).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0008_iluminacao_publica")]
    operations = [migrations.RunPython(carregar, desfazer)]
