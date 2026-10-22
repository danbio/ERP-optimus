"""Configuração comum dos testes."""

import pytest
from django.test import Client


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
