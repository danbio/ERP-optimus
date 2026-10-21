from django.core.management.base import BaseCommand

from core.dados_oficiais import importar_municipios


class Command(BaseCommand):
    help = "Importa os municípios de uma UF com coordenadas (IBGE, via kelvins/municipios-brasileiros)."

    def add_arguments(self, parser):
        parser.add_argument("uf", help="Sigla da UF, ex.: GO")

    def handle(self, *args, uf, **opcoes):
        self.stdout.write(importar_municipios(uf))
