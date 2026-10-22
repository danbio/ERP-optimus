"""Fatia v2.2: tela de Configurações e leitura dos dados oficiais (ANEEL, NASA POWER, IBGE)."""

from datetime import date
from decimal import Decimal

import pytest
from django.test import Client as Navegador
from django.urls import reverse

from core import dados_oficiais
from core.models import ConfigEmpresa, Municipio
from propostas.models import Bandeira, TarifaVigente, TaxaFinanciamento


# ---------- Leitura dos dados oficiais (funções puras) ----------

def _tarifa(subgrupo, classe, subclasse, tusd, te, vigencia="2026-08-26", detalhe="Não se aplica",
            base="Tarifa de Aplicação", modalidade="Convencional"):
    """Registro no formato do datastore da ANEEL (valores em R$/MWh, vírgula decimal)."""
    return {
        "SigAgente": "ETO", "DscREH": "RESOLUÇÃO HOMOLOGATÓRIA Nº 3.323", "DatInicioVigencia": vigencia,
        "DscBaseTarifaria": base, "DscSubGrupo": subgrupo, "DscModalidadeTarifaria": modalidade,
        "DscClasse": classe, "DscSubClasse": subclasse, "DscDetalhe": detalhe,
        "DscUnidadeTerciaria": "MWh", "VlrTUSD": tusd, "VlrTE": te,
    }


def test_ler_tarifas_aneel_pega_a_linha_certa():
    registros = [
        _tarifa("B1", "Residencial", "Residencial", "683,27", "309,51"),
        _tarifa("B1", "Residencial", "Residencial", "600,00", "290,00", vigencia="2025-08-26"),
        _tarifa("B1", "Residencial", "Residencial", "100,00", "100,00", detalhe="SCEE"),
        _tarifa("B1", "Residencial", "Residencial", "1,00", "1,00", base="Base Econômica"),
        _tarifa("B1", "Residencial", "Residencial", "1,00", "1,00", modalidade="Branca"),
        _tarifa("B1", "Residencial", "Baixa Renda", "574,03", "309,64"),
        _tarifa("B2", "Rural", "Não se aplica", "683,27", "309,51"),
        _tarifa("B3", "Não se aplica", "Não se aplica", "683,27", "309,51"),
    ]
    lidas = dados_oficiais.ler_tarifas_aneel(registros)
    assert set(lidas) == {"B1", "B1_BAIXA_RENDA", "B2", "B3"}
    assert lidas["B1"]["vigencia"] == date(2026, 8, 26)
    assert lidas["B1"]["tusd"] == Decimal("0.683270")
    assert lidas["B1"]["te"] == Decimal("0.309510")
    assert lidas["B1_BAIXA_RENDA"]["tusd"] == Decimal("0.574030")


def test_ler_tarifas_aneel_sem_dados():
    assert dados_oficiais.ler_tarifas_aneel([]) == {}


def test_ler_bandeiras_aneel_fica_com_a_mais_recente():
    registros = [
        {"DatVigencia": "2024-04-01", "NomBandeiraAcionada": "Amarela", "VlrAdicionalBandeiraRSMWh": "18,85"},
        {"DatVigencia": "2022-07-01", "NomBandeiraAcionada": "Amarela", "VlrAdicionalBandeiraRSMWh": "29,89"},
        {"DatVigencia": "2024-04-01", "NomBandeiraAcionada": "Vermelha P2", "VlrAdicionalBandeiraRSMWh": "78,77"},
        {"DatVigencia": "2024-04-01", "NomBandeiraAcionada": "Escassez Hídrica", "VlrAdicionalBandeiraRSMWh": "142,00"},
    ]
    lidas = dados_oficiais.ler_bandeiras_aneel(registros)
    assert lidas == {
        "Amarela": (Decimal("0.01885"), date(2024, 4, 1)),
        "Vermelha patamar 2": (Decimal("0.07877"), date(2024, 4, 1)),
    }


def _nasa(valores):
    meses = dados_oficiais.MESES_NASA
    return {"properties": {"parameter": {"ALLSKY_SFC_SW_DWN": dict(zip(meses, valores)) | {"ANN": 5.5}}}}


def test_ler_irradiacao_nasa():
    gurupi = [5.3926, 5.3098, 5.1804, 5.2351, 5.209, 5.3249, 5.6206, 6.0691, 6.0869, 5.7209, 5.497, 5.4605]
    assert dados_oficiais.ler_irradiacao_nasa(_nasa(gurupi)) == [
        5.39, 5.31, 5.18, 5.24, 5.21, 5.32, 5.62, 6.07, 6.09, 5.72, 5.5, 5.46,
    ]


