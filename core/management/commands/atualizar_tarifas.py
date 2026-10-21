from django.core.management.base import BaseCommand

from core.dados_oficiais import atualizar_bandeiras, atualizar_tarifas


class Command(BaseCommand):
    help = "Baixa da ANEEL as tarifas do Grupo B da Energisa TO e o adicional das bandeiras (D21, D27)."

    def handle(self, *args, **opcoes):
        self.stdout.write(atualizar_tarifas())
        self.stdout.write(atualizar_bandeiras())
