"""Leitura do CSV do catálogo Belenus (D28). Função pura: sem import de Django.

O CSV vem de `importar/extrair_belenus.py` (separador ";"), com as colunas
categoria, codigo, descricao, marca, potencia_w, preco, rs_wp, emb_venda, estoque, foto, link.
"""

import csv
import io
import re
from decimal import Decimal

DISTRIBUIDOR = "Belenus"

TIPO_POR_CATEGORIA = {
    "modulos": "modulo",
    "inversor-mono-220v": "inversor",
    "inversor-trifasico-380v": "inversor",
    "microinversores-220v": "microinversor",
    "estruturas": "estrutura",
}

# Palavra na descrição → tipo de estrutura (a primeira que aparecer).
ESTRUTURA_POR_PALAVRA = [
    ("solo", "solo"),
    ("haste solar", "fibrocimento"),
    ("laje", "laje"),
    ("fibrocimento", "fibrocimento"),
    ("metalica", "metalica"),
    ("zipada", "metalica"),
    ("colonial", "ceramica"),
    ("ceramica", "ceramica"),
]

# A "marca" do CSV é o nome do arquivo do logo; alguns precisam de acerto.
MARCAS = {
    "belenergy e solis": "Bel Energy", "belenergy": "Bel Energy", "jasolar": "JA Solar",
    "trinasolar": "Trina Solar", "foxess": "FoxESS",
}


def _sem_acento(texto):
    trocas = str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc")
    return texto.lower().translate(trocas)


def tipo_do_item(categoria, descricao):
    if categoria in TIPO_POR_CATEGORIA:
        return TIPO_POR_CATEGORIA[categoria]
    texto = _sem_acento(descricao)
    if categoria == "mat-eletricos" and texto.startswith("cabo"):
        return "cabo"
    if categoria == "mat-eletricos" and texto.startswith("conector solar"):
        return "conector"
    return "outro"


def fase_e_tensao(descricao):
    """("mono", 220), ("tri", 380) ou ("", None) pela descrição do inversor."""
    texto = _sem_acento(descricao)
    if "trifasico" in texto or "380v" in texto:
        return "tri", 380
    if "monofasico" in texto or "mono" in texto or "220v" in texto:
        return "mono", 220
    return "", None


def tipo_estrutura(descricao):
    texto = _sem_acento(descricao)
    for palavra, tipo in ESTRUTURA_POR_PALAVRA:
        if palavra in texto:
            return tipo
    return ""


# Papel do item na montagem do kit (D34). Primeira regra que casar com a descrição sem acento.
# Variantes de telha zipada, telha shingle e mini trilho alto ficam sem papel: o vendedor escolhe à mão.
FUNCAO_POR_DESCRICAO = [
    (r"zipada|shingle|mini trilho alto", ""),
    (r"^perfil fixacao .* x 2\.70m", "trilho"),
    (r"^mini trilho telha metalica 550mm", "mini_trilho"),
    (r"^grampo final", "grampo_final"),
    (r"^grampo intermediario", "grampo_intermediario"),
    (r"^garra aterramento", "aterramento"),
    (r"^suporte gancho|^suporte pe em l fibrocimento|^suporte ajustavel p/ laje", "fixacao"),
    (r"^haste solar 10mm x 250mm .*inox", "haste"),
    (r"^juncao para perfil", "juncao"),
    (r"^suporte para fixacao de microinversor", "suporte_micro"),
    (r"^cabo solar .*preto", "cabo_preto"),
    (r"^cabo solar .*vermelho", "cabo_vermelho"),
    (r"^conector solar fotovoltaico macho e femea", "conector"),
]


def funcao_no_kit(descricao):
    """"grampo_final", "trilho"... ou "" quando o item não entra sozinho no kit."""
    texto = _sem_acento(descricao)
    for padrao, funcao in FUNCAO_POR_DESCRICAO:
        if re.search(padrao, texto):
            return funcao
    return ""


def pecas_por_embalagem(descricao):
    """Peças (ou pares, no conector) vendidas juntas: "4 Pecas" → 4, "C/2 Pares" → 2. Sem indicação: 1."""
    achado = re.search(r"(\d+)\s*(pecas|peca|pares|par)\b", _sem_acento(descricao))
    return int(achado.group(1)) if achado else 1


def mppts(descricao):
    """Quantidade de MPPT do inversor pela descrição ("2mppt", "4mmpt"), ou None."""
    achado = re.search(r"(\d+)\s*mm?pp?t", _sem_acento(descricao))
    return int(achado.group(1)) if achado else None


def modulos_por_micro(potencia_w):
    """Microinversores de 1,5 kW ou mais ligam 4 módulos; os menores (Enphase), 1. O gestor corrige na tela."""
    if not potencia_w:
        return None
    return 4 if potencia_w >= 1500 else 1


def espessura_mm(descricao):
    """Espessura da moldura atendida pelo grampo final: "Grampo Final 35mm" → 35."""
    achado = re.search(r"grampo final (\d+)\s*mm", _sem_acento(descricao))
    return int(achado.group(1)) if achado else None


def fabricante(marca, descricao):
    marca = (marca or "").lower().replace("logo_", "").replace("logo ", "").replace("sem fundo", "").strip()
    if marca in MARCAS:
        return MARCAS[marca]
    if marca:
        return marca.title()
    ultima = descricao.split()[-1] if descricao.split() else ""
    return ultima.title()


def ler_catalogo_belenus(texto):
    """Texto do CSV → lista de dicts prontos para gravar em Equipamento."""
    itens = []
    for linha in csv.DictReader(io.StringIO(texto.lstrip("﻿")), delimiter=";"):
        codigo = (linha.get("codigo") or "").strip()
        descricao = " ".join((linha.get("descricao") or "").split())
        if not codigo or not descricao:
            continue
        tipo = tipo_do_item(linha["categoria"], descricao)
        fase, tensao = fase_e_tensao(descricao) if tipo in ("inversor", "microinversor") else ("", None)
        potencia = (linha.get("potencia_w") or "").strip()
        preco = (linha.get("preco") or "").strip()
        potencia_w = int(float(potencia)) if re.fullmatch(r"\d+(\.\d+)?", potencia) and tipo in (
            "modulo", "inversor", "microinversor") else None
        itens.append({
            "tipo": tipo,
            "codigo": codigo,
            "descricao": descricao,
            "fabricante": fabricante(linha.get("marca"), descricao),
            "potencia_w": potencia_w,
            "fase": fase,
            "tensao": tensao,
            "tipo_estrutura": tipo_estrutura(descricao) if tipo == "estrutura" else "",
            "preco_referencia": Decimal(preco) if re.fullmatch(r"\d+(\.\d+)?", preco) else None,
            "funcao": funcao_no_kit(descricao) if tipo in ("estrutura", "cabo", "conector") else "",
            "pecas_por_embalagem": pecas_por_embalagem(descricao) if tipo in ("estrutura", "conector") else 1,
            "mppts": mppts(descricao) if tipo == "inversor" else None,
            "modulos_por_micro": modulos_por_micro(potencia_w) if tipo == "microinversor" else None,
            "espessura_mm": espessura_mm(descricao) if tipo == "estrutura" else None,
            "foto": (linha.get("foto") or "").strip(),
        })
    return itens
