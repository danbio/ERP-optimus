"""Carga inicial da memória de cotações: as duas cotações reais de 21/10/2026 (spec v2, seção 9).

Os equipamentos principais entram no catálogo para a sugestão de módulo e inversor funcionar
antes da importação do catálogo Belenus. A Belenus usa os códigos do site, para a importação
atualizar estes mesmos registros em vez de duplicar.
"""

from datetime import date
from decimal import Decimal

from django.db import migrations

EQUIPAMENTOS = [
    # distribuidor, código, tipo, fabricante, descrição, W, fase, tensão, estrutura
    ("Belenus", "MFTF-0.4-BF-132-610W", "modulo", "Huansheng",
     "Modulo Bifacial 132 Cel. N Type 610w Black Frame Cabo 0.4m Huansheng Solar", 610, "", None, ""),
    ("Belenus", "INVDE-MO-220V-10KW", "inversor", "Deye",
     "Inversor De Corrente Monofasico 2mppt 220v 10kw Deye", 10000, "mono", 220, ""),
    ("Intelbras", "EMSC-620B", "modulo", "Intelbras", "Módulo Intelbras EMSC-620B 620 W", 620, "", None, ""),
    ("Intelbras", "IONS-12K-T2-AFCI", "inversor", "Intelbras",
     "Inversor Intelbras IONS-12K T2 AFCI trifásico 380 V", 12000, "tri", 380, ""),
]

COTACOES = [
    {
        "distribuidor": "Belenus", "numero": "WEB-007005988", "kwp": "12.810",
        "total_produtos": "25683.58", "frete": "1982.86", "total": "27666.44",
        "observacao": "Kit de solo. Preço de 21/10/2026.",
        "itens": [
            ("MFTF-0.4-BF-132-610W", "Módulo Huansheng HSM-ND66-GR610-Y 610 W", "21", "un"),
            ("INVDE-MO-220V-10KW", "Inversor Deye SUN-10K-G02P1-EU-CM2-P 10 kW mono 220 V 2 MPPT", "1", "un"),
            ("", "Estrutura de solo mesa 8 módulos isopleta 45 m/s", "1", "un"),
            ("", "Cabo solar 4 mm preto", "100", "m"),
            ("", "Cabo solar 4 mm vermelho", "100", "m"),
            ("", "Conector MC4 (par)", "10", "par"),
        ],
    },
    {
        "distribuidor": "Intelbras", "numero": "PROJ26101627017", "kwp": "16.120",
        "total_produtos": "34874.60", "frete": "0", "total": "34874.60",
        "observacao": "Só o kit. A plataforma mostra R$ 46.158,60 porque soma a mão de obra da Optimus (16,12 × R$ 700).",
        "itens": [
            ("EMSC-620B", "Módulo Intelbras EMSC-620B 620 W", "26", "un"),
            ("IONS-12K-T2-AFCI", "Inversor Intelbras IONS-12K T2 AFCI tri 380 V", "1", "un"),
            ("", "Mesa modular Dynamo 6 módulos 45 m/s", "5", "un"),
            ("", "Finalizador de solo", "1", "un"),
            ("", "Cabo solar 4 mm preto", "100", "m"),
            ("", "Cabo solar 4 mm vermelho", "100", "m"),
            ("", "Conector MC4 (par)", "3", "par"),
        ],
    },
]


def carregar(apps, schema_editor):
    Equipamento = apps.get_model("propostas", "Equipamento")
    Cotacao = apps.get_model("propostas", "Cotacao")
    ItemCotado = apps.get_model("propostas", "ItemCotado")
    hoje = date(2026, 10, 21)

    for distribuidor, codigo, tipo, fabricante, descricao, potencia, fase, tensao, estrutura in EQUIPAMENTOS:
        Equipamento.objects.get_or_create(
            distribuidor=distribuidor, codigo=codigo,
            defaults={"tipo": tipo, "fabricante": fabricante, "descricao": descricao, "potencia_w": potencia,
                      "fase": fase, "tensao": tensao, "tipo_estrutura": estrutura},
        )

    for dados in COTACOES:
        if Cotacao.objects.filter(distribuidor=dados["distribuidor"], numero=dados["numero"]).exists():
            continue
        cotacao = Cotacao.objects.create(
            distribuidor=dados["distribuidor"], numero=dados["numero"], data=hoje, kwp=Decimal(dados["kwp"]),
            total_produtos=Decimal(dados["total_produtos"]), frete=Decimal(dados["frete"]),
            total=Decimal(dados["total"]), observacao=dados["observacao"],
        )
        for codigo, descricao, quantidade, unidade in dados["itens"]:
            equipamento = Equipamento.objects.filter(distribuidor=dados["distribuidor"], codigo=codigo).first() if codigo else None
            ItemCotado.objects.create(
                cotacao=cotacao, equipamento=equipamento, codigo=codigo, descricao=descricao,
                quantidade=Decimal(quantidade), unidade=unidade,
            )


class Migration(migrations.Migration):
    dependencies = [("propostas", "0007_catalogo_cotacoes")]
    operations = [migrations.RunPython(carregar, migrations.RunPython.noop)]
