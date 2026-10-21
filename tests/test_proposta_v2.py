"""Fatia v2.5: nova proposta em 4 passos, com os 3 cenários da auditoria (R$ 500, 800 kWh e fatura)."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as Navegador
from django.urls import reverse

from clientes.models import Cliente
from core.models import ConfigEmpresa, Municipio
from propostas.models import Bandeira, ItemKit, Proposta, TarifaVigente, TaxaFinanciamento
from propostas.montagem import montar

from .test_fatia4_proposta_view import fatura_alesio, uc_alesio  # noqa: F401 (fixtures)
from .test_fatia5_pdf import proposta_alesio  # noqa: F401 (fixture)


@pytest.fixture
def base(db):
    """Tarifas com tributos e Fio B preenchidos pelo gestor e duas taxas de financiamento."""
    TarifaVigente.objects.update(aliquota_tributos=Decimal("0.25"), fiob_kwh=Decimal("0.30"))
    TaxaFinanciamento.objects.create(banco="BV", prazo_meses=60, taxa_mensal=Decimal("0.0159"), vigente_desde="2026-10-21")
    TaxaFinanciamento.objects.create(banco="BV", prazo_meses=12, taxa_mensal=Decimal("0.0139"), vigente_desde="2026-10-21")
    return {
        "b1": TarifaVigente.objects.get(tipo="B1"),
        "gurupi": Municipio.objects.get(codigo_ibge=1709500),
        "verde": Bandeira.objects.get(nome="Verde"),
        "perfil": ConfigEmpresa.obter().perfis_simultaneidade[0]["nome"],
    }


def _passo1(navegador, base, **mudancas):
    dados = {"nome": "Maria Souza", "telefone": "(63) 99999-1234", "municipio": base["gurupi"].pk,
             "cpf_cnpj": "", "ligacao": "mono", "tipo_tarifa": base["b1"].pk}
    return navegador.post(reverse("propostas:nova"), dados | mudancas)


def _passo2(navegador, proposta, base, **mudancas):
    dados = {"origem_consumo": "rs", "conta_informada": "500,00", "iluminacao_publica": "30,00",
             "bandeira": base["verde"].pk, "kwh_informado": "", "folga": "10", "perfil_simultaneidade": base["perfil"]}
    return navegador.post(reverse("propostas:passo", args=[proposta.pk, 2]), dados | mudancas)


def _passo3(navegador, proposta, **mudancas):
    dados = {"orientacao": "norte", "tipo_estrutura": "ceramica", "modulo": "", "qtd_modulos": "", "inversor": "",
             "qtd_inversores": "", "cabo_preto_m": "", "cabo_vermelho_m": "", "cotacao": "", "custo_kit": "",
             "mao_de_obra": "", "desconto_texto": ""}
    return navegador.post(reverse("propostas:passo", args=[proposta.pk, 3]), dados | mudancas)


def test_cenario_conta_de_500_reais(base):
    navegador = Navegador()
    resposta = _passo1(navegador, base)
    proposta = Proposta.objects.get()
    assert resposta.url == reverse("propostas:passo", args=[proposta.pk, 2])
    assert proposta.cliente.telefone == "63999991234"
    assert proposta.numero.startswith("OPT-")

    assert _passo2(navegador, proposta, base).status_code == 302
    assert _passo3(navegador, proposta).status_code == 302

    proposta.refresh_from_db()
    m = montar(proposta)
    # (500 − 30) / tarifa com tributos (0,99278 / 0,75 = 1,3237) ≈ 355 kWh/mês
    assert m.consumo == pytest.approx(355.07, abs=0.1)
    assert m.modulo.distribuidor == "Belenus"           # menor R$/Wp entre as cotações de 21/10
    assert m.inversor.fase == "mono"
    assert m.mao_de_obra == 4500                          # mínimo
    assert proposta.investimento == Decimal(f"{m.investimento:.2f}")
    assert proposta.nivel == "estimativa"
    assert proposta.itens_kit.filter(tipo=ItemKit.Tipo.MODULO).get().quantidade == m.qtd_modulos

    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 4])).content.decode()
    assert "Economia no 1º ano" in html
    assert "60×" in html and "12×" in html
    assert ConfigEmpresa.obter().aviso_estimativa[:30] in html


def test_cenario_800_kwh_trifasico(base):
    navegador = Navegador()
    _passo1(navegador, base, ligacao="tri")
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base, origem_consumo="kwh", kwh_informado="800", conta_informada="")
    _passo3(navegador, proposta, desconto_texto="5%", tipo_estrutura="solo")
    proposta.refresh_from_db()
    m = montar(proposta)
    assert m.consumo == 800
    assert m.inversor.fase == "tri"
    assert proposta.desconto_pct == Decimal("0.0500")
    assert m.desconto == pytest.approx(m.mao_de_obra * 0.05)
    assert m.mao_de_obra == pytest.approx(max(m.kwp * 700, 4500))  # solo


def test_cenario_com_fatura_vira_confirmada(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    resposta = _passo2(navegador, proposta, base, origem_consumo="fatura", conta_informada="", numero_uc="123456",
                       endereco="Rua 1, Centro", competencia="2026-09-01", fatura_kwh="620", dias_ciclo="31",
                       valor_fatura="845,30", cpf_cnpj="529.982.247-25",
                       arquivo_fatura=SimpleUploadedFile("fatura.pdf", b"%PDF-1.4", content_type="application/pdf"))
    assert resposta.status_code == 302
    proposta.refresh_from_db()
    assert proposta.nivel == "confirmada"
    assert proposta.uc.numero_uc == "123456" and proposta.uc.municipio == base["gurupi"]
    assert proposta.cliente.cpf_cnpj == "52998224725"
    assert montar(proposta).consumo == pytest.approx(620 / 31 * 30)


def test_cliente_existente_pelo_telefone_nao_duplica(base):
    Cliente.objects.create(nome="Maria", telefone="63999991234")
    _passo1(Navegador(), base)
    assert Cliente.objects.count() == 1
    assert Proposta.objects.get().cliente.nome == "Maria Souza"


@pytest.mark.parametrize("campo, valor", [("telefone", "9999"), ("cpf_cnpj", "123abc"), ("nome", "  ")])
def test_passo1_recusa_dado_malformado(base, campo, valor):
    assert _passo1(Navegador(), base, **{campo: valor}).status_code == 200
    assert not Proposta.objects.exists()


@pytest.mark.parametrize("mudancas", [
    {"conta_informada": ""},
    {"conta_informada": "abc"},
    {"iluminacao_publica": "600,00"},
    {"origem_consumo": "kwh", "kwh_informado": "0"},
    {"origem_consumo": "fatura", "conta_informada": ""},  # fatura sem os dados
    {"folga": "150"},
])
def test_passo2_recusa_dado_malformado(base, mudancas):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    assert _passo2(navegador, proposta, base, **mudancas).status_code == 200
    proposta.refresh_from_db()
    assert proposta.passo_atual == 2


@pytest.mark.parametrize("mudancas", [{"desconto_texto": "abc"}, {"qtd_modulos": "0"}, {"custo_kit": "1,234.00"}])
def test_passo3_recusa_dado_malformado(base, mudancas):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base)
    assert _passo3(navegador, proposta, **mudancas).status_code == 200


def test_quantidade_e_custo_editados_pelo_vendedor(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base)
    _passo3(navegador, proposta, qtd_modulos="12", custo_kit="15.000,00", mao_de_obra="5.000,00", desconto_texto="300")
    proposta.refresh_from_db()
    m = montar(proposta)
    assert m.qtd_modulos == 12 and m.qtd_modulos_sugerida != 12
    assert proposta.investimento == Decimal("19700.00")
    assert not m.custo_kit_estimado


def test_sem_tributos_avisa_onde_preencher(base):
    TarifaVigente.objects.update(aliquota_tributos=0)
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base, origem_consumo="kwh", kwh_informado="800")
    _passo3(navegador, proposta)
    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 4])).content.decode()
    assert "Configurações → Tarifas" in html
    assert "Economia no 1º ano" not in html


def test_previa_recalcula_sem_gravar(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base)
    resposta = navegador.post(reverse("propostas:previa", args=[proposta.pk, 2]), {
        "origem_consumo": "kwh", "kwh_informado": "1000", "folga": "0", "perfil_simultaneidade": base["perfil"],
        "bandeira": base["verde"].pk,
    })
    html = resposta.content.decode()
    assert 'hx-swap-oob' in html and "1000" in html
    proposta.refresh_from_db()
    assert proposta.origem_consumo == "rs"


def test_modo_cliente_esconde_o_interno(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base)
    _passo3(navegador, proposta)
    navegador.post(reverse("propostas:modo_cliente"), {"voltar": "/"})
    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 4])).content.decode()
    assert "assistente modo-cliente" in html


def test_escolher_prazo_para_comparar(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base)
    _passo3(navegador, proposta)
    navegador.post(reverse("propostas:passo", args=[proposta.pk, 4]), {"prazo": "12"})
    proposta.refresh_from_db()
    assert proposta.prazo_comparacao == 12
    assert montar(proposta).parcela["prazo"] == 12


def test_proposta_antiga_abre_no_formulario_antigo(proposta_alesio):
    navegador = Navegador()
    resposta = navegador.get(reverse("propostas:editar", args=[proposta_alesio.pk]))
    assert resposta.url == reverse("propostas:legado_editar", args=[proposta_alesio.pk])
    resposta = navegador.get(reverse("propostas:passo", args=[proposta_alesio.pk, 2]))
    assert resposta.url == reverse("propostas:legado_editar", args=[proposta_alesio.pk])


def test_lista_busca_por_telefone(base):
    navegador = Navegador()
    _passo1(navegador, base)
    html = navegador.get(reverse("propostas:lista"), {"busca": "99999-1234"}).content.decode()
    assert "Maria Souza" in html
