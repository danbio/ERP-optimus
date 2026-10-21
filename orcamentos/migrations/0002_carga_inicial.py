from decimal import Decimal

from django.db import migrations

# Padrões iniciais (D14). Todos editáveis em Admin → Parâmetros de orçamento.
GARANTIA = (
    "Equipamentos: garantia do fabricante Intelbras, conforme o manual de cada produto.\n"
    "Serviços de instalação: 90 dias (Código de Defesa do Consumidor, art. 26)."
)
OBSERVACOES = (
    "Não inclusos: obras civis, adequações elétricas e itens não listados neste orçamento."
)


def criar_parametros(apps, schema_editor):
    ParametrosOrcamento = apps.get_model("orcamentos", "ParametrosOrcamento")
    ParametrosOrcamento.objects.get_or_create(
        pk=1,
        defaults=dict(
            uf_destino="TO",
            markup_padrao=Decimal("30"),
            validade_padrao_dias=7,
            forma_pagamento_padrao="A combinar",
            prazo_padrao="A combinar após o aceite",
            garantia_padrao=GARANTIA,
            observacoes_padrao=OBSERVACOES,
        ),
    )


def remover_parametros(apps, schema_editor):
    apps.get_model("orcamentos", "ParametrosOrcamento").objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("orcamentos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(criar_parametros, remover_parametros),
    ]
