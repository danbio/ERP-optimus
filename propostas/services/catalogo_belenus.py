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
        itens.append({
            "tipo": tipo,
            "codigo": codigo,
            "descricao": descricao,
            "fabricante": fabricante(linha.get("marca"), descricao),
            "potencia_w": int(float(potencia)) if re.fullmatch(r"\d+(\.\d+)?", potencia) and tipo in (
                "modulo", "inversor", "microinversor") else None,
            "fase": fase,
            "tensao": tensao,
            "tipo_estrutura": tipo_estrutura(descricao) if tipo == "estrutura" else "",
            "preco_referencia": Decimal(preco) if re.fullmatch(r"\d+(\.\d+)?", preco) else None,
            "foto": (linha.get("foto") or "").strip(),
        })
    return itens
