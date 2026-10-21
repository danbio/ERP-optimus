"""Grava o catálogo Belenus no banco (D28).

Uso (PowerShell, na pasta do projeto):
    python manage.py importar_belenus importar\\belenus\\belenus-catalogo.csv

Fotos e datasheets são procurados ao lado do CSV, em fotos\\<codigo>.jpg e
datasheets\\<codigo>.pdf, e copiados para a pasta media.
"""

from datetime import date, datetime
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from propostas.models import Equipamento
from propostas.services.catalogo_belenus import DISTRIBUIDOR, ler_catalogo_belenus


class Command(BaseCommand):
    help = "Importa o CSV do catálogo Belenus (gerado por importar/extrair_belenus.py)."

    def add_arguments(self, parser):
        parser.add_argument("csv", help="Caminho do belenus-catalogo.csv")
        parser.add_argument("--data", help="Data dos preços (AAAA-MM-DD). Padrão: data do arquivo.")

    def handle(self, *args, **opcoes):
        caminho = Path(opcoes["csv"])
        pasta = caminho.parent
        if opcoes["data"]:
            data_precos = date.fromisoformat(opcoes["data"])
        else:
            data_precos = datetime.fromtimestamp(caminho.stat().st_mtime).date()

        itens = ler_catalogo_belenus(caminho.read_text(encoding="utf-8-sig"))
        novos = atualizados = fotos = datasheets = 0
        for item in itens:
            foto = item.pop("foto")
            equipamento, criado = Equipamento.objects.update_or_create(
                distribuidor=DISTRIBUIDOR, codigo=item["codigo"],
                defaults=item | {"preco_em": data_precos if item["preco_referencia"] else None},
            )
            novos += criado
            atualizados += not criado

            arquivo_foto = pasta / "fotos" / foto if foto else None
            if arquivo_foto and arquivo_foto.is_file() and not equipamento.foto:
                with arquivo_foto.open("rb") as f:
                    equipamento.foto.save(arquivo_foto.name, File(f), save=True)
                fotos += 1
            arquivo_pdf = pasta / "datasheets" / f"{item['codigo']}.pdf"
            if arquivo_pdf.is_file() and not equipamento.datasheet:
                with arquivo_pdf.open("rb") as f:
                    equipamento.datasheet.save(arquivo_pdf.name, File(f), save=True)
                datasheets += 1

        self.stdout.write(
            f"{len(itens)} itens da Belenus: {novos} novos, {atualizados} atualizados, "
            f"{fotos} fotos e {datasheets} datasheets copiados. Preços de {data_precos:%d/%m/%Y}."
        )
