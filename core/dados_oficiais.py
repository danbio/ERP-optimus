"""Atualização dos dados oficiais (D21): tarifas e bandeiras da ANEEL, municípios e irradiação.

Cada atualização baixa da internet com urllib, grava no banco com fonte e data e
devolve um texto curto para mostrar ao gestor. A proposta nunca chama a internet:
só lê o que está no banco. Falha de rede não apaga dado antigo.

As funções `ler_*` são puras (recebem o que a API devolveu e devolvem os valores
prontos) e têm teste próprio; as funções `atualizar_*` fazem o download e gravam.
"""

import csv
import gzip
import io
import json
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal

ANEEL_API = "https://dadosabertos.aneel.gov.br/api/3/action/datastore_search?"
ANEEL_TARIFAS = "fcf2906c-7c32-4b9b-a637-054e7a5234f4"
ANEEL_BANDEIRAS = "5879ca80-b3bd-45b1-a135-d9b77c1d5b36"
MUNICIPIOS_CSV = "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv"

# Como cada tipo de tarifa do Grupo B aparece no conjunto da ANEEL.
FILTROS_TARIFA = {
    "B1": {"DscSubGrupo": "B1", "DscClasse": "Residencial", "DscSubClasse": "Residencial"},
    "B1_BAIXA_RENDA": {"DscSubGrupo": "B1", "DscClasse": "Residencial", "DscSubClasse": "Baixa Renda"},
    "B2": {"DscSubGrupo": "B2", "DscClasse": "Rural", "DscSubClasse": "Não se aplica"},
    "B3": {"DscSubGrupo": "B3", "DscClasse": "Não se aplica", "DscSubClasse": "Não se aplica"},
}

# Nomes da ANEEL → nomes que o vendedor vê. A ordem é a da tela.
NOMES_BANDEIRA = {"Amarela": "Amarela", "Vermelha P1": "Vermelha patamar 1", "Vermelha P2": "Vermelha patamar 2"}


def baixar_json(url, timeout=90):
    requisicao = urllib.request.Request(url, headers={"User-Agent": "meu_erp (Optimus Energia Solar)"})
    with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
        conteudo = resposta.read()
    if conteudo[:2] == b"\x1f\x8b":  # alguns servidores mandam gzip mesmo sem pedir
        conteudo = gzip.decompress(conteudo)
    return json.loads(conteudo)


def numero_aneel(texto):
    """A ANEEL publica "683,27" e ",00"."""
    return Decimal((texto or "0").strip().replace(".", "").replace(",", ".") or "0")


# ---------- Tarifas ----------

def ler_tarifas_aneel(registros):
    """Registros da ANEEL (uma distribuidora) → {tipo: {vigencia, tusd, te, reh}} em R$/kWh.

    Usa só a Tarifa de Aplicação, modalidade Convencional, sem detalhe (a linha "SCEE" é a
    da energia compensada). Fica a vigência mais recente de cada tipo.
    """
    resultado = {}
    for tipo, filtro in FILTROS_TARIFA.items():
        candidatos = [
            r for r in registros
            if r.get("DscBaseTarifaria") == "Tarifa de Aplicação"
            and r.get("DscModalidadeTarifaria") == "Convencional"
            and r.get("DscDetalhe") == "Não se aplica"
            and all(r.get(campo) == valor for campo, valor in filtro.items())
        ]
        if not candidatos:
            continue
        mais_recente = max(candidatos, key=lambda r: r["DatInicioVigencia"])
        fator = Decimal("1000") if mais_recente.get("DscUnidadeTerciaria") == "MWh" else Decimal("1")
        resultado[tipo] = {
            "vigencia": date.fromisoformat(mais_recente["DatInicioVigencia"][:10]),
            "tusd": (numero_aneel(mais_recente["VlrTUSD"]) / fator).quantize(Decimal("0.000001")),
            "te": (numero_aneel(mais_recente["VlrTE"]) / fator).quantize(Decimal("0.000001")),
            "reh": mais_recente.get("DscREH", ""),
        }
    return resultado


