from django.db import migrations

PREMISSAS_PADRAO = {
    "perdas": 0.18,
    "perda_clipping": 0.015,
    "ano_conexao": 2027,
    "simultaneidade": 0.50,
    "reajuste_anual": 0.04,
    "degradacao_ano1": 0.01,
    "degradacao_anual": 0.004,
    "cobrar_disponibilidade": True,
    "horizonte_anos": 25,
    "razao_cc_ca_max": 1.30,
}


def criar_config_empresa(apps, schema_editor):
    ConfigEmpresa = apps.get_model("core", "ConfigEmpresa")
    ConfigEmpresa.objects.get_or_create(
        pk=1,
        defaults=dict(
            razao_social="Optimus Empreendimentos LTDA",
            nome_fantasia="Optimus Energia Solar",
            cnpj="43.324.626/0001-66",
            endereco="R S-015, 178, Parque Sol Nascente, Gurupi-TO",
            telefone="(63) 99841-6077",
            projetos_entregues=800,
            anos_atuacao=5,
            validade_padrao_dias=15,
            premissas_padrao=PREMISSAS_PADRAO,
        ),
    )


def remover_config_empresa(apps, schema_editor):
    ConfigEmpresa = apps.get_model("core", "ConfigEmpresa")
    ConfigEmpresa.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(criar_config_empresa, remover_config_empresa),
    ]
