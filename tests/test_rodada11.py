"""Rodada 11: página do produto solar e campos por tipo (H08, D45)."""

from django.core.files.base import ContentFile
from django.test import Client as Navegador
from django.urls import reverse

from propostas.forms import EquipamentoForm
from propostas.models import Equipamento

from .test_login_registro import _vendedor


def _modulo(**extra):
    return Equipamento.objects.create(**{
        "tipo": "modulo", "distribuidor": "Belenus", "codigo": "M610", "fabricante": "Honor", "descricao": "Módulo 610 W",
        "potencia_w": 610, "comprimento_mm": 2382, "largura_mm": 1134, "espessura_mm": 30,
        "mppts": 4,  # valor de outro tipo, vindo de importação: não aparece na ficha
    } | extra)


def test_ficha_so_com_os_campos_do_tipo(db):
    ficha = dict(_modulo().ficha())
    assert ficha["potência (W)"] == 610 and ficha["espessura da moldura (mm)"] == 30
    assert "MPPT" not in ficha and "fase" not in ficha


def test_vendedor_ve_o_produto_sem_botao_de_editar(db):
    modulo = _modulo()
    vendedor = _vendedor()
    resposta = vendedor.get(reverse("propostas:solar_equipamento_ver", args=[modulo.pk]))
    html = resposta.content.decode()
    assert resposta.status_code == 200 and "Módulo 610 W" in html and "2382" in html
    assert "Sem foto cadastrada" in html and "Sem datasheet cadastrado" in html  # espaços reservados
    assert reverse("propostas:solar_equipamento", args=[modulo.pk]) not in html
    assert vendedor.get(reverse("propostas:solar_equipamento", args=[modulo.pk])).status_code == 403


def test_lista_leva_a_pagina_do_produto_e_vendedor_nao_ve_incluir(db):
    modulo = _modulo()
    html = _vendedor().get(reverse("propostas:solar_equipamentos")).content.decode()
    assert reverse("propostas:solar_equipamento_ver", args=[modulo.pk]) in html
    assert "+ equipamento" not in html


def test_gestor_ve_editar_e_o_datasheet_na_pagina(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    modulo = _modulo()
    modulo.datasheet.save("ficha.pdf", ContentFile(b"%PDF-1.4"), save=True)
    navegador = Navegador()
    html = navegador.get(reverse("propostas:solar_equipamento_ver", args=[modulo.pk])).content.decode()
    assert "<iframe" in html and "Abrir o datasheet" in html
    assert reverse("propostas:solar_equipamento", args=[modulo.pk]) in html
    resposta = navegador.get(modulo.datasheet.url)
    assert resposta["X-Frame-Options"] == "SAMEORIGIN"


def test_edicao_marca_cada_campo_com_os_tipos_que_o_usam():
    form = EquipamentoForm()
    assert form.fields["mppts"].widget.attrs["data-tipos"] == "inversor"
    assert form.fields["espessura_mm"].widget.attrs["data-tipos"] == "modulo estrutura"
    assert "data-tipos" not in form.fields["descricao"].widget.attrs


def test_salvar_volta_para_a_pagina_do_produto(db):
    resposta = Navegador().post(reverse("propostas:solar_equipamento_novo"), {
        "tipo": "outro", "distribuidor": "Belenus", "codigo": "X1", "descricao": "Caixa de passagem",
        "pecas_por_embalagem": "1", "ativo": "on"})
    assert resposta.url == reverse("propostas:solar_equipamento_ver", args=[Equipamento.objects.get(codigo="X1").pk])
