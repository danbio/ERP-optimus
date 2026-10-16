from django.db import migrations

FIO_B_ESCALONAMENTO = {
    2023: 15,
    2024: 30,
    2025: 45,
    2026: 60,
    2027: 75,
    2028: 90,
    2029: 100,
}

FONTE_IRRADIACAO = "estimativa regional — validar CRESESB"

VALORES_IRRADIACAO = [4.95, 5.05, 4.95, 5.15, 5.35, 5.40, 5.65, 6.05, 5.90, 5.45, 5.10, 4.85]

MUNICIPIOS_IRRADIACAO = [
    ("São Valério da Natividade", "TO"),
    ("Gurupi", "TO"),
]


def criar_fio_b(apps, schema_editor):
    FioBEscalonamento = apps.get_model("propostas", "FioBEscalonamento")
    for ano, percentual in FIO_B_ESCALONAMENTO.items():
        FioBEscalonamento.objects.get_or_create(ano=ano, defaults={"percentual": percentual})


def remover_fio_b(apps, schema_editor):
    FioBEscalonamento = apps.get_model("propostas", "FioBEscalonamento")
    FioBEscalonamento.objects.filter(ano__in=FIO_B_ESCALONAMENTO).delete()


def criar_irradiacao(apps, schema_editor):
    IrradiacaoMunicipio = apps.get_model("propostas", "IrradiacaoMunicipio")
    for municipio, uf in MUNICIPIOS_IRRADIACAO:
        IrradiacaoMunicipio.objects.get_or_create(
            municipio=municipio,
            uf=uf,
            defaults={"valores": VALORES_IRRADIACAO, "fonte": FONTE_IRRADIACAO},
        )


def remover_irradiacao(apps, schema_editor):
    IrradiacaoMunicipio = apps.get_model("propostas", "IrradiacaoMunicipio")
    IrradiacaoMunicipio.objects.filter(
        municipio__in=[m for m, _ in MUNICIPIOS_IRRADIACAO], uf="TO"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("propostas", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(criar_fio_b, remover_fio_b),
        migrations.RunPython(criar_irradiacao, remover_irradiacao),
    ]
