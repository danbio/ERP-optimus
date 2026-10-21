"""Fatia v2.1: cadastro, lista e ficha de clientes; municípios do IBGE; menu."""

import pytest
from django.test import Client as Navegador
from django.urls import reverse

from clientes.models import Cliente
from core.models import Municipio


@pytest.fixture
def gurupi(db):
    return Municipio.objects.get(codigo_ibge=1709500)


def test_carga_dos_municipios_do_to(db):
    assert Municipio.objects.filter(uf="TO").count() == 139
    sao_valerio = Municipio.objects.get(codigo_ibge=1720499)
    assert sao_valerio.nome == "São Valério"
    assert len(sao_valerio.irradiacao) == 12  # veio da antiga IrradiacaoMunicipio


def test_cadastro_minimo_grava_so_digitos(gurupi):
    resposta = Navegador().post(reverse("clientes:cliente_novo"), {
        "nome": "  Maria   Souza ", "telefone": "(63) 99999-1234", "municipio": gurupi.pk,
        "cpf_cnpj": "529.982.247-25",
    })
    cliente = Cliente.objects.get()
    assert resposta.status_code == 302
    assert resposta.url == reverse("clientes:ficha", args=[cliente.pk])
    assert (cliente.nome, cliente.telefone, cliente.cpf_cnpj) == ("Maria Souza", "63999991234", "52998224725")
    assert cliente.telefone_formatado == "(63) 99999-1234"


def test_cadastro_recusa_dados_malformados(gurupi):
    resposta = Navegador().post(reverse("clientes:cliente_novo"), {
        "nome": "Maria", "telefone": "9999", "municipio": gurupi.pk, "cpf_cnpj": "123abc",
    })
    assert resposta.status_code == 200
    assert not Cliente.objects.exists()
    erros = resposta.context["form"].errors
    assert "cpf_cnpj" in erros and "telefone" in erros


def test_cpf_repetido_mostra_quem_ja_tem(gurupi):
    Cliente.objects.create(nome="João", telefone="63999991234", cpf_cnpj="52998224725")
    resposta = Navegador().post(reverse("clientes:cliente_novo"), {
        "nome": "Outro", "telefone": "63988887777", "cpf_cnpj": "529.982.247-25",
    })
    assert "João" in resposta.context["form"].errors["cpf_cnpj"][0]


def test_cadastro_vindo_da_proposta_volta_para_ela(gurupi):
    destino = reverse("propostas:nova")
    resposta = Navegador().post(f"{reverse('clientes:cliente_novo')}?next={destino}", {
        "nome": "Maria", "telefone": "63999991234",
    })
    assert resposta.url == f"{destino}?cliente={Cliente.objects.get().pk}"


def test_busca_por_nome_e_telefone(db):
    Cliente.objects.create(nome="Maria Souza", telefone="63999991234")
    Cliente.objects.create(nome="Pedro Lima", telefone="63988887777")
    navegador = Navegador()
    assert [c.nome for c in navegador.get(reverse("clientes:lista"), {"busca": "souza"}).context["clientes"]] == ["Maria Souza"]
    assert [c.nome for c in navegador.get(reverse("clientes:lista"), {"busca": "8888-7777"}).context["clientes"]] == ["Pedro Lima"]


def test_ficha_e_edicao(gurupi):
    cliente = Cliente.objects.create(nome="Maria", telefone="63999991234")
    navegador = Navegador()
    assert navegador.get(reverse("clientes:ficha", args=[cliente.pk])).status_code == 200
    formulario = navegador.get(reverse("clientes:cliente_editar", args=[cliente.pk]))
    assert formulario.context["form"].initial["telefone"] == "(63) 99999-1234"
    navegador.post(reverse("clientes:cliente_editar", args=[cliente.pk]), {
        "nome": "Maria Souza", "telefone": "(63) 99999-1234", "municipio": gurupi.pk,
    })
    cliente.refresh_from_db()
    assert (cliente.nome, cliente.municipio) == ("Maria Souza", gurupi)


def test_menu_sem_link_morto(db):
    html = Navegador().get(reverse("core:inicio")).content.decode()
    assert 'href="#"' not in html
    assert reverse("clientes:lista") in html
