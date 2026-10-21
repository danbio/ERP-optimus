"""Textos padrão da proposta, tirados da proposta aprovada do caso Alesio (v2).

Só preenche campos que ainda estão vazios: não sobrescreve o que já foi
editado no admin.
"""

from django.db import migrations

TEXTOS = {
    "texto_sobre": (
        "Empresa especializada em energia solar fotovoltaica, com mais de 5 anos de atuação e mais de 800 "
        "projetos concluídos. Atendemos todas as etapas, do projeto à conexão do sistema à rede."
    ),
    "beneficios_padrao": "\n".join([
        "Geração concentrada no período diurno, quando o consumo costuma ser maior.",
        "O excedente de geração vira créditos junto à concessionária, válidos por 60 meses.",
        "Redução da exposição a reajustes tarifários e bandeiras.",
        "Vida útil superior a 25 anos, com monitoramento remoto da geração.",
    ]),
    "escopo_padrao": "\n".join([
        "Visita técnica e levantamento",
        "Projeto elétrico e ART",
        "Homologação junto à Energisa",
        "Equipamentos e materiais",
        "Frete até o local",
        "Instalação e comissionamento",
        "Configuração do monitoramento",
        "Acompanhamento até a ligação",
    ]),
    "etapas_padrao": "\n".join([
        "Aceite | assinatura",
        "Projeto | projeto e ART",
        "Homologação | Energisa",
        "Instalação | montagem e testes",
        "Conexão | vistoria e ligação",
    ]),
}


def preencher_textos(apps, schema_editor):
    ConfigEmpresa = apps.get_model("core", "ConfigEmpresa")
    config = ConfigEmpresa.objects.filter(pk=1).first()
    if config is None:
        return
    for campo, texto in TEXTOS.items():
        if not getattr(config, campo):
            setattr(config, campo, texto)
    config.save()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_carga_inicial"),
    ]

    operations = [
        migrations.RunPython(preencher_textos, migrations.RunPython.noop),
    ]
