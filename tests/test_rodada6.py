"""Rodada 6 do plano de correções: bloqueio e erros rápidos do teste humano de 24/10/2026 (H01–H17)."""

import pytest
from django.urls import reverse

from core import ia
from core.validacoes import limpar_cpf_cnpj
from propostas.models import Proposta

from .test_leitura_ia import FATURA_LIDA, _pdf
from .test_proposta_v2 import _ate_passo2, _passo2, _passo3

FATURA_SEM_CPF = {
    "origem_consumo": "fatura", "conta_informada": "", "numero_uc": "123456", "endereco": "Rua 1, Centro",
    "competencia": "2026-09-01", "fatura_kwh": "620", "dias_ciclo": "31", "valor_fatura": "845,30", "cpf_cnpj": "",
}


# ---------- H13 · CPF/CNPJ só na emissão (D38)

def test_fatura_sem_cpf_avanca_e_a_emissao_pede_o_cpf(base):
    navegador, proposta = _ate_passo2(base, **FATURA_SEM_CPF)
    assert proposta.passo_atual == 3 and proposta.nivel == "confirmada"
    assert proposta.cliente.cpf_cnpj == ""
    _passo3(navegador, proposta)

    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 4])).content.decode()
    assert "Falta o CPF ou CNPJ do titular" in html
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    proposta.refresh_from_db()
    assert proposta.status == Proposta.Status.RASCUNHO

    _passo2(navegador, proposta, base, **(FATURA_SEM_CPF | {"cpf_cnpj": "529.982.247-25"}))
    _passo3(navegador, proposta)
    navegador.post(reverse("propostas:emitir", args=[proposta.pk]))
    proposta.refresh_from_db()
    assert proposta.status == Proposta.Status.EMITIDA and proposta.cliente.cpf_cnpj == "52998224725"


def test_fatura_sem_cpf_nao_confunde_com_outro_cliente_sem_cpf(base):
    """CPF vazio não pode achar "dono" entre os clientes que também não têm CPF."""
    from clientes.models import Cliente
    Cliente.objects.create(nome="Outro", telefone="63988887777")
    _, proposta = _ate_passo2(base, **FATURA_SEM_CPF)
    assert proposta.passo_atual == 3


def test_estimativa_continua_sem_cpf(base):
    navegador, proposta = _ate_passo2(base)
    _passo3(navegador, proposta)
    html = navegador.get(reverse("propostas:passo", args=[proposta.pk, 4])).content.decode()
    assert "Falta o CPF" not in html


def test_cpf_com_asterisco_explica_que_a_fatura_esconde():
    with pytest.raises(ValueError, match="esconde parte do número"):
        limpar_cpf_cnpj("***.982.247-**")


# ---------- H14 · CPF mascarado na leitura da fatura

def test_leitura_com_cpf_mascarado_avisa_para_pedir_ao_cliente(base, monkeypatch):
    lida = FATURA_LIDA | {"cpf_cnpj": "***.982.247-**"}
    monkeypatch.setattr(ia, "ler_pdf", lambda conteudo, instrucao, esquema: lida)
    navegador, proposta = _ate_passo2(base)
    html = navegador.post(reverse("propostas:ler_fatura", args=[proposta.pk]),
                          {"arquivo_fatura": _pdf(), "cpf_cnpj": ""}).content.decode()
    assert "não traz o CPF ou CNPJ completo" in html
    assert "A IA não achou: CPF" not in html


def test_leitura_nao_avisa_cpf_quando_o_vendedor_ja_digitou(base, monkeypatch):
    lida = FATURA_LIDA | {"cpf_cnpj": "***.982.247-**"}
    monkeypatch.setattr(ia, "ler_pdf", lambda conteudo, instrucao, esquema: lida)
    navegador, proposta = _ate_passo2(base)
    html = navegador.post(reverse("propostas:ler_fatura", args=[proposta.pk]),
                          {"arquivo_fatura": _pdf(), "cpf_cnpj": "529.982.247-25"}).content.decode()
    assert "não traz o CPF" not in html


# ---------- H01 · estáticos com DEBUG=0 (CSS do admin)

@pytest.mark.parametrize("caminho", ["admin/css/base.css", "css/tokens.css"])
def test_rota_de_estaticos_acha_o_css_do_admin_e_o_do_projeto(rf, caminho):
    from config.urls import arquivo_estatico
    resposta = arquivo_estatico(rf.get(f"/static/{caminho}"), caminho)
    assert resposta.status_code == 200
    assert b"".join(resposta.streaming_content)