def test_ler_irradiacao_nasa_recusa_mes_sem_dado():
    with pytest.raises(ValueError):
        dados_oficiais.ler_irradiacao_nasa(_nasa([5.0] * 11 + [-999]))


def test_ler_municipios_csv_filtra_a_uf():
    texto = (
        "codigo_ibge,nome,latitude,longitude,capital,codigo_uf,siafi_id,ddd,fuso_horario\n"
        "1709500,Gurupi,-11.7279,-49.068,0,17,9419,63,America/Araguaina\n"
        "5208707,Goiânia,-16.6864,-49.2643,1,52,9373,62,America/Sao_Paulo\n"
    )
    assert dados_oficiais.ler_municipios_csv(texto, 17) == [
        {"codigo_ibge": 1709500, "nome": "Gurupi", "latitude": -11.7279, "longitude": -49.068},
    ]


def test_numero_aneel():
    assert dados_oficiais.numero_aneel("683,27") == Decimal("683.27")
    assert dados_oficiais.numero_aneel(",00") == Decimal("0.00")
    assert dados_oficiais.numero_aneel("1.234,5") == Decimal("1234.5")


# ---------- Gravação no banco, sem internet ----------

def test_carga_inicial_de_tarifas_e_bandeiras(db):
    b1 = TarifaVigente.objects.get(tipo="B1")
    assert (b1.tusd, b1.te) == (Decimal("0.683270"), Decimal("0.309510"))
    # Tributos e Fio B conferidos em faturas e na ANEEL (D32)
    assert (b1.aliquota_tributos, b1.fiob_kwh) == (Decimal("0.2740"), Decimal("0.441478"))
    assert round(b1.tarifa_com_tributos, 6) == Decimal("1.367466")
    assert not b1.fiob_desatualizado
    assert list(Bandeira.objects.values_list("nome", flat=True)) == [
        "Verde", "Amarela", "Vermelha patamar 1", "Vermelha patamar 2",
    ]


def test_tarifa_nova_herda_tributos_e_fio_b(db, monkeypatch):
    TarifaVigente.objects.filter(tipo="B1").update(aliquota_tributos=Decimal("0.25"), fiob_kwh=Decimal("0.3"))
    registros = [_tarifa("B1", "Residencial", "Residencial", "700,00", "320,00", vigencia="2027-08-26")]
    monkeypatch.setattr(dados_oficiais, "_registros_aneel_tarifas", lambda sub: registros if sub == "B1" else [])

    texto = dados_oficiais.atualizar_tarifas()

    nova = TarifaVigente.objects.get(tipo="B1", vigencia_inicio=date(2027, 8, 26))
    assert "B1 residencial" in texto
    assert (nova.aliquota_tributos, nova.fiob_kwh) == (Decimal("0.2500"), Decimal("0.300000"))
    assert nova.fiob_desatualizado  # o gestor precisa conferir o Fio B da vigência nova
    assert TarifaVigente.vigentes()[0].vigencia_inicio == date(2027, 8, 26)


def test_irradiacao_com_erro_mantem_o_dado_antigo(db, monkeypatch):
    gurupi = Municipio.objects.get(codigo_ibge=1709500)
    antes = list(gurupi.irradiacao)

    def falha(url):
        raise OSError("sem rede")

    monkeypatch.setattr(dados_oficiais, "baixar_json", falha)
    atualizados, erros = dados_oficiais.atualizar_irradiacao([gurupi])
    gurupi.refresh_from_db()
    assert (atualizados, gurupi.irradiacao) == (0, antes)
    assert "Gurupi" in erros[0]


def test_irradiacao_gravada_com_fonte(db, monkeypatch):
    gurupi = Municipio.objects.get(codigo_ibge=1709500)
    monkeypatch.setattr(dados_oficiais, "baixar_json", lambda url: _nasa([5.5] * 12))
    assert dados_oficiais.atualizar_irradiacao([gurupi]) == (1, [])
    gurupi.refresh_from_db()
    assert gurupi.irradiacao == [5.5] * 12
    assert gurupi.fonte_irradiacao.startswith("NASA POWER")
    assert gurupi.atualizado_em == date.today()


# ---------- Telas ----------

