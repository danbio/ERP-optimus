"""Rodada 1 do plano de correções: travas de cálculo e emissão (A01, A02, A03, A06)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client as Navegador
from django.urls import reverse

from core.models import ConfigEmpresa
from propostas.views import documento
from propostas.models import Cotacao, Equipamento, Proposta
from propostas.services import calculo
from propostas.montagem import impedimentos_de_emissao, montar

from .test_proposta_v2 import _ate_passo2, _passo1, _passo2, _passo3


@pytest.fixture(autouse=True)
def sem_chromium(monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(documento, "html_para_pdf", lambda html: b"%PDF-1.4 falso")


def _rascunho(base, passo3=None, **passo2):
    navegador, proposta = _ate_passo2(base, **passo2)
    _passo3(navegador, proposta, **(passo3 or {}))
    proposta.refresh_from_db()
    return navegador, proposta


def _emitir(navegador, proposta):
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    proposta.refresh_from_db()


# A03: disponibilidade fora do dimensionamento e da economia (D33).

def test_disponibilidade_nao_entra_no_dimensionamento(base):
    _, proposta = _rascunho(base, origem_consumo="kwh", kwh_informado="400", conta_informada="")
    assert ConfigEmpresa.obter().premissas_padrao["cobrar_disponibilidade"] is False
    m = montar(proposta)
    assert m.consumo_alvo == pytest.approx(400 * 1.10)
    assert calculo.geracao_necessaria(400, 0.10) == pytest.approx(440)  # sem os 30 kWh da disponibilidade


def test_conta_com_sistema_nao_fica_abaixo_do_minimo(base):
    _, proposta = _rascunho(base)
    m = montar(proposta)
    minimo = m.disponibilidade * m.tarifa_kwh + m.iluminacao
    assert m.conta_com_sistema >= minimo - 0.01
    assert m.conta_com_sistema == pytest.approx(max(m.conta_hoje - m.resultado.economia_mensal_ano1, minimo))


# A02: emissão bloqueada; acima de 75 kWp só avisa.

def test_mao_de_obra_zerada_bloqueia_a_emissao(base):
    navegador, proposta = _rascunho(base, passo3={"mao_de_obra": "0,00"})
    assert any("mão de obra" in motivo for motivo in impedimentos_de_emissao(montar(proposta)))
    _emitir(navegador, proposta)
    assert proposta.status == "rascunho"


def test_alerta_de_erro_bloqueia_a_emissao(base):
    # Ligação monofásica com inversor trifásico escolhido à mão: erro de fase.
    trifasico = Equipamento.objects.filter(tipo="inversor", ativo=True, fase="tri").first()
    navegador, proposta = _rascunho(base)
    proposta.inversor = trifasico
    proposta.save(update_fields=["inversor"])
    m = montar(proposta)
    assert any("Ligação monofásica" in motivo for motivo in impedimentos_de_emissao(m))
    _emitir(navegador, proposta)
    assert proposta.status == "rascunho"


def test_acima_de_75_kwp_so_avisa(base):
    _, proposta = _rascunho(base, origem_consumo="kwh", kwh_informado="12000", conta_informada="", confirmo="on")
    m = montar(proposta)
    assert m.kwp > 75
    aviso = next(a for a in m.alertas if "microgeração" in a["texto"])
    assert aviso["tipo"] == "aviso" and not aviso["interno"]


# A01: cotação de outro tamanho ou de outro distribuidor.

def _cotacao(m, kwp, distribuidor=None, validade=None):
    return Cotacao.objects.create(
        distribuidor=distribuidor or m.modulo.distribuidor, numero="T-1", data=date.today(), validade=validade,
        kwp=Decimal(str(kwp)), total_produtos=Decimal("10000"), total=Decimal("10000"))


def test_cotacao_de_outro_tamanho_bloqueia_e_sugere_a_quantidade(base):
    navegador, proposta = _rascunho(base)
    m = montar(proposta)
    cotacao = _cotacao(m, round(m.kwp * 2, 2))
    _passo3(navegador, proposta, cotacao=cotacao.pk, modulo=m.modulo.pk)
    proposta.refresh_from_db()
    m = montar(proposta)
    assert any("Use" in a["texto"] and "módulos" in a["texto"] for a in m.alertas if a["tipo"] == "erro")
    _emitir(navegador, proposta)
    assert proposta.status == "rascunho"


def test_cotacao_do_mesmo_tamanho_emite(base):
    navegador, proposta = _rascunho(base)
    m = montar(proposta)
    cotacao = _cotacao(m, round(m.kwp, 3))
    _passo3(navegador, proposta, cotacao=cotacao.pk, modulo=m.modulo.pk)
    proposta.refresh_from_db()
    assert not impedimentos_de_emissao(montar(proposta))


def test_cotacao_de_outro_distribuidor_bloqueia(base):
    navegador, proposta = _rascunho(base)
    m = montar(proposta)
    cotacao = _cotacao(m, round(m.kwp, 3), distribuidor="Outro Distribuidor")
    _passo3(navegador, proposta, cotacao=cotacao.pk, modulo=m.modulo.pk)
    proposta.refresh_from_db()
    assert any("Outro Distribuidor" in motivo for motivo in impedimentos_de_emissao(montar(proposta)))


def test_cotacao_vencida_nao_aparece_para_escolher(base):
    navegador, proposta = _rascunho(base)
    m = montar(proposta)
    vencida = _cotacao(m, round(m.kwp, 3), validade=date.today() - timedelta(days=1))
    resposta = _passo3(navegador, proposta, cotacao=vencida.pk, modulo=m.modulo.pk)
    assert resposta.status_code == 200  # recusada pelo formulário
    proposta.refresh_from_db()
    assert proposta.cotacao_id is None


# A06: plausibilidade dos dados do passo 2.

def test_conta_muito_alta_pede_confirmacao(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    resposta = _passo2(navegador, proposta, base, conta_informada="50.000,00")
    assert resposta.status_code == 200
    assert "Confirmo" in resposta.content.decode() or "confirm" in resposta.content.decode().lower()
    proposta.refresh_from_db()
    assert proposta.conta_informada is None or proposta.conta_informada != Decimal("50000")
    assert _passo2(navegador, proposta, base, conta_informada="50.000,00", confirmo="on").status_code == 302


def test_previa_calcula_sem_pedir_confirmacao(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    dados = {"origem_consumo": "rs", "conta_informada": "50.000,00", "iluminacao_publica": "30,00",
             "bandeira": base["verde"].pk, "kwh_informado": "", "folga": "10", "perfil_simultaneidade": base["perfil"]}
    resposta = navegador.post(reverse("propostas:previa", args=[proposta.pk, 2]), dados)
    assert resposta.status_code == 200


def _fatura(**mudancas):
    dados = {"origem_consumo": "fatura", "conta_informada": "", "numero_uc": "123456", "endereco": "Rua 1",
             "competencia": "2026-09-01", "fatura_kwh": "620", "dias_ciclo": "31", "valor_fatura": "845,30",
             "cpf_cnpj": "529.982.247-25"}
    return dados | mudancas


@pytest.mark.parametrize("mudancas", [
    {"competencia": (date.today().replace(day=1) + timedelta(days=40)).isoformat()},  # mês futuro
    {"competencia": "2024-01-01"},                                                      # mais de 13 meses
    {"numero_uc": "x"},
    {"numero_uc": "12"},
])
def test_fatura_malformada_e_recusada(base, mudancas):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    assert _passo2(navegador, proposta, base, **_fatura(**mudancas)).status_code == 200
    proposta.refresh_from_db()
    assert proposta.nivel == "estimativa"


def test_fatura_com_tarifa_fora_do_normal_pede_confirmacao(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    # 620 kWh por R$ 100: R$ 0,16/kWh, muito abaixo da tarifa vigente.
    assert _passo2(navegador, proposta, base, **_fatura(valor_fatura="100,00")).status_code == 200
    assert _passo2(navegador, proposta, base, **_fatura(valor_fatura="100,00"), confirmo="on").status_code == 302


def test_limites_vem_das_configuracoes(base):
    config = ConfigEmpresa.obter()
    config.conta_alta = Decimal("100000")
    config.save()
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    assert _passo2(navegador, proposta, base, conta_informada="50.000,00").status_code == 302