@pytest.mark.parametrize("caminho", ["nao/existe.css", "../config/settings.py"])
def test_rota_de_estaticos_nao_serve_o_que_nao_e_estatico(rf, caminho):
    from django.core.exceptions import SuspiciousFileOperation
    from django.http import Http404

    from config.urls import arquivo_estatico
    with pytest.raises((Http404, SuspiciousFileOperation)):
        arquivo_estatico(rf.get(f"/static/{caminho}"), caminho)


# ---------- H03 · logo com miniatura e "Remover logo"

def test_logo_atual_aparece_e_pode_ser_removido(db, settings, tmp_path):
    from django.core.files.base import ContentFile
    from django.forms.models import model_to_dict
    from django.test import Client as Navegador

    from core.forms import EmpresaForm
    from core.models import ConfigEmpresa

    settings.MEDIA_ROOT = tmp_path
    config = ConfigEmpresa.obter()
    config.razao_social, config.cnpj = "Optimus", "11222333000181"
    config.logo.save("logo.png", ContentFile(b"\x89PNG"), save=True)
    navegador = Navegador()
    html = navegador.get(reverse("core:config_empresa")).content.decode()
    assert 'class="miniatura"' in html and "Remover logo" in html and 'name="logo-clear"' in html
    assert "Limpar" not in html  # a caixa solta que o Django gerava

    dados = {campo: valor for campo, valor in model_to_dict(config, fields=EmpresaForm.Meta.fields).items()
             if campo != "logo"}
    navegador.post(reverse("core:config_empresa"), dados | {"logo-clear": "on"})
    config.refresh_from_db()
    assert not config.logo


# ---------- H17 · importação Intelbras lista novos e saídos

def test_importacao_lista_quais_sao_os_novos_e_os_que_sairam(db):
    from orcamentos.importacao import aplicar_importacao
    from orcamentos.models import TabelaPreco
    from orcamentos.services.tabela_intelbras import LeituraTabela

    from .test_orcamentos_fluxo import _produto

    tabela = TabelaPreco.objects.create(referencia="OUTUBRO/2026", arquivo="tabelas/x.xlsb", uf_destino="TO")
    resumo = aplicar_importacao(LeituraTabela("OUTUBRO", [_produto("1", "100", "130"), _produto("2", "50", "65")], {}),
                                tabela)
    assert [p["codigo"] for p in resumo["lista_novos"]] == ["1", "2"]
    resumo = aplicar_importacao(LeituraTabela("NOVEMBRO", [_produto("1", "100", "130")], {}), tabela)
    assert resumo["lista_novos"] == [] and resumo["lista_sairam"] == [{"codigo": "2", "produto": "Produto 2"}]


def test_tela_de_importacao_explica_novo_encerramento_e_inativo(db):
    from django.test import Client as Navegador
    html = Navegador().get(reverse("orcamentos:importar")).content.decode()
    assert "Em encerramento" in html and "Fica inativo" in html


# ---------- H11 · sem selo de múltiplos na busca (D39)

def test_busca_de_produtos_nao_mostra_multiplo():
    from pathlib import Path
    from django.conf import settings
    modelo = Path(settings.BASE_DIR, "orcamentos", "templates", "orcamentos", "_busca_produtos.html").read_text("utf-8")
    assert "múltiplo" not in modelo


# ---------- Tarifa vigente por distribuidora (preparo para H05)

def test_tarifa_de_outra_distribuidora_nao_substitui_a_vigente(base):
    from datetime import date
    from decimal import Decimal

    from propostas.models import TarifaVigente
    TarifaVigente.objects.create(distribuidora="Equatorial Goiás", tipo="B1", vigencia_inicio=date(2030, 1, 1),
                                 tusd=Decimal("0.5"), te=Decimal("0.3"), atualizado_em=date(2030, 1, 1))
    b1 = [t for t in TarifaVigente.vigentes() if t.tipo == "B1"]
    assert {t.distribuidora for t in b1} == {"Energisa TO", "Equatorial Goiás"}


# ---------- H06/H07/P2 · busca e filtros sem botão (D40)

@pytest.mark.parametrize("rota", ["clientes:lista", "propostas:lista", "orcamentos:lista", "orcamentos:catalogo",
                                  "propostas:solar_equipamentos"])
def test_listas_filtram_na_hora_sem_botao(db, rota):
    from django.test import Client as Navegador
    html = Navegador().get(reverse(rota)).content.decode()
    assert 'hx-select="#resultado"' in html and 'id="resultado"' in html
    assert ">Filtrar<" not in html and ">Buscar<" not in html
