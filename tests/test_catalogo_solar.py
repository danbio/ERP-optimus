"""Fatia v2.4: catálogo solar, importação Belenus e memória de cotações (D18, D28)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import Client as Navegador
from django.urls import reverse

from propostas.models import Cotacao, Equipamento
from propostas.services.catalogo_belenus import fase_e_tensao, ler_catalogo_belenus, tipo_estrutura

CSV = (
    "﻿categoria;codigo;descricao;marca;potencia_w;preco;rs_wp;emb_venda;estoque;foto;link\n"
    "modulos;MFTF-0.4-BF-132-610W;Modulo Bifacial 132 Cel. N Type 610w Huansheng Solar;huansheng;610;517.89;0.849;1;SP;MFTF.jpg;x\n"
    "inversor-mono-220v;INVDE-MO-220V-10KW;Inversor De Corrente Monofasico 2mppt 220v 10kw Deye;deye;10000;1974.46;;1;SP;;x\n"
    "inversor-trifasico-380v;INVGR-TRI-380V-15KW;Inversor De Corrente TrifáSico 2mppt 380v 15kw Growatt;growatt sem fundo;15000;3500.00;;1;SP;;x\n"
    "microinversores-220v;MINVEN-220V-475W;Microinversor De Corrente Mono/Bif 220v 475w Enphase;enphase;475;900.00;;1;SP;;x\n"
    "estruturas;SUPL2A;Suporte Pe Em L Fibrocimento 2 Pecas Aluminio Belenergy;logo_belenergy;;14.22;;1;SP;;x\n"
    "mat-eletricos;CBSOLBE-4MM-PT;Cabo Solar 4mm 0.6/1kv Ac 1.8kv Dc Preto;sil;;6.07;;1;SP;;x\n"
    "mat-eletricos;MDRSG-TR-1;Medidor Energia Trifasico Sungrow;sungrow;;;;1;SP;;x\n"
    "modulos;;linha sem código;;;;;;;;\n"
)


def test_ler_catalogo_belenus():
    itens = {i["codigo"]: i for i in ler_catalogo_belenus(CSV)}
    assert len(itens) == 7
    assert (itens["MFTF-0.4-BF-132-610W"]["tipo"], itens["MFTF-0.4-BF-132-610W"]["potencia_w"]) == ("modulo", 610)
    assert itens["MFTF-0.4-BF-132-610W"]["preco_referencia"] == Decimal("517.89")
    assert (itens["INVDE-MO-220V-10KW"]["fase"], itens["INVDE-MO-220V-10KW"]["tensao"]) == ("mono", 220)
    assert (itens["INVGR-TRI-380V-15KW"]["fase"], itens["INVGR-TRI-380V-15KW"]["fabricante"]) == ("tri", "Growatt")
    assert itens["MINVEN-220V-475W"]["tipo"] == "microinversor"
    assert (itens["SUPL2A"]["tipo_estrutura"], itens["SUPL2A"]["fabricante"]) == ("fibrocimento", "Bel Energy")
    assert (itens["CBSOLBE-4MM-PT"]["tipo"], itens["CBSOLBE-4MM-PT"]["potencia_w"]) == ("cabo", None)
    assert (itens["MDRSG-TR-1"]["tipo"], itens["MDRSG-TR-1"]["preco_referencia"]) == ("outro", None)


@pytest.mark.parametrize("descricao, esperado", [
    ("Suporte Gancho Telha Colonial C/ Prolongador", "ceramica"),
    ("Mini Trilho Telha Metalica 260mm", "metalica"),
    ("Grampo Final 30 Mm Para Telha Zipada", "metalica"),
    ("Suporte Ajustavel P/ Laje 1 Peca", "laje"),
    ("Grampo Final 30mm Para Estrutura Solo", "solo"),
    ("Grampo Intermediario 2 Pecas", ""),
])
def test_tipo_estrutura(descricao, esperado):
    assert tipo_estrutura(descricao) == esperado


def test_fase_desconhecida():
    assert fase_e_tensao("Inversor Híbrido 5kw") == ("", None)


def test_carga_inicial_das_cotacoes(db):
    belenus, intelbras = (Cotacao.objects.get(distribuidor=d) for d in ("Belenus", "Intelbras"))
    assert belenus.rs_por_wp == pytest.approx(Decimal("2.1598"), abs=Decimal("0.0001"))
    assert intelbras.total == Decimal("34874.60")  # só o kit, sem a mão de obra
    assert belenus.itens.get(codigo="INVDE-MO-220V-10KW").equipamento.fase == "mono"
    assert [c.distribuidor for c in Cotacao.referencias()] == ["Belenus", "Intelbras"]


def test_importar_belenus_atualiza_sem_duplicar(db, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    (tmp_path / "fotos").mkdir()
    (tmp_path / "fotos" / "MFTF.jpg").write_bytes(b"\xff\xd8foto")
    (tmp_path / "datasheets").mkdir()
    (tmp_path / "datasheets" / "INVDE-MO-220V-10KW.pdf").write_bytes(b"%PDF-1.4")
    arquivo = tmp_path / "belenus-catalogo.csv"
    arquivo.write_text(CSV, encoding="utf-8")

    call_command("importar_belenus", str(arquivo), "--data", "2026-10-21")
    call_command("importar_belenus", str(arquivo), "--data", "2026-10-21")

    assert Equipamento.objects.filter(distribuidor="Belenus").count() == 7  # 2 da carga inicial + 5 novos
    modulo = Equipamento.objects.get(codigo="MFTF-0.4-BF-132-610W")
    assert modulo.preco_referencia == Decimal("517.89")
    assert modulo.preco_em == date(2026, 10, 21)
    assert modulo.foto.name.startswith("catalogo/fotos/")
    assert Equipamento.objects.get(codigo="INVDE-MO-220V-10KW").datasheet


def test_cotacao_velha_aparece_com_aviso(db):
    Cotacao.objects.update(data=date.today() - timedelta(days=20))
    html = Navegador().get(reverse("propostas:solar_cotacoes")).content.decode()
    assert "20 dias: preço velho" in html


def _post_cotacao(**mudancas):
    dados = {
        "distribuidor": "Aldo", "numero": "123", "data": "2026-10-21", "validade": "",
        "kwp": "5,49", "total_produtos": "11.000,00", "frete": "500", "total": "",
        "observacao": "",
        "item-TOTAL_FORMS": "3", "item-INITIAL_FORMS": "0", "item-MIN_NUM_FORMS": "0", "item-MAX_NUM_FORMS": "1000",
        "item-0-codigo": "MFTF-0.4-BF-132-610W", "item-0-descricao": "Módulo 610 W", "item-0-quantidade": "9",
        "item-0-unidade": "un",
        "item-1-codigo": "", "item-1-descricao": "Cabo solar 4 mm", "item-1-quantidade": "50,5", "item-1-unidade": "m",
        "item-2-codigo": "", "item-2-descricao": "", "item-2-quantidade": "", "item-2-unidade": "un",
    }
    return Navegador().post(reverse("propostas:solar_cotacao_nova"), dados | mudancas)


def test_cadastrar_cotacao_soma_frete(db):
    resposta = _post_cotacao()
    assert resposta.status_code == 302
    cotacao = Cotacao.objects.get(distribuidor="Aldo")
    assert cotacao.total == Decimal("11500.00")
    assert cotacao.rs_por_wp == pytest.approx(Decimal("2.0947"), abs=Decimal("0.0001"))
    assert cotacao.itens.count() == 2
    assert cotacao.itens.get(unidade="m").quantidade == Decimal("50.50")


def test_item_ligado_ao_catalogo_pelo_codigo(db):
    _post_cotacao(distribuidor="Belenus")
    cotacao = Cotacao.objects.get(numero="123")
    assert cotacao.itens.get(codigo="MFTF-0.4-BF-132-610W").equipamento.potencia_w == 610


@pytest.mark.parametrize("campo, valor", [("kwp", "0"), ("kwp", "abc"), ("total_produtos", "1,234.00"), ("item-0-quantidade", "x")])
def test_cotacao_recusa_dado_malformado(db, campo, valor):
    assert _post_cotacao(**{campo: valor}).status_code == 200
    assert not Cotacao.objects.filter(distribuidor="Aldo").exists()


def test_equipamento_exige_potencia_e_fase(db):
    resposta = Navegador().post(reverse("propostas:solar_equipamento_novo"), {
        "tipo": "inversor", "distribuidor": "Aldo", "codigo": "X1", "descricao": "Inversor 5 kW", "ativo": "on",
    })
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Informe a potência" in html and "Informe a fase" in html


def test_filtro_do_catalogo(db):
    navegador = Navegador()
    html = navegador.get(reverse("propostas:solar_equipamentos")).content.decode()
    assert "Huansheng" in html and "Inversor Intelbras" not in html  # padrão: módulos
    html = navegador.get(reverse("propostas:solar_equipamentos"), {"tipo": "inversor", "busca": "intelbras"}).content.decode()
    assert "Inversor Intelbras" in html and "Deye" not in html
