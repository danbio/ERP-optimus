"""Fatia v2.5: nova proposta em 4 passos, com os 3 cenários da auditoria (R$ 500, 800 kWh e fatura)."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as Navegador
from django.urls import reverse

from clientes.models import Cliente
from core.models import ConfigEmpresa, Municipio
from propostas.models import ItemKit, Proposta, TarifaVigente
from propostas.montagem import montar


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
    assert proposta.numero is None  # o número sai na primeira emissão (A13)

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
    Cliente.objects.create(nome="Maria  SOUZA", telefone="63999991234")
    _passo1(Navegador(), base)  # mesmo nome, com outra grafia: usa a ficha sem perguntar
    assert Cliente.objects.count() == 1
    assert Proposta.objects.get().cliente.nome == "Maria  SOUZA"


def test_telefone_de_outro_nome_pergunta_e_nao_sobrescreve(base):
    """A04: a ficha de outra pessoa com o mesmo telefone não pode ser renomeada."""
    existente = Cliente.objects.create(nome="Maria da Silva", telefone="63999991234", municipio=base["gurupi"])
    navegador = Navegador()
    resposta = _passo1(navegador, base, nome="João Souza")
    assert resposta.status_code == 200
    assert "Já existe Maria da Silva, de Gurupi, com este telefone" in resposta.content.decode()
    assert not Proposta.objects.exists()

    _passo1(navegador, base, nome="João Souza", mesma_pessoa="nao")
    existente.refresh_from_db()
    assert existente.nome == "Maria da Silva"
    assert Proposta.objects.get().cliente.nome == "João Souza"


def test_mesma_pessoa_usa_a_ficha_sem_trocar_o_nome(base):
    existente = Cliente.objects.create(nome="Maria da Silva", telefone="63999991234")
    _passo1(Navegador(), base, nome="Maria S.", mesma_pessoa="sim")
    existente.refresh_from_db()
    assert existente.nome == "Maria da Silva" and existente.municipio == base["gurupi"]
    assert Proposta.objects.get().cliente == existente


def test_passo1_nao_renomeia_cliente_com_outras_propostas(base):
    navegador, proposta = _ate_passo2(base)
    _passo1(Navegador(), base, mesma_pessoa="sim")  # segunda proposta para a mesma Maria
    resposta = navegador.post(reverse("propostas:passo", args=[proposta.pk, 1]), {
        "nome": "Outro Nome", "telefone": "(63) 99999-1234", "municipio": base["gurupi"].pk, "cpf_cnpj": "",
        "ligacao": "mono", "tipo_tarifa": base["b1"].pk,
    })
    assert resposta.status_code == 200
    assert "Corrija nome e telefone na ficha do cliente" in resposta.content.decode()
    assert Cliente.objects.get().nome == "Maria Souza"


def test_municipio_fica_na_proposta(base):
    navegador, proposta = _ate_passo2(base)
    palmas = Municipio.objects.get(codigo_ibge=1721000)
    navegador.post(reverse("propostas:passo", args=[proposta.pk, 1]), {
        "nome": "Maria Souza", "telefone": "(63) 99999-1234", "municipio": palmas.pk, "cpf_cnpj": "",
        "ligacao": "mono", "tipo_tarifa": base["b1"].pk,
    })
    proposta.refresh_from_db()
    assert proposta.municipio == palmas
    assert proposta.cliente.municipio == base["gurupi"]  # a ficha do cliente não muda


def test_ligacao_e_tarifa_comecam_sem_escolha(base):
    html = Navegador().get(reverse("propostas:nova")).content.decode()
    assert '<option value="" selected>Escolha a ligação</option>' in html
    assert '<option value="" selected>Escolha o tipo</option>' in html


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
    _passo3(navegador, proposta, qtd_modulos="15", custo_kit="15.000,00", mao_de_obra="5.000,00", desconto_texto="300")
    proposta.refresh_from_db()
    m = montar(proposta)
    assert m.qtd_modulos == 15 and m.qtd_modulos_sugerida != 15
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

def test_lista_busca_por_telefone(base):
    navegador = Navegador()
    _passo1(navegador, base)
    html = navegador.get(reverse("propostas:lista"), {"busca": "99999-1234"}).content.decode()
    assert "Maria Souza" in html


# ---------- Correções da revisão do PR #7

def _ate_passo2(base, **mudancas):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.latest("pk")
    _passo2(navegador, proposta, base, **mudancas)
    proposta.refresh_from_db()
    return navegador, proposta

def test_campos_da_aba_nao_escolhida_sao_ignorados(base):
    _, proposta = _ate_passo2(base, origem_consumo="kwh", kwh_informado="800", conta_informada="abc",
                              fatura_kwh="xyz")
    assert proposta.passo_atual == 3
    assert proposta.kwh_informado == 800 and proposta.conta_informada is None


@pytest.mark.parametrize("mudancas", [
    {"conta_informada": "0,00", "iluminacao_publica": ""},
    {"conta_informada": "-500,00", "iluminacao_publica": ""},
    {"iluminacao_publica": "-30,00"},
])
def test_passo2_recusa_conta_ou_iluminacao_invalidas(base, mudancas):
    _, proposta = _ate_passo2(base, **mudancas)
    assert proposta.passo_atual == 2


@pytest.mark.parametrize("mudancas", [
    {"custo_kit": "-10.000,00"}, {"mao_de_obra": "-1,00"}, {"desconto_texto": "-300"}, {"desconto_texto": "120%"},
    {"mao_de_obra": "4.500,00", "desconto_texto": "5.000,00"},
    {"desconto_texto": "999.999,00"},  # maior que a mão de obra sugerida
])
def test_passo3_recusa_valores_negativos_e_desconto_acima_da_mao_de_obra(base, mudancas):
    navegador, proposta = _ate_passo2(base)
    assert _passo3(navegador, proposta, **mudancas).status_code == 200
    proposta.refresh_from_db()
    assert proposta.passo_atual == 3


def test_telefone_de_outro_cpf_nao_sobrescreve_o_cadastro(base):
    Cliente.objects.create(nome="João", telefone="63999991234", cpf_cnpj="52998224725")
    resposta = _passo1(Navegador(), base, cpf_cnpj="111.444.777-35")
    assert resposta.status_code == 200
    assert "Este telefone já é de João" in resposta.content.decode()
    assert Cliente.objects.get().cpf_cnpj == "52998224725"
    assert not Proposta.objects.exists()


def test_previa_do_passo1_nao_quebra(base):
    navegador, proposta = _ate_passo2(base)
    resposta = navegador.post(reverse("propostas:previa", args=[proposta.pk, 1]), {
        "nome": "Maria", "telefone": "(63) 99999-1234", "municipio": base["gurupi"].pk, "cpf_cnpj": "",
        "ligacao": "mono", "tipo_tarifa": base["b1"].pk,
    })
    assert resposta.status_code == 200


def test_municipio_corrigido_no_passo1_vale_para_a_uc(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base, origem_consumo="fatura", conta_informada="", numero_uc="123456",
            endereco="Rua 1", competencia="2026-09-01", fatura_kwh="620", dias_ciclo="31", valor_fatura="845,30",
            cpf_cnpj="529.982.247-25")
    palmas = Municipio.objects.get(codigo_ibge=1721000)
    navegador.post(reverse("propostas:passo", args=[proposta.pk, 1]), {
        "nome": "Maria Souza", "telefone": "(63) 99999-1234", "municipio": palmas.pk, "cpf_cnpj": "529.982.247-25",
        "ligacao": "mono", "tipo_tarifa": base["b1"].pk,
    })
    proposta.refresh_from_db()
    assert proposta.uc.municipio == palmas
    _passo2(navegador, proposta, base)  # volta para valor da conta: deixa de ter UC e fatura
    proposta.refresh_from_db()
    assert proposta.uc is None and proposta.fatura is None and proposta.nivel == "estimativa"


def test_conta_de_hoje_e_o_valor_informado(base):
    navegador, proposta = _ate_passo2(base)
    _passo3(navegador, proposta)
    proposta.refresh_from_db()
    assert montar(proposta).conta_hoje == pytest.approx(500.0)


# ---------- Fatia v2.6: PDF da v2 (D30)

def _proposta_completa(base, **passo2):
    navegador, proposta = _ate_passo2(base, **passo2)
    _passo3(navegador, proposta)
    proposta.refresh_from_db()
    return navegador, proposta


def test_preview_da_estimativa_tem_aviso_e_financiamento(base):
    navegador, proposta = _proposta_completa(base)
    html = navegador.get(reverse("propostas:preview", args=[proposta.pk])).content.decode()
    aviso = ConfigEmpresa.obter().aviso_estimativa
    assert html.count("faixa-estimativa") == 2 and aviso in html
    assert "Consumo considerado" in html and "Análise da fatura" not in html
    assert "Financiamento" in html and "60×" in html and "12×" in html
    assert "por Wp" not in html  # R$/Wp é interno
    assert "Anexo I" not in html
    m = montar(proposta)
    assert f"R$ {m.parcela['parcela']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") in html


def test_preview_da_confirmada_usa_a_fatura(base):
    navegador, proposta = _proposta_completa(
        base, origem_consumo="fatura", conta_informada="", numero_uc="123456", endereco="Rua 1, Centro",
        competencia="2026-09-01", fatura_kwh="620", dias_ciclo="31", valor_fatura="845,30", cpf_cnpj="529.982.247-25")
    html = navegador.get(reverse("propostas:preview", args=[proposta.pk])).content.decode()
    assert "faixa-estimativa" not in html
    assert "Análise da fatura de referência" in html and "UC 123456" in html


def test_preview_de_rascunho_incompleto_diz_o_que_falta(base):
    navegador, proposta = _ate_passo2(base)
    TarifaVigente.objects.update(fiob_kwh=None)
    resposta = navegador.get(reverse("propostas:preview", args=[proposta.pk]))
    assert resposta.status_code == 422
    assert "Configurações → Tarifas" in resposta.content.decode()


def test_passo4_pre_visualiza_e_emite_com_confirmacao(base):
    """A15/A09: no rascunho não há PDF; a pré-visualização tem a marca RASCUNHO."""
    navegador, proposta = _proposta_completa(base)
    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 4])).content.decode()
    assert reverse("propostas:pdf", args=[proposta.pk]) not in html
    assert "Pré-visualizar" in html and "Confirmo, emitir agora" in html
    previa = navegador.get(reverse("propostas:preview", args=[proposta.pk])).content.decode()
    assert "proposta-doc--rascunho" in previa
    assert navegador.get(reverse("propostas:pdf", args=[proposta.pk])).status_code == 409


def test_passo4_mostra_o_que_impede_emitir(base):
    navegador, proposta = _proposta_completa(base)
    _passo3(navegador, proposta, mao_de_obra="0,00")
    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 4])).content.decode()
    assert "Ainda não dá para emitir" in html and "mão de obra está zerada" in html
    assert "Confirmo, emitir agora" not in html


# ---------- Iluminação pública estimada pela lei municipal (D32) ----------

def test_iluminacao_em_branco_e_estimada_pela_tabela_de_gurupi(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base, iluminacao_publica="")
    proposta.refresh_from_db()
    assert proposta.iluminacao_publica is None
    m = montar(proposta)
    # Conta de R$ 500 com tarifa 1,3237: cerca de 359 kWh, faixa 351–400 = 6,40 UFIRG × 4,61 = R$ 29,50
    assert m.iluminacao_estimada
    assert m.iluminacao == pytest.approx(29.50, abs=0.01)
    assert m.consumo == pytest.approx((500 - 29.504) / m.tarifa_kwh)
    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 2])).content.decode()
    assert "Iluminação pública estimada pela lei de Gurupi" in html


def test_iluminacao_digitada_vale_mesmo_zero(base):
    navegador = Navegador()
    _passo1(navegador, base)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base, iluminacao_publica="0")
    proposta.refresh_from_db()
    m = montar(proposta)
    assert not m.iluminacao_estimada and m.iluminacao == 0
    assert m.consumo == pytest.approx(500 / m.tarifa_kwh)


def test_consumo_em_kwh_soma_iluminacao_da_tabela_na_conta_de_hoje(base):
    navegador = Navegador()
    _passo1(navegador, base, ligacao="tri")
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base, origem_consumo="kwh", kwh_informado="900", conta_informada="")
    _passo3(navegador, proposta)
    proposta.refresh_from_db()
    m = montar(proposta)
    assert m.iluminacao == pytest.approx(54.17, abs=0.01)  # 801–1.500 kWh = 11,75 UFIRG
    assert m.conta_hoje == pytest.approx(900 * m.tarifa_kwh + m.iluminacao)


def test_b2_rural_nao_estima_iluminacao(base):
    navegador = Navegador()
    _passo1(navegador, base, tipo_tarifa=TarifaVigente.objects.get(tipo="B2").pk)
    proposta = Proposta.objects.get()
    _passo2(navegador, proposta, base, iluminacao_publica="")
    proposta.refresh_from_db()
    m = montar(proposta)
    assert not m.iluminacao_estimada and m.iluminacao == 0