def _registros_aneel_tarifas(sigla, subgrupo):
    consulta = {
        "resource_id": ANEEL_TARIFAS,
        "limit": 200,
        "sort": "DatInicioVigencia desc",
        "filters": json.dumps({
            "SigAgente": sigla,
            "DscSubGrupo": subgrupo,
            "DscBaseTarifaria": "Tarifa de Aplicação",
            "DscModalidadeTarifaria": "Convencional",
        }),
    }
    return baixar_json(ANEEL_API + urllib.parse.urlencode(consulta))["result"]["records"]


def atualizar_tarifas():
    """Para cada distribuidora com sigla ANEEL (D47), grava uma TarifaVigente nova por tipo cuja vigência mudou.

    Tributos e Fio B são do gestor: a tarifa nova começa com os valores da anterior,
    e o Fio B fica marcado para conferir (D21).
    """
    from .models import Distribuidora

    textos = [_atualizar_tarifas_de(d) for d in Distribuidora.objects.exclude(sigla_aneel="")]
    return " ".join(textos) or "Nenhuma distribuidora com sigla ANEEL cadastrada. Nada foi alterado."


def _atualizar_tarifas_de(distribuidora):
    from propostas.models import TarifaVigente

    registros = []
    for subgrupo in ("B1", "B2", "B3"):
        registros += _registros_aneel_tarifas(distribuidora.sigla_aneel, subgrupo)
    lidas = ler_tarifas_aneel(registros)
    if not lidas:
        return f"A ANEEL não devolveu tarifas da {distribuidora}. Nada foi alterado."

    novas, iguais = [], []
    for tipo, valores in lidas.items():
        anterior = TarifaVigente.objects.filter(
            distribuidora=distribuidora.nome, tipo=tipo).order_by("-vigencia_inicio").first()
        tarifa, criada = TarifaVigente.objects.update_or_create(
            distribuidora=distribuidora.nome, tipo=tipo, vigencia_inicio=valores["vigencia"],
            defaults={
                "tusd": valores["tusd"], "te": valores["te"],
                "fonte": f"ANEEL, dados abertos ({valores['reh'][:150]})",
                "atualizado_em": date.today(),
            },
        )
        if criada and anterior:
            tarifa.aliquota_tributos = anterior.aliquota_tributos
            tarifa.fiob_kwh = anterior.fiob_kwh
            tarifa.save(update_fields=["aliquota_tributos", "fiob_kwh"])
        (novas if criada else iguais).append(tarifa.get_tipo_display())
    if novas:
        return f"{distribuidora}: tarifas novas ({', '.join(novas)}). Confira os tributos e o Fio B."
    return f"{distribuidora}: tarifas já estavam em dia ({len(iguais)} tipos)."


# ---------- Bandeiras ----------

def ler_bandeiras_aneel(registros):
    """Registros "Bandeira Tarifária - Adicional" → {nome: (adicional R$/kWh, vigência)} da resolução mais recente."""
    resultado = {}
    for registro in sorted(registros, key=lambda r: r["DatVigencia"]):
        nome = NOMES_BANDEIRA.get(registro["NomBandeiraAcionada"])
        if nome:
            valor = (numero_aneel(registro["VlrAdicionalBandeiraRSMWh"]) / 1000).quantize(Decimal("0.00001"))
            resultado[nome] = (valor, date.fromisoformat(registro["DatVigencia"][:10]))
    return resultado


def atualizar_bandeiras():
    from propostas.models import Bandeira

    consulta = {"resource_id": ANEEL_BANDEIRAS, "limit": 100}
    lidas = ler_bandeiras_aneel(baixar_json(ANEEL_API + urllib.parse.urlencode(consulta))["result"]["records"])
    if not lidas:
        return "A ANEEL não devolveu as bandeiras. Nada foi alterado."
    Bandeira.objects.update_or_create(
        nome="Verde", defaults={"adicional_kwh": Decimal("0"), "vigencia": min(v for _, v in lidas.values()), "ordem": 0}
    )
    for ordem, nome in enumerate(NOMES_BANDEIRA.values(), start=1):
        if nome in lidas:
            valor, vigencia = lidas[nome]
            Bandeira.objects.update_or_create(nome=nome, defaults={"adicional_kwh": valor, "vigencia": vigencia, "ordem": ordem})
    return "Bandeiras atualizadas: " + ", ".join(f"{n} R$ {v:.5f}/kWh" for n, (v, _) in lidas.items())


# ---------- Municípios ----------

