from django.core.management.base import BaseCommand

from core.dados_oficiais import atualizar_irradiacao, municipios_para_atualizar
from core.models import Municipio


class Command(BaseCommand):
    help = "Baixa da NASA POWER a irradiação dos municípios sem dado ou com dado de mais de 1 ano (D27)."

    def add_arguments(self, parser):
        parser.add_argument("--uf", help="Só os municípios desta UF (ex.: TO).")
        parser.add_argument("--todos", action="store_true", help="Atualiza mesmo quem já tem dado recente.")

    def handle(self, *args, uf=None, todos=False, **opcoes):
        municipios = Municipio.objects.filter(uf=uf.upper()) if (todos and uf) else (
            Municipio.objects.all() if todos else municipios_para_atualizar([uf] if uf else None)
        )
        total = municipios.count()
        self.stdout.write(f"{total} municípios para atualizar...")
        atualizados, erros = atualizar_irradiacao(municipios)
        self.stdout.write(f"{atualizados} atualizados.")
        for erro in erros:
            self.stderr.write(erro)
