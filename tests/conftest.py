"""Configuração comum dos testes."""

from decimal import Decimal
from pathlib import Path

import pytest
from django.test import Client
from django.utils import timezone

from core.models import ConfigEmpresa, Municipio
from propostas.models import Bandeira, Equipamento, TarifaVigente, TaxaFinanciamento
from propostas.services.catalogo_belenus import DISTRIBUIDOR, ler_catalogo_belenus

CATALOGO_BELENUS = Path(__file__).parent / "dados" / "belenus-catalogo-2026-10-21.csv"


def importar_catalogo(data=None):
    """O catálogo Belenus real de 21/10/2026, com os preços datados de hoje (ou de `data`)."""
    data = data or timezone.localdate()
    for item in ler_catalogo_belenus(CATALOGO_BELENUS.read_text(encoding="utf-8-sig")):
        item.pop("foto")
        Equipamento.objects.update_or_create(
            distribuidor=DISTRIBUIDOR, codigo=item["codigo"],
            defaults=item | {"preco_em": data if item["preco_referencia"] else None},
        )


@pytest.fixture(autouse=True)
def entrar_como_gestor(request, monkeypatch):
    """Todo o ERP exige login (D36). Nos testes que usam o banco, cada navegador já entra como gestor.

    Teste de login ou de permissão: chame navegador.logout() ou entre com outro usuário.
    """
    if "db" not in request.fixturenames and not request.node.get_closest_marker("django_db"):
        return
    request.getfixturevalue("db")
    from django.contrib.auth.models import User

    gestor = User.objects.create(username="gestor_teste", is_superuser=True, is_staff=True)
    criar = Client.__init__

    def criar_e_entrar(self, *args, **kwargs):
        criar(self, *args, **kwargs)
        self.force_login(gestor)

    monkeypatch.setattr(Client, "__init__", criar_e_entrar)


@pytest.fixture
def base(db):
    """Tarifas com tributos e Fio B preenchidos pelo gestor, duas taxas de financiamento e o catálogo Belenus."""
    importar_catalogo()
    TarifaVigente.objects.update(aliquota_tributos=Decimal("0.25"), fiob_kwh=Decimal("0.30"))
    TaxaFinanciamento.objects.create(banco="BV", prazo_meses=60, taxa_mensal=Decimal("0.0159"), vigente_desde="2026-10-21")
    TaxaFinanciamento.objects.create(banco="BV", prazo_meses=12, taxa_mensal=Decimal("0.0139"), vigente_desde="2026-10-21")
    return {
        "b1": TarifaVigente.objects.get(tipo="B1"),
        "gurupi": Municipio.objects.get(codigo_ibge=1709500),
        "verde": Bandeira.objects.get(nome="Verde"),
        "perfil": ConfigEmpresa.obter().perfis_simultaneidade[0]["nome"],
    }
