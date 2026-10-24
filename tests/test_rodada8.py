"""Rodada 8: endereço do cliente com CEP e CNPJ (H12, D42) e dados da fatura no cadastro (H15)."""

import pytest
from django.test import Client as Navegador
from django.urls import reverse

from clientes.forms import ClienteForm
from clientes.models import Cliente
from core.validacoes import limpar_cep

from .test_proposta_v2 import _ate_passo2, _passo2
from .test_rodada6 import FATURA_SEM_CPF


def test_limpar_cep():
    assert limpar_cep("77400000") == limpar_cep("77.400-000") == "77400-000"
    assert limpar_cep("") == ""
    with pytest.raises(ValueError):
        limpar_cep("7740")


def test_cliente_com_endereco(db):
    form = ClienteForm({"nome": "Maria", "telefone": "(63) 99999-1234", "cep": "77400000",
                        "logradouro": "  Rua 7 ", "numero": "120", "bairro": "Centro"})
    assert form.is_valid(), form.errors
    cliente = form.save()
    assert cliente.endereco_completo == "Rua 7, 120, Centro, CEP 77400-000"


def test_cliente_com_cep_errado(db):
    form = ClienteForm({"nome": "Maria", "telefone": "(63) 99999-1234", "cep": "123"})
    assert not form.is_valid() and "cep" in form.errors


def test_tela_do_cliente_tem_busca_por_cep_e_cnpj(db):
    html = Navegador().get(reverse("clientes:cliente_novo")).content.decode()
    assert 'id="municipios-ibge"' in html and "1709500" in html  # Gurupi
    assert "data-busca-cep" in html and "data-busca-cnpj" in html and "js/cliente.js" in html


def test_fatura_completa_o_endereco_do_cliente_sem_endereco(base):
    _, proposta = _ate_passo2(base, **FATURA_SEM_CPF)
    assert proposta.cliente.logradouro == "Rua 1, Centro"


def test_fatura_nao_troca_o_endereco_que_o_cliente_ja_tem(base):
    navegador, proposta = _ate_passo2(base)
    Cliente.objects.filter(pk=proposta.cliente_id).update(logradouro="Av. Goiás, 10")
    _passo2(navegador, proposta, base, **FATURA_SEM_CPF)
    proposta.refresh_from_db()
    assert proposta.cliente.logradouro == "Av. Goiás, 10"
    assert proposta.uc.endereco == "Rua 1, Centro"  # o da instalação fica na UC


def test_fatura_de_outro_titular_nao_troca_o_cpf_do_cliente(base):
    navegador, proposta = _ate_passo2(base)
    Cliente.objects.filter(pk=proposta.cliente_id).update(cpf_cnpj="52998224725")
    resposta = _passo2(navegador, proposta, base, **(FATURA_SEM_CPF | {"cpf_cnpj": "111.444.777-35"}))
    assert "já tem o CPF/CNPJ" in resposta.content.decode()
    assert Cliente.objects.get(pk=proposta.cliente_id).cpf_cnpj == "52998224725"