def ler_municipios_csv(texto, uf_codigo):
    """CSV de municípios (código IBGE, nome, latitude, longitude, código da UF) → lista de dicts."""
    return [
        {"codigo_ibge": int(r["codigo_ibge"]), "nome": r["nome"], "latitude": float(r["latitude"]),
         "longitude": float(r["longitude"])}
        for r in csv.DictReader(io.StringIO(texto))
        if r["codigo_uf"] == str(uf_codigo)
    ]


CODIGOS_UF = {
    "AC": 12, "AL": 27, "AM": 13, "AP": 16, "BA": 29, "CE": 23, "DF": 53, "ES": 32, "GO": 52, "MA": 21,
    "MG": 31, "MS": 50, "MT": 51, "PA": 15, "PB": 25, "PE": 26, "PI": 22, "PR": 41, "RJ": 33, "RN": 24,
    "RO": 11, "RR": 14, "RS": 43, "SC": 42, "SE": 28, "SP": 35, "TO": 17,
}


def importar_municipios(uf):
    from .models import Distribuidora, Municipio

    uf = uf.upper()
    # Estado com uma distribuidora só: os municípios já vêm com ela; senão, o gestor escolhe (D47).
    distribuidoras = list(Distribuidora.objects.filter(uf=uf))
    distribuidora = distribuidoras[0] if len(distribuidoras) == 1 else None
    requisicao = urllib.request.Request(MUNICIPIOS_CSV, headers={"User-Agent": "meu_erp"})
    with urllib.request.urlopen(requisicao, timeout=90) as resposta:
        texto = resposta.read().decode("utf-8")
    lidos = ler_municipios_csv(texto, CODIGOS_UF[uf])
    for m in lidos:
        Municipio.objects.update_or_create(
            codigo_ibge=m["codigo_ibge"],
            defaults={"nome": m["nome"], "uf": uf, "latitude": m["latitude"], "longitude": m["longitude"]},
        )
    if distribuidora:
        Municipio.objects.filter(uf=uf, distribuidora__isnull=True).update(distribuidora=distribuidora)
    return f"{len(lidos)} municípios de {uf} gravados."


# ---------- Irradiação (D27) ----------

NASA_POWER = "https://power.larc.nasa.gov/api/temporal/climatology/point?"
FONTE_NASA = "NASA POWER, climatologia 2001–2025 (ALLSKY_SFC_SW_DWN)"
MESES_NASA = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def ler_irradiacao_nasa(resposta):
    """Resposta da NASA POWER → 12 médias mensais em kWh/m²·dia (plano horizontal)."""
    valores = resposta["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
    mensal = [round(float(valores[mes]), 2) for mes in MESES_NASA]
    if any(v <= 0 for v in mensal):  # a NASA usa -999 para dado faltante
        raise ValueError("A NASA POWER devolveu mês sem dado.")
    return mensal


def atualizar_irradiacao(municipios):
    """Busca a irradiação de cada município da lista. Devolve (atualizados, erros)."""
    atualizados, erros = 0, []
    for municipio in municipios:
        consulta = {
            "parameters": "ALLSKY_SFC_SW_DWN", "community": "RE", "format": "JSON",
            "latitude": f"{municipio.latitude:.4f}", "longitude": f"{municipio.longitude:.4f}",
        }
        try:
            municipio.irradiacao = ler_irradiacao_nasa(baixar_json(NASA_POWER + urllib.parse.urlencode(consulta)))
        except Exception as erro:  # rede, API fora do ar ou dado faltante: mantém o que havia
            erros.append(f"{municipio.nome}: {erro}")
            continue
        municipio.fonte_irradiacao = FONTE_NASA
        municipio.atualizado_em = date.today()
        municipio.save(update_fields=["irradiacao", "fonte_irradiacao", "atualizado_em"])
        atualizados += 1
    return atualizados, erros


def municipios_para_atualizar(ufs=None):
    """Municípios (dos estados da lista) sem irradiação ou com dado de mais de um ano (D21)."""
    from django.db.models import Q

    from .models import Municipio

    um_ano_atras = date.today().replace(year=date.today().year - 1)
    pendentes = Municipio.objects.filter(
        Q(irradiacao__isnull=True) | Q(atualizado_em__isnull=True) | Q(atualizado_em__lt=um_ano_atras)
    )
    return pendentes.filter(uf__in=[u.upper() for u in ufs]) if ufs else pendentes
