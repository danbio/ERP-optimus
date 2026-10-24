"""Rodada 13: estrutura para mais de uma distribuidora e de um estado (H05, D47). Goiás sem dados."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from core import dados_oficiais
from core.forms import EmpresaForm
from core.models import ConfigEmpresa, Distribuidora, Municipio
from propostas.forms import Passo1Form
from propostas.models import TarifaVigente


@pytest.fixture
def goias(db):
    equatorial = Distribuidora.objects.create(nome="Equatorial Goiás", sigla_aneel="EQTL GO", uf="GO")
    anapolis = Municipio.objects.create(codigo_ibge=5201108, nome="Anápolis", uf="GO", latitude=-16.3, longitude=-48.9,
                                        irradiacao=[5.5] * 12, distribuidora=equatorial)
    tarifa = TarifaVigente.objects.create(distribuidora="Equatorial Goiás", tipo="B1", vigencia_inicio=date(2026, 10, 1),
                                          tusd=Decimal("0.5"), te=Decimal("0.3"), aliquota_tributos=Decimal("0.3"),
                                          fiob_kwh=Decimal("0.4"), atualizado_em=date(2026, 10, 1))
    return equatorial, anapolis, tarifa


def test_municipios_do_tocantins_vem_com_a_energisa(db):
    gurupi = Municipio.objects.get(codigo_ibge=1709500)
    assert gurupi.distribuidora.nome == "Energisa TO" and gurupi.distribuidora.sigla_aneel == "ETO"


def test_so_aparecem_os_municipios_dos_estados_atendidos(goias):
    _, anapolis, _ = goias
    assert anapolis not in Municipio.atendidos()
    config = ConfigEmpresa.obter()
    config.ufs_atendidas = "TO, GO"
    config.save()
    assert anapolis in Municipio.atendidos()
    assert anapolis in Passo1Form().fields["municipio"].queryset


def _passo1(municipio, tarifa):
    return Passo1Form({"nome": "Maria", "telefone": "(63) 99999-1234", "municipio": municipio.pk,
                       "ligacao": "mono", "tipo_tarifa": tarifa.pk})


def test_tarifa_de_outra_distribuidora_nao_passa_no_passo1(goias):
    _, anapolis, tarifa_go = goias
    config = ConfigEmpresa.obter()
    config.ufs_atendidas = "TO, GO"
    config.save()
    gurupi = Municipio.objects.get(codigo_ibge=1709500)
    form = _passo1(gurupi, tarifa_go)
    assert not form.is_valid() and "atendido pela Energisa TO" in str(form.errors["tipo_tarifa"])
    assert _passo1(anapolis, tarifa_go).is_valid()
    # Com duas distribuidoras, o vendedor vê de quem é cada tarifa.
    assert "B1 residencial · Equatorial Goiás" in [str(r) for _, r in form.fields["tipo_tarifa"].choices]


def test_estado_sem_distribuidora_nao_entra_nos_atendidos(db):
    config = ConfigEmpresa.obter()
    from django.forms.models import model_to_dict
    dados = {k: v for k, v in model_to_dict(config, fields=EmpresaForm.Meta.fields).items() if k != "logo"}
    dados |= {"cnpj": "43.324.626/0001-66", "razao_social": "Optimus", "endereco": "Rua 1",
              "etapas_padrao": "Aceite | assinatura"}
    form = EmpresaForm(dados | {"ufs_atendidas": "to, go"}, instance=config)
    assert not form.is_valid() and "GO ainda não tem distribuidora" in str(form.errors["ufs_atendidas"])
    assert not EmpresaForm(dados | {"ufs_atendidas": "XX"}, instance=config).is_valid()
    Distribuidora.objects.create(nome="Equatorial Goiás", uf="GO")
    form = EmpresaForm(dados | {"ufs_atendidas": "to; go"}, instance=config)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["ufs_atendidas"] == "TO, GO"


def test_atualizacao_da_aneel_passa_por_cada_distribuidora(goias, monkeypatch):
    pedidas = []
    monkeypatch.setattr(dados_oficiais, "_registros_aneel_tarifas", lambda sigla, sub: pedidas.append(sigla) or [])
    texto = dados_oficiais.atualizar_tarifas()
    assert set(pedidas) == {"ETO", "EQTL GO"}
    assert "Energisa TO" in texto and "Equatorial Goiás" in texto


def test_uc_da_fatura_recebe_a_distribuidora_do_municipio(base):
    from .test_rodada6 import FATURA_SEM_CPF
    from .test_proposta_v2 import _ate_passo2
    _, proposta = _ate_passo2(base, **FATURA_SEM_CPF)
    assert proposta.uc.concessionaria == "Energisa TO"


def test_tela_de_tarifas_mostra_a_distribuidora_quando_ha_mais_de_uma(goias):
    from django.test import Client as Navegador
    html = Navegador().get(reverse("core:config_tarifas")).content.decode()
    assert "<th>Distribuidora</th>" in html and "Equatorial Goiás" in html
