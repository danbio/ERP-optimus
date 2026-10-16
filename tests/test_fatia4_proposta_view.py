"""Teste de integração — cria a proposta do caso Alesio pela view de verdade
(POST em propostas:nova) e confere economia mensal e payback contra
docs/caso-referencia.md. Usa a carga inicial das migrations (irradiação de
São Valério da Natividade, Fio B, ConfigEmpresa) — não recria esses dados.
"""

from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from clientes.models import Cliente, UnidadeConsumidora
from propostas.models import FaturaReferencia, Proposta

TOL = 0.005  # ±0,5%


@pytest.fixture
def uc_alesio(db):
    cliente = Cliente.objects.create(
        nome="Alesio Matte",
        razao_social="Distribuidora Stilus",
        cpf_cnpj="12.345.678/0001-90",  # CNPJ: dispara o alerta de classe B1 + pessoa jurídica
    )
    return UnidadeConsumidora.objects.create(
        cliente=cliente,
        numero_uc="20.008.015-05",
        endereco="Av. Tocantins, 1255, Qd. 40, Lt. 16 – Centro",
        municipio="São Valério da Natividade",
        uf="TO",
        classe=UnidadeConsumidora.Classe.B1,
        ligacao=UnidadeConsumidora.Ligacao.TRI,
    )


@pytest.fixture
def fatura_alesio(uc_alesio):
    return FaturaReferencia.objects.create(
        uc=uc_alesio,
        competencia=date(2026, 9, 1),
        kwh=5560,
        dias_ciclo=28,
        valor_total="7762.74",
        tarifa_kwh="1.372680",
        valor_distribuicao="2458.63",
        impostos="2128.86",
    )


def _dados_formulario(uc, fatura):
    return {
        "uc": uc.pk,
        "fatura": fatura.pk,
        "investimento": "92502.81",
        "forma_pagamento": "A combinar",
        "validade_dias": "15",
        "beneficios": "",
        "escopo": "",
        "texto_sobre": "",
        "perdas": "0.18",
        "perda_clipping": "0.015",
        "ano_conexao": "2027",
        "simultaneidade": "0.50",
        "reajuste_anual": "0.04",
        "degradacao_ano1": "0.01",
        "degradacao_anual": "0.004",
        "cobrar_disponibilidade": "on",
        "horizonte_anos": "25",
        "razao_cc_ca_max": "1.30",
        "proximo_indice": "2",
        "kit-0-tipo": "modulo",
        "kit-0-descricao": "Módulo Huansheng HSM-ND66-GR615-Y",
        "kit-0-modelo": "N-type bifacial",
        "kit-0-quantidade": "90",
        "kit-0-potencia_w": "615",
        "kit-1-tipo": "inversor",
        "kit-1-descricao": "Inversor Deye SUN-20K-G05",
        "kit-1-modelo": "trifásico 380V",
        "kit-1-quantidade": "2",
        "kit-1-potencia_w": "20000",
    }


@pytest.mark.django_db
def test_criar_proposta_alesio_pela_view(uc_alesio, fatura_alesio):
    cliente_http = Client()

    resposta_get = cliente_http.get(reverse("propostas:nova"))
    assert resposta_get.status_code == 200

    resposta_post = cliente_http.post(
        reverse("propostas:nova"), data=_dados_formulario(uc_alesio, fatura_alesio)
    )
    if resposta_post.status_code != 302:
        erros = resposta_post.context["proposta_form"].errors
        assert resposta_post.status_code == 302, f"Formulário não salvou: {erros}"

    proposta = Proposta.objects.get()
    assert proposta.numero.startswith("OPT-")
    assert proposta.status == Proposta.Status.RASCUNHO
    assert proposta.cliente == uc_alesio.cliente
    assert proposta.kwp == pytest.approx(55.35, rel=TOL)
    assert proposta.kw_ca == pytest.approx(40.0, rel=TOL)

    resultados = proposta.resultados
    assert resultados["economia_mensal_ano1"] == pytest.approx(6_773.54, rel=TOL)
    assert resultados["payback_meses"] == pytest.approx(13.7, abs=0.2)

    texto_alertas = " ".join(resultados["alertas"])
    assert "B1" in texto_alertas
    assert "CC/CA" in texto_alertas