@pytest.mark.parametrize("rota", [
    "core:config_empresa", "core:config_premissas", "core:config_tarifas",
    "core:config_financiamento", "core:config_municipios",
])
def test_telas_abrem(db, rota):
    resposta = Navegador().get(reverse(rota))
    assert resposta.status_code == 200
    assert "Configurações" in resposta.content.decode()


def _post_premissas(**mudancas):
    dados = {
        "prazo_homologacao_dias": "60", "horizonte_anos": "25", "razao_cc_ca_max": "1,5",
        "sobrecarga_min": "0,8", "cobertura_min": "80", "cobertura_max": "130",
        "conta_alta": "5.000,00", "consumo_alto": "3000", "tolerancia_tarifa_fatura": "30",
        "tolerancia_kwp_cotacao": "5", "limite_microgeracao_kwp": "75",
        "mo_por_kwp": "550,00", "mo_por_kwp_solo": "700", "mo_minima": "4.500,00", "dias_preco_velho": "15",
        "distribuidor_kit": "Belenus", "frete_kit": "7", "dias_catalogo_velho": "30", "metros_cabo_por_string": "15",
        "pares_conector_por_string": "2", "modulos_por_string_min": "4", "modulos_por_string_max": "12",
        "espessura_modulo_padrao": "35",
        "perdas": "14", "perda_clipping": "1", "simultaneidade": "35", "reajuste_anual": "8",
        "degradacao_ano1": "2", "degradacao_anual": "0,55",
        "orientacao_norte": "100", "orientacao_nordeste_noroeste": "97", "orientacao_leste_oeste": "90",
        "orientacao_sul": "80",
        "perfil-TOTAL_FORMS": "2", "perfil-INITIAL_FORMS": "0", "perfil-MIN_NUM_FORMS": "0", "perfil-MAX_NUM_FORMS": "1000",
        "perfil-0-nome": "Residencial", "perfil-0-simultaneidade": "35",
        "perfil-1-nome": "", "perfil-1-simultaneidade": "",
    }
    return Navegador().post(reverse("core:config_premissas"), dados | mudancas)


def test_premissas_salvas_em_fracao(db):
    resposta = _post_premissas()
    assert resposta.status_code == 302
    config = ConfigEmpresa.obter()
    assert config.premissas_padrao["degradacao_anual"] == pytest.approx(0.0055)
    assert config.premissas_padrao["razao_cc_ca_max"] == 1.5
    assert config.fatores_orientacao["leste_oeste"] == pytest.approx(0.9)
    assert config.mo_por_kwp == Decimal("550.00")
    assert config.frete_kit == Decimal("0.07")
    assert config.mo_minima == Decimal("4500.00")
    assert config.perfis_simultaneidade == [{"nome": "Residencial", "simultaneidade": 0.35}]
    assert config.tolerancia_kwp_cotacao == Decimal("0.05") and config.prazo_homologacao_dias == 60
    assert config.premissas_padrao["cobertura_max"] == pytest.approx(1.30)
    assert config.premissas_padrao["sobrecarga_min"] == 0.8


@pytest.mark.parametrize("campo, valor", [
    ("perdas", "abc"), ("perdas", "150"), ("mo_minima", "4,500.00"), ("razao_cc_ca_max", "3"),
    ("perfil-1-nome", "Comércio"),  # perfil sem simultaneidade
])
def test_premissas_recusam_dado_malformado(db, campo, valor):
    antes = ConfigEmpresa.obter().premissas_padrao
    resposta = _post_premissas(**{campo: valor})
    assert resposta.status_code == 200
    assert ConfigEmpresa.obter().premissas_padrao == antes


def test_tela_de_premissas_mostra_valores_em_percentual(db):
    html = Navegador().get(reverse("core:config_premissas")).content.decode()
    assert 'value="97"' in html  # nordeste/noroeste 0,97
    assert 'value="4.500,00"' in html


def _post_taxas(dados):
    return Navegador().post(reverse("core:config_financiamento"), dados)


