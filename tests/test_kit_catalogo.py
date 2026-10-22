"""Rodada 4 do plano de correções: kit montado pelo catálogo (D34) e cotação que substitui o catálogo (D35)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import ConfigEmpresa
from propostas.models import Cotacao, Equipamento, ItemCotado
from propostas.montagem import impedimentos_de_emissao, montar
from propostas.services import calculo
from propostas.services.catalogo_belenus import funcao_no_kit, mppts, pecas_por_embalagem
from propostas.views import documento

from .conftest import importar_catalogo
from .test_proposta_v2 import _ate_passo2, _passo3


@pytest.fixture(autouse=True)
def sem_chromium(monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(documento, "html_para_pdf", lambda html: b"%PDF-1.4 falso")


def _rascunho(base, passo3=None, **passo2):
    navegador, proposta = _ate_passo2(base, **passo2)
    resposta = _passo3(navegador, proposta, **(passo3 or {}))
    proposta.refresh_from_db()
    return navegador, proposta, resposta


def _linha(m, funcao):
    return next((linha for linha in m.kit if linha.funcao == funcao), None)


# ---------- Leitura do catálogo ----------

@pytest.mark.parametrize("descricao, funcao", [
    ("Perfil Fixacao Modulo Fotov. 31.9mm X 53.8mm X 2.36m Aluminio", "trilho"),
    ("Perfil Fixacao Modulo Fotov. 31.9mm X 53.8mm X 1.23m Aluminio", ""),
    ("Grampo Final 35mm 4 Pecas Aluminio Belenergy", "grampo_final"),
    ("Grampo Final 30 Mm Para Telha Zipada 4 Pecas Aluminio Belenergy", ""),
    ("Grampo Intermediario 2 Pecas Aluminio Belenergy", "grampo_intermediario"),
    ("Garra Aterramento 2 Pecas Aluminio Belenergy", "aterramento"),
    ("Suporte Gancho Ajustavel Colonial C/ Prolongador 2 Pecas Galvanizado A Fogo", "fixacao"),
    ("Mini Trilho Telha Metalica 2 Pecas Aluminio Belenergy", "mini_trilho"),
    ("Mini Trilho Alto Telha Metalica Para Microinversor 300mm 2p 2 Pecas Aluminio Belenergy", ""),
    ("Cabo Solar 4mm 0.6/1kv Ac 1.8kv Dc Preto", "cabo_preto"),
    ("Cabo Ca Flex 750v 4.00mm 100m Preto", ""),
    ("Conector Solar Fotovoltaico Macho E Femea C/2 Pares", "conector"),
])
def test_papel_no_kit_pela_descricao(descricao, funcao):
    assert funcao_no_kit(descricao) == funcao


def test_pecas_e_mppt_pela_descricao():
    assert pecas_por_embalagem("Grampo Final 35mm 4 Pecas Aluminio") == 4
    assert pecas_por_embalagem("Conector Solar Fotovoltaico Macho E Femea C/2 Pares") == 2
    assert pecas_por_embalagem("Suporte Ajustavel P/ Laje 1 Peca Aluminio") == 1
    assert pecas_por_embalagem("Perfil Fixacao Modulo Fotov. 2.36m Aluminio") == 1
    assert mppts("Inversor De Corrente Monofasico 3mppt 220v 10kw Growatt") == 3
    assert mppts("Microinversor De Corrente Monofasico 4mmpt 220v 2kw Hyxipower") == 4


# ---------- Funções puras (D34) ----------

def test_escolher_modulo_pelo_menor_rs_por_wp():
    modulos = [{"w": 610, "preco": 517.89}, {"w": 425, "preco": 318.75}, {"w": 700, "preco": None}]
    assert calculo.escolher_modulo(modulos)["w"] == 425
    assert calculo.escolher_modulo([{"w": 500, "preco": 400}, {"w": 600, "preco": 480}])["w"] == 600  # empate
    assert calculo.escolher_modulo([{"w": 500, "preco": None}, {"w": 600, "preco": None}])["w"] == 600


def test_inversor_mais_barato_dentro_da_faixa_de_sobrecarga():
    inversores = [
        {"nome": "3 kW", "kw": 3, "fase": "mono", "preco": 1165},
        {"nome": "5 kW", "kw": 5, "fase": "mono", "preco": 1669},
        {"nome": "6 kW", "kw": 6, "fase": "mono", "preco": 1675},
        {"nome": "10 kW", "kw": 10, "fase": "mono", "preco": 1974},
    ]
    # 6 kWp: 5 kW (1,2) e 6 kW (1,0) estão na faixa 0,8–1,5; o 5 kW é o mais barato.
    assert calculo.sugerir_inversor(6, inversores, "mono", 1.5, 0.8)[0]["nome"] == "5 kW"
    # 2 kWp: nenhum na faixa (3 kW dá 0,67): fica o menor que aguenta.
    assert calculo.sugerir_inversor(2, inversores, "mono", 1.5, 0.8)[0]["nome"] == "3 kW"
    # 20 kWp: nenhum aguenta sozinho.
    assert calculo.sugerir_inversor(20, inversores, "mono", 1.5, 0.8) == (inversores[3], 2)


def test_microinversor_de_menor_custo_total():
    micros = [
        {"nome": "Enphase", "w": 475, "modulos": 1, "preco": 314.65},
        {"nome": "Hyxipower", "w": 2000, "modulos": 4, "preco": 903.06},
        {"nome": "Growatt", "w": 2250, "modulos": 4, "preco": 957.20},
    ]
    micro, qtd = calculo.sugerir_micro(10, 425, micros, 1.5)
    assert (micro["nome"], qtd) == ("Hyxipower", 3)
    # Módulo de 715 W: 4 × 715 / 2000 = 1,43 ainda cabe; o Enphase (715/475 = 1,51) não.
    assert calculo.sugerir_micro(8, 715, micros, 1.5)[0]["nome"] == "Hyxipower"
    assert calculo.sugerir_micro(8, 800, micros[:1], 1.5) == (None, 0)


@pytest.mark.parametrize("modulos, mppts_total, esperado", [
    (10, 2, 2),   # 5 + 5
    (6, 2, 1),    # 3 + 3 fica abaixo do mínimo de 4
    (30, 3, 3),
    (40, 3, 4),   # 13 por string passa do máximo de 12
    (2, 1, 1),
])
def test_strings_do_inversor(modulos, mppts_total, esperado):
    assert calculo.strings_do_inversor(modulos, mppts_total, 4, 12) == esperado


def test_dividir_em_fileiras():
    assert calculo.dividir_em_fileiras(11, 2) == [6, 5]
    assert calculo.dividir_em_fileiras(10, 2) == [5, 5]
    assert calculo.dividir_em_fileiras(3, 5) == [1, 1, 1]


def test_quantidades_da_estrutura_ceramica():
    pecas = {"grampo_final": 4, "grampo_intermediario": 2, "fixacao": 2}
    assert calculo.quantidades_estrutura([5, 5], "ceramica", pecas) == {
        "trilho": 10,                 # 1 por módulo
        "grampo_final": 2,            # 1 pacote de 4 por fileira
        "grampo_intermediario": 8,    # 2 × (5 − 1) por fileira, pacotes de 2
        "aterramento": 2,             # 1 por fileira
        "fixacao": 12,                # 2 × (5 + 1) por fileira, pacotes de 2
    }


def test_quantidades_da_estrutura_metalica_e_solo():
    pecas = {"grampo_final": 4, "grampo_intermediario": 2, "mini_trilho": 2}
    metalica = calculo.quantidades_estrutura([6], "metalica", pecas)
    assert metalica == {"grampo_final": 1, "grampo_intermediario": 5, "aterramento": 1, "mini_trilho": 7}
    assert "trilho" not in calculo.quantidades_estrutura([6], "solo", pecas)
    # Uma fileira de 1 módulo não tem grampo intermediário.
    assert "grampo_intermediario" not in calculo.quantidades_estrutura([1], "ceramica", pecas)


def test_quantidades_eletricas():
    assert calculo.quantidades_eletricas(2, 15, 2, 2) == {"conector": 2, "cabo_vermelho": 30, "cabo_preto": 30}
    assert calculo.quantidades_eletricas(3, 0, 2, 2) == {"conector": 3}  # microinversor: sem cabo solar


def test_custo_do_kit_com_frete():
    assert calculo.custo_do_kit([(2, 100.0), (1, 50.0)], 0.07) == pytest.approx(267.5)


# ---------- Montagem pelo catálogo ----------

def test_kit_completo_pelo_catalogo(base):
    _, proposta, resposta = _rascunho(base)
    assert resposta.status_code == 302
    m = montar(proposta)
    config = ConfigEmpresa.obter()
    assert m.modulo.codigo == "MFMA-1.3-MO-66-425W"  # menor R$/Wp do catálogo (0,750)
    assert not m.micro and m.inversor.tipo == "inversor"
    assert {linha.funcao for linha in m.kit} >= {
        "modulo", "inversor", "trilho", "fixacao", "grampo_final", "grampo_intermediario", "aterramento",
        "cabo_vermelho", "cabo_preto", "conector"}
    assert _linha(m, "trilho").quantidade == m.qtd_modulos
    assert _linha(m, "trilho").equipamento.codigo == "PERFIL2.36AL"
    assert _linha(m, "fixacao").equipamento.tipo_estrutura == "ceramica"
    assert _linha(m, "grampo_final").equipamento.espessura_mm == 35  # moldura padrão sem cadastro
    assert _linha(m, "grampo_final").quantidade == len(m.fileiras)
    assert _linha(m, "cabo_preto").quantidade == 15 * m.strings
    assert _linha(m, "conector").quantidade == m.strings  # 2 pares por string, embalagem de 2 pares
    assert sum(m.fileiras) == m.qtd_modulos
    assert m.produtos_kit == pytest.approx(sum(linha.subtotal for linha in m.kit))
    assert m.custo_kit == pytest.approx(m.produtos_kit * (1 + float(config.frete_kit)))
    assert not [a for a in m.alertas if a["tipo"] == "erro"]
    # O kit gravado tem preço por item e vai para o PDF (A21).
    assert proposta.itens_kit.count() == len(m.kit)
    assert proposta.itens_kit.get(funcao="trilho").preco_unitario == Decimal("63.25")


def test_microinversor_troca_cabos_por_suporte(base):
    _, proposta, _ = _rascunho(base, passo3={"tipo_inversor": "microinversor"})
    m = montar(proposta)
    assert m.micro and m.inversor.tipo == "microinversor"
    assert m.strings == m.qtd_inversores
    assert _linha(m, "suporte_micro").quantidade == m.qtd_inversores
    assert _linha(m, "cabo_preto") is None
    assert _linha(m, "conector").quantidade == m.qtd_inversores


def test_inversor_string_com_a_chave_em_micro_e_ignorado(base):
    string = Equipamento.objects.get(codigo="INVDE-MO-220V-3KW")
    _, proposta, _ = _rascunho(base, passo3={"tipo_inversor": "microinversor", "inversor": string.pk})
    m = montar(proposta)
    assert m.inversor.tipo == "microinversor"
    assert any("não é micro" in a["texto"] for a in m.alertas)


def test_vendedor_troca_item_muda_quantidade_e_acrescenta(base):
    navegador, proposta, _ = _rascunho(base)
    gancho_aluminio = Equipamento.objects.get(codigo="GANCHOAJ2PROL2A")
    junção = Equipamento.objects.get(codigo="JUNPERF1A")
    _passo3(navegador, proposta, kit_fixacao_equipamento=gancho_aluminio.pk, kit_trilho_qtd="3",
            kit_aterramento_qtd="0", extra_0_equipamento=junção.pk, extra_0_qtd="4")
    proposta.refresh_from_db()
    m = montar(proposta)
    assert _linha(m, "fixacao").equipamento == gancho_aluminio and _linha(m, "fixacao").alterada
    assert _linha(m, "trilho").quantidade == 3 and _linha(m, "trilho").sugerida == m.qtd_modulos
    assert _linha(m, "aterramento") is None  # quantidade 0 tira do kit
    extra = _linha(m, "extra")
    assert (extra.equipamento, extra.quantidade) == (junção, 4)
    assert m.produtos_kit == pytest.approx(sum(linha.subtotal for linha in m.kit))


def test_item_a_mais_sem_quantidade_pede_a_quantidade(base):
    navegador, proposta, _ = _rascunho(base)
    junção = Equipamento.objects.get(codigo="JUNPERF1A")
    resposta = _passo3(navegador, proposta, extra_0_equipamento=junção.pk)
    assert resposta.status_code == 200
    assert "Informe a quantidade" in resposta.content.decode()


def test_fileiras_do_vendedor(base):
    navegador, proposta, _ = _rascunho(base)
    qtd = montar(proposta).qtd_modulos
    _passo3(navegador, proposta, fileiras=f"{qtd - 1} + 1")
    proposta.refresh_from_db()
    assert proposta.fileiras == f"{qtd - 1}+1"
    m = montar(proposta)
    assert m.fileiras == [qtd - 1, 1] and not m.fileiras_sugeridas
    assert _linha(m, "grampo_final").quantidade == 2


def test_fileiras_que_nao_somam_bloqueiam_a_emissao(base):
    navegador, proposta, _ = _rascunho(base, passo3={"fileiras": "2+2"})
    m = montar(proposta)
    assert any("As fileiras" in motivo for motivo in impedimentos_de_emissao(m))


@pytest.mark.parametrize("texto", ["seis", "6+0", "6-5"])
def test_fileiras_malformadas(base, texto):
    _, _, resposta = _rascunho(base, passo3={"fileiras": texto})
    assert resposta.status_code == 200
    assert "separados por +" in resposta.content.decode()


def test_item_sem_preco_impede_o_calculo(base):
    Equipamento.objects.filter(codigo="PERFIL2.36AL").update(preco_referencia=None)
    _, proposta, _ = _rascunho(base)
    m = montar(proposta)
    assert m.custo_kit is None and "Sem preço no catálogo" in m.mensagem


def test_preco_velho_do_catalogo_avisa(base):
    importar_catalogo(date.today() - timedelta(days=31))
    _, proposta, _ = _rascunho(base)
    assert any("Reimporte o catálogo" in a["texto"] for a in montar(proposta).alertas)


def test_emissao_congela_o_kit(base):
    navegador, proposta, _ = _rascunho(base)
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    proposta.refresh_from_db()
    assert proposta.status == "emitida"
    antes = [(linha.funcao, linha.equipamento.pk, linha.quantidade) for linha in montar(proposta).kit]
    assert proposta.ajustes_kit["trilho"]["quantidade"] == proposta.qtd_modulos
    # O catálogo muda depois: um grampo final mais barato não troca o item da emitida.
    Equipamento.objects.filter(codigo="GRFN304A").update(preco_referencia=Decimal("0.10"), espessura_mm=35)
    depois = [(linha.funcao, linha.equipamento.pk, linha.quantidade) for linha in montar(proposta).kit]
    assert depois == antes
    assert proposta.registro["saidas"]["kit"][0]["funcao"] == "modulo"


def test_pdf_lista_o_kit_montado(base, monkeypatch):
    navegador, proposta, _ = _rascunho(base)
    html_recebido = {}

    def falso(html):
        html_recebido["html"] = html
        return b"%PDF-1.4 falso"

    monkeypatch.setattr(documento, "html_para_pdf", falso)
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    navegador.get(reverse("propostas:pdf", args=[proposta.pk]))
    assert "Perfil Fixacao Modulo" in html_recebido["html"]
    assert "30 m" in html_recebido["html"] or "15 m" in html_recebido["html"]  # cabo solar em metros


# ---------- Cotação vinculada substitui o catálogo (D35) ----------

def test_cotacao_com_itens_substitui_o_catalogo(base):
    navegador, proposta, _ = _rascunho(base)
    m = montar(proposta)
    modulo = Equipamento.objects.get(codigo="MFTF-0.4-BF-132-610W")
    inversor = Equipamento.objects.get(codigo="INVDE-MO-220V-3KW")
    cotacao = Cotacao.objects.create(distribuidor="Belenus", numero="WEB-1", data=date.today(), kwp=Decimal("3.050"),
                                     total_produtos=Decimal("6000"), frete=Decimal("400"), total=Decimal("6400"))
    ItemCotado.objects.create(cotacao=cotacao, equipamento=modulo, codigo=modulo.codigo, descricao="Módulo 610 W",
                              quantidade=5)
    ItemCotado.objects.create(cotacao=cotacao, equipamento=inversor, codigo=inversor.codigo,
                              descricao="Inversor 3 kW", quantidade=1)
    ItemCotado.objects.create(cotacao=cotacao, descricao="Estrutura cerâmica 5 módulos", quantidade=1)
    _passo3(navegador, proposta, cotacao=cotacao.pk)
    proposta.refresh_from_db()
    m = montar(proposta)
    assert m.kit_da_cotacao and m.custo_kit == 6400
    assert (m.modulo, m.qtd_modulos, m.inversor) == (modulo, 5, inversor)
    assert [linha.descricao for linha in m.kit] == ["Módulo 610 W", "Inversor 3 kW", "Estrutura cerâmica 5 módulos"]
    assert m.produtos_kit is None
