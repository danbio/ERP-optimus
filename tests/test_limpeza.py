"""Rodada 3 do plano de correções: limpeza antes das regras novas (A24–A28)."""

from datetime import date
from decimal import Decimal

import pytest
from django.test import Client as Navegador
from django.urls import NoReverseMatch, reverse

from core.models import ConfigEmpresa
from propostas.models import Proposta
from propostas.montagem import montar
from propostas.services import calculo

from .test_proposta_v2 import _ate_passo2, _passo3


def _rascunho(base, **passo2):
    navegador, proposta = _ate_passo2(base, **passo2)
    _passo3(navegador, proposta)
    proposta.refresh_from_db()
    return navegador, proposta


@pytest.mark.parametrize("rota", ["legado_nova", "recalcular", "kit_nova_linha", "fatura_novo"])
def test_fluxo_da_fatia4_saiu(rota):
    with pytest.raises(NoReverseMatch):
        reverse(f"propostas:{rota}")


def test_geracao_por_kwp_e_a_mesma_do_dimensionamento():
    irradiacao = [5.0] * 12
    por_kwp = calculo.geracao_por_kwp_mes(irradiacao, 0.14, 0.01, 1.0)
    assert por_kwp == pytest.approx(5.0 * 365 / 12 * 0.86 * 0.99)
    assert calculo.kwp_necessario(400, 0.1, irradiacao, 0.14, 0.01, 1.0) == pytest.approx(440 / por_kwp)


def test_sem_economia_nao_quebra_e_bloqueia(base):
    _, proposta = _rascunho(base)
    proposta.qtd_modulos = 1
    proposta.kwh_informado, proposta.origem_consumo, proposta.conta_informada = Decimal("1"), "kwh", None
    proposta.save()
    m = montar(proposta)  # antes: ZeroDivisionError quando a economia dava zero
    assert m.resultado is not None


def test_limites_de_cobertura_vem_das_premissas(base):
    config = ConfigEmpresa.obter()
    config.premissas_padrao = config.premissas_padrao | {"cobertura_max": 1.0, "cobertura_min": 0.99}
    config.save()
    _, proposta = _rascunho(base)
    textos = [a["texto"] for a in montar(proposta).alertas]
    assert any("Cobertura de" in t and ("acima de 100%" in t or "abaixo de 99%" in t) for t in textos)


def test_lista_mostra_kwp_gravado_e_filtra_por_mes(base):
    navegador, proposta = _rascunho(base)
    assert proposta.kwp and proposta.kwp == Decimal(f"{montar(proposta).kwp:.3f}")
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    proposta.refresh_from_db()
    hoje = date.today()
    html = navegador.get(reverse("propostas:lista"), {"mes": f"{hoje:%Y-%m}"}).content.decode()
    assert proposta.numero in html and f"{proposta.kwp:.2f}".replace(".", ",") in html
    html = navegador.get(reverse("propostas:lista"), {"mes": "2020-01"}).content.decode()
    assert proposta.numero not in html and "Nenhuma proposta com estes filtros" in html


def test_lista_paginada(base):
    _, proposta = _rascunho(base)
    for _ in range(55):
        proposta.pk = None
        proposta.save()
    navegador = Navegador()
    html = navegador.get(reverse("propostas:lista")).content.decode()
    assert "Página 1 de 2" in html
    html = navegador.get(reverse("propostas:lista"), {"pagina": "2"}).content.decode()
    assert "Página 2 de 2" in html
    assert Proposta.objects.count() == 56
