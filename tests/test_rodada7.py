"""Rodada 7: validação e higienização de toda entrada (P1, D41), travas de Configurações (A22) e modo cliente (A29)."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.forms import BandeiraForm, EmpresaForm, PerfisFormSet, TAMANHO_TEXTO
from core.validacoes import ARQUIVO_IMAGEM, ARQUIVO_PDF, conferir_arquivo, limpar_linhas, limpar_texto

from .test_proposta_v2 import _ate_passo2, _passo3

# ---------- Funções puras


def test_limpar_texto_e_linhas():
    assert limpar_texto("  Optimus   Energia  ", 50) == "Optimus Energia"
    assert limpar_linhas("  Item 1  \n\n\n  Item 2\n  ", 50) == "Item 1\n\nItem 2"
    with pytest.raises(ValueError, match="no máximo 5"):
        limpar_texto("123456", 5)


@pytest.mark.parametrize("nome, tamanho, tipo", [
    ("logo.html", 10, ARQUIVO_IMAGEM),  # HTML servido pela mídia viraria página do ERP
    ("fatura.exe", 10, ARQUIVO_PDF),
    ("sem_extensao", 10, ARQUIVO_PDF),
    ("grande.pdf", 16 * 1024 * 1024, ARQUIVO_PDF),
])
def test_arquivo_recusado(nome, tamanho, tipo):
    with pytest.raises(ValueError):
        conferir_arquivo(nome, tamanho, tipo)


def test_arquivo_aceito():
    conferir_arquivo("Foto.JPG", 1000, ARQUIVO_IMAGEM)
    conferir_arquivo("datasheet.pdf", 1000, ARQUIVO_PDF)


# ---------- Configurações (H02, A22)

def _empresa(**mudancas):
    dados = {
        "razao_social": "Optimus Empreendimentos LTDA", "nome_fantasia": "Optimus", "cnpj": "43.324.626/0001-66",
        "endereco": "Rua 1", "telefone": "(63) 99841-6077", "email": "contato@optimus.com.br",
        "projetos_entregues": "800", "anos_atuacao": "5", "validade_padrao_dias": "15",
        "texto_sobre": "Sobre", "beneficios_padrao": "A\nB", "escopo_padrao": "C", "etapas_padrao": "Aceite | assinatura",
        "aviso_estimativa": "Valores estimados.",
    }
    return EmpresaForm(dados | mudancas)


def test_empresa_valida_grava_formatado(db):
    form = _empresa(cnpj="43324626000166", telefone="63998416077", razao_social="  Optimus   LTDA ")
    assert form.is_valid(), form.errors
    assert form.cleaned_data["cnpj"] == "43.324.626/0001-66"
    assert form.cleaned_data["telefone"] == "(63) 99841-6077"
    assert form.cleaned_data["razao_social"] == "Optimus LTDA"


@pytest.mark.parametrize("campo, valor", [
    ("cnpj", "43.324.626/0001-00"),  # dígito errado
    ("cnpj", "529.982.247-25"),  # CPF no lugar do CNPJ
    ("cnpj", "abc"),
    ("telefone", "9999"),
    ("email", "sem-arroba"),
    ("validade_padrao_dias", "0"),
    ("validade_padrao_dias", "365"),
    ("anos_atuacao", "500"),
    ("etapas_padrao", "Etapa sem barra"),
    ("texto_sobre", "x" * 1600),
    ("razao_social", "   "),
])
def test_empresa_recusa_dado_malformado(db, campo, valor):
    form = _empresa(**{campo: valor})
    assert not form.is_valid() and campo in form.errors


def test_logo_que_nao_e_imagem_e_recusado(db):
    arquivo = SimpleUploadedFile("logo.html", b"<script>alert(1)</script>", content_type="text/html")
    form = EmpresaForm(_empresa().data, {"logo": arquivo})
    assert not form.is_valid() and "logo" in form.errors


def test_perfis_exigem_pelo_menos_um_e_sem_repetir():
    def formset(*perfis):
        dados = {"perfil-TOTAL_FORMS": str(len(perfis)), "perfil-INITIAL_FORMS": "0"}
        for i, (nome, simult) in enumerate(perfis):
            dados |= {f"perfil-{i}-nome": nome, f"perfil-{i}-simultaneidade": simult}
        return PerfisFormSet(dados, prefix="perfil")
    assert not formset(("", "")).is_valid()
    assert not formset(("Residencial", "35"), ("residencial", "40")).is_valid()
    assert formset(("Residencial", "35"), ("", "")).is_valid()


def test_premissas_recusam_orientacao_abaixo_de_50(db):
    from .test_configuracoes import _post_premissas
    resposta = _post_premissas(orientacao_sul="30")
    assert "entre 50% e 100%" in resposta.content.decode()


@pytest.mark.parametrize("valor", ["-0,01", "5,00"])
def test_bandeira_fora_da_faixa(db, valor):
    assert not BandeiraForm({"adicional_kwh": valor, "vigencia": "2026-10-01"}).is_valid()


# ---------- Cadastros e catálogo

def test_cliente_com_observacao_enorme_e_recusado(db):
    from clientes.forms import ClienteForm
    form = ClienteForm({"nome": "Maria", "telefone": "(63) 99999-1234", "observacoes": "x" * (TAMANHO_TEXTO + 1)})
    assert not form.is_valid() and "observacoes" in form.errors


@pytest.mark.parametrize("numero", ["12", "UC-ABC"])
def test_uc_com_numero_malformado(db, numero):
    from clientes.forms import UnidadeConsumidoraForm
    form = UnidadeConsumidoraForm({"numero_uc": numero})
    form.is_valid()
    assert "numero_uc" in form.errors


@pytest.mark.parametrize("campo, valor", [("potencia_w", "5500000"), ("modulos_por_micro", "40"), ("mppts", "0")])
def test_equipamento_fora_da_faixa(db, campo, valor):
    from propostas.forms import EquipamentoForm
    dados = {"tipo": "microinversor", "distribuidor": "Belenus", "descricao": "Micro", "potencia_w": "2000",
             "modulos_por_micro": "4", "fase": "mono"} | {campo: valor}
    form = EquipamentoForm(dados)
    assert not form.is_valid() and campo in form.errors


def test_equipamento_com_datasheet_que_nao_e_pdf(db):
    from propostas.forms import EquipamentoForm
    dados = {"tipo": "outro", "distribuidor": "Belenus", "descricao": "Item"}
    form = EquipamentoForm(dados, {"datasheet": SimpleUploadedFile("ficha.docx", b"x")})
    assert not form.is_valid() and "datasheet" in form.errors


def test_cotacao_com_validade_antes_da_data(db):
    from propostas.forms import CotacaoForm
    form = CotacaoForm({"distribuidor": "Belenus", "data": "2026-10-20", "validade": "2026-10-10", "kwp": "5",
                        "total_produtos": "10.000,00"})
    assert not form.is_valid() and "validade" in form.errors


def test_orcamento_com_validade_absurda(db):
    from orcamentos.forms import OrcamentoDadosForm
    form = OrcamentoDadosForm({"validade_dias": "999"})
    form.is_valid()
    assert "validade_dias" in form.errors


def test_aceite_no_futuro_e_recusado():
    from datetime import date, timedelta

    from propostas.forms import AceiteForm
    assert not AceiteForm({"data_aceite": (date.today() + timedelta(days=3)).isoformat()}).is_valid()


def test_fatura_que_nao_e_pdf_nao_avanca(base):
    from .test_rodada6 import FATURA_SEM_CPF
    navegador, proposta = _ate_passo2(base)
    from .test_proposta_v2 import _passo2
    _passo2(navegador, proposta, base, **FATURA_SEM_CPF,
            arquivo_fatura=SimpleUploadedFile("fatura.html", b"<html>", content_type="text/html"))
    proposta.refresh_from_db()
    assert proposta.nivel == "estimativa"


# ---------- A29 · modo cliente

def _no_modo_cliente(base, custo="19.876,54"):
    navegador, proposta = _ate_passo2(base)
    _passo3(navegador, proposta, custo_kit=custo, mao_de_obra="6.123,45")
    navegador.post(reverse("propostas:modo_cliente"), {"voltar": "/"})
    return navegador, proposta


def test_modo_cliente_nao_envia_custo_nem_mao_de_obra(base):
    navegador, proposta = _no_modo_cliente(base)
    for n in (3, 4):
        html = navegador.get(reverse("propostas:passo", args=[proposta.pk, n])).content.decode()
        assert "19.876,54" not in html and "6.123,45" not in html and "R$ por Wp" not in html
        assert "Mão de obra" not in html
    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 3])).content.decode()
    assert "<fieldset disabled" in html


def test_modo_cliente_nao_grava_o_passo3(base):
    navegador, proposta = _no_modo_cliente(base)
    _passo3(navegador, proposta)  # sem custo e mão de obra
    proposta.refresh_from_db()
    assert proposta.custo_kit == Decimal("19876.54") and proposta.mao_de_obra == Decimal("6123.45")


def test_modo_cliente_volta_para_a_pagina_em_que_estava(base):
    navegador, proposta = _ate_passo2(base)
    pagina = reverse("propostas:passo", args=[proposta.pk, 2])
    html = navegador.get(pagina).content.decode()
    assert f'name="voltar" value="{pagina}"' in html
    resposta = navegador.post(reverse("propostas:modo_cliente"), {"voltar": pagina})
    assert resposta.url == pagina