def test_taxas_incluir_alterar_e_remover(db):
    resposta = _post_taxas({"banco_0": "BV", "taxa_0_12": "1,59", "taxa_0_60": "1,89"})
    assert resposta.status_code == 302
    assert TaxaFinanciamento.objects.count() == 2
    assert TaxaFinanciamento.objects.get(banco="BV", prazo_meses=12).taxa_mensal == Decimal("0.015900")

    # Grade já tem a linha do BV (índice 0) e a vazia (índice 1).
    _post_taxas({"banco_0": "BV", "taxa_0_12": "1,49", "banco_1": "Sicredi", "taxa_1_72": "2,1"})
    assert set(TaxaFinanciamento.objects.values_list("banco", "prazo_meses")) == {("BV", 12), ("Sicredi", 72)}
    assert TaxaFinanciamento.objects.get(banco="BV").taxa_mensal == Decimal("0.014900")


@pytest.mark.parametrize("dados", [
    {"banco_0": "", "taxa_0_12": "1,5"},           # taxa sem banco
    {"banco_0": "BV", "taxa_0_12": "abc"},          # taxa ilegível
    {"banco_0": "BV", "taxa_0_12": "15"},           # 15% ao mês: erro de digitação
])
def test_taxas_recusam_dado_malformado(db, dados):
    assert _post_taxas(dados).status_code == 200
    assert not TaxaFinanciamento.objects.exists()


def test_taxas_recusam_banco_repetido(db):
    _post_taxas({"banco_0": "BV", "taxa_0_12": "1,5"})
    resposta = _post_taxas({"banco_0": "BV", "taxa_0_12": "1,5", "banco_1": "bv", "taxa_1_24": "1,6"})
    assert resposta.status_code == 200
    assert TaxaFinanciamento.objects.count() == 1


def _post_tarifas(**mudancas):
    dados = {}
    for tarifa in TarifaVigente.vigentes():
        prefixo = f"tarifa-{tarifa.pk}"
        dados |= {f"{prefixo}-aliquota_tributos": "0", f"{prefixo}-fiob_kwh": ""}
    bandeiras = list(Bandeira.objects.all())
    dados |= {
        "bandeira-TOTAL_FORMS": str(len(bandeiras)), "bandeira-INITIAL_FORMS": str(len(bandeiras)),
        "bandeira-MIN_NUM_FORMS": "0", "bandeira-MAX_NUM_FORMS": "1000",
    }
    for i, b in enumerate(bandeiras):
        dados |= {f"bandeira-{i}-id": str(b.pk), f"bandeira-{i}-adicional_kwh": str(b.adicional_kwh).replace(".", ","),
                  f"bandeira-{i}-vigencia": b.vigencia.isoformat()}
    return Navegador().post(reverse("core:config_tarifas"), dados | mudancas)


def test_tributos_e_fio_b_digitados_pelo_gestor(db):
    b1 = TarifaVigente.objects.get(tipo="B1")
    resposta = _post_tarifas(**{f"tarifa-{b1.pk}-aliquota_tributos": "27,5", f"tarifa-{b1.pk}-fiob_kwh": "0,312"})
    assert resposta.status_code == 302
    b1.refresh_from_db()
    assert b1.aliquota_tributos == Decimal("0.2750")
    assert b1.fiob_kwh == Decimal("0.312000")
    assert b1.fiob_conferido_em == date.today()
    assert not b1.fiob_desatualizado
    assert b1.tarifa_com_tributos == pytest.approx(Decimal("1.36935"), abs=Decimal("0.00001"))


def test_tributos_acima_do_limite_recusados(db):
    b1 = TarifaVigente.objects.get(tipo="B1")
    assert _post_tarifas(**{f"tarifa-{b1.pk}-aliquota_tributos": "75"}).status_code == 200
    b1.refresh_from_db()
    assert b1.aliquota_tributos == Decimal("0.2740")  # não mudou


def test_atualizar_tarifas_sem_internet_avisa_e_nao_apaga(db, monkeypatch):
    def falha(url):
        raise OSError("sem rede")

    monkeypatch.setattr(dados_oficiais, "baixar_json", falha)
    resposta = Navegador().post(reverse("core:config_tarifas_atualizar"), follow=True)
    assert "Não consegui falar com a ANEEL" in resposta.content.decode()
    assert TarifaVigente.objects.count() == 4


def test_atualizar_irradiacao_pela_tela(db, monkeypatch):
    monkeypatch.setattr(dados_oficiais, "baixar_json", lambda url: _nasa([5.5] * 12))
    Municipio.objects.filter(uf="TO").update(irradiacao=None)
    resposta = Navegador().post(reverse("core:config_municipios_atualizar"), follow=True)
    html = resposta.content.decode()
    assert "20 municípios atualizados" in html
    assert "Faltam 119" in html
