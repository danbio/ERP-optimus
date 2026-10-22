"""O que a IA lê na fatura e na cotação, e como a resposta vira campos da tela (D35, D37).

Funções puras: sem import de Django. A chamada à IA fica em `core/ia.py`.
Os valores voltam como o vendedor digitaria ("845,30", "2026-09-01"), para passar pelas
mesmas validações dos formulários quando ele salvar.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from core.validacoes import formatar_cpf_cnpj, formatar_reais, so_digitos

INSTRUCAO_FATURA = (
    "Esta é uma fatura de energia elétrica de uma distribuidora brasileira. Extraia os dados pedidos no esquema. "
    "Use só o que está escrito na fatura; se um dado não aparecer, deixe vazio (string vazia ou 0). "
    "consumo_kwh é o consumo faturado do mês de referência, em kWh (não o histórico). "
    "mes_referencia no formato AAAA-MM. valor_total em reais, com ponto decimal. "
    "dias_ciclo é o número de dias de leitura (entre a leitura anterior e a atual)."
)

ESQUEMA_FATURA = {
    "type": "OBJECT",
    "properties": {
        "titular": {"type": "STRING", "description": "Nome do titular da conta."},
        "cpf_cnpj": {"type": "STRING", "description": "CPF ou CNPJ do titular."},
        "numero_uc": {"type": "STRING", "description": "Número da unidade consumidora (UC) ou código da instalação."},
        "endereco": {"type": "STRING", "description": "Endereço da instalação."},
        "mes_referencia": {"type": "STRING", "description": "Mês de referência, AAAA-MM."},
        "consumo_kwh": {"type": "NUMBER"},
        "dias_ciclo": {"type": "INTEGER"},
        "valor_total": {"type": "NUMBER", "description": "Total a pagar, em reais."},
    },
    "required": ["titular", "cpf_cnpj", "numero_uc", "endereco", "mes_referencia", "consumo_kwh", "dias_ciclo",
                 "valor_total"],
}

INSTRUCAO_COTACAO = (
    "Esta é uma cotação (orçamento) de kit fotovoltaico de um distribuidor brasileiro. Extraia os dados pedidos "
    "no esquema. Use só o que está escrito; se um dado não aparecer, deixe vazio (string vazia ou 0). "
    "Datas no formato AAAA-MM-DD. Valores em reais, com ponto decimal. kwp é a potência total dos módulos. "
    "Liste todos os itens do kit, com o código do produto quando houver. Cabos em metros (unidade m)."
)

ESQUEMA_COTACAO = {
    "type": "OBJECT",
    "properties": {
        "distribuidor": {"type": "STRING"},
        "numero": {"type": "STRING", "description": "Número da cotação ou do pedido."},
        "data": {"type": "STRING", "description": "Data da cotação, AAAA-MM-DD."},
        "validade": {"type": "STRING", "description": "Válida até, AAAA-MM-DD."},
        "kwp": {"type": "NUMBER"},
        "total_produtos": {"type": "NUMBER"},
        "frete": {"type": "NUMBER"},
        "total": {"type": "NUMBER"},
        "itens": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "codigo": {"type": "STRING"},
                    "descricao": {"type": "STRING"},
                    "quantidade": {"type": "NUMBER"},
                    "unidade": {"type": "STRING", "description": "un, m, par, kit..."},
                },
                "required": ["codigo", "descricao", "quantidade", "unidade"],
            },
        },
    },
    "required": ["distribuidor", "numero", "data", "validade", "kwp", "total_produtos", "frete", "total", "itens"],
}


def _texto(valor, limite=255):
    return " ".join(str(valor or "").split())[:limite]


def _numero(valor):
    """Número da IA → Decimal, ou None se vier vazio, zero ou inválido."""
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero > 0 else None


def _data(texto):
    """"2026-10-21" → "2026-10-21"; inválida → ""."""
    try:
        return date.fromisoformat(str(texto or "").strip()[:10]).isoformat()
    except ValueError:
        return ""


def _reais(valor):
    numero = _numero(valor)
    return formatar_reais(numero) if numero is not None else ""


def _quantidade(valor):
    numero = _numero(valor)
    return f"{numero.normalize():f}".replace(".", ",") if numero is not None else ""


def campos_da_fatura(dados):
    """Resposta da IA → campos da aba "Fatura" do passo 2, mais o titular (para conferir com o cliente)."""
    competencia = ""
    achado = re.fullmatch(r"(\d{4})-(\d{1,2})", _texto(dados.get("mes_referencia")))
    if achado and 1 <= int(achado.group(2)) <= 12:
        competencia = f"{achado.group(1)}-{int(achado.group(2)):02d}-01"
    documento = so_digitos(_texto(dados.get("cpf_cnpj")))
    kwh = _numero(dados.get("consumo_kwh"))
    dias = _numero(dados.get("dias_ciclo"))
    return {
        "numero_uc": _texto(dados.get("numero_uc"), 30),
        "endereco": _texto(dados.get("endereco")),
        "competencia": competencia,
        "fatura_kwh": str(round(kwh)) if kwh else "",
        "dias_ciclo": str(round(dias)) if dias else "",
        "valor_fatura": _reais(dados.get("valor_total")),
        "cpf_cnpj": formatar_cpf_cnpj(documento) if len(documento) in (11, 14) else "",  # mascarado na fatura: vazio
        "titular": _texto(dados.get("titular"), 200),
    }


def campos_da_cotacao(dados):
    """Resposta da IA → (campos da cotação, [itens]) no formato da tela de cotação."""
    cabecalho = {
        "distribuidor": _texto(dados.get("distribuidor"), 60),
        "numero": _texto(dados.get("numero"), 60),
        "data": _data(dados.get("data")),
        "validade": _data(dados.get("validade")),
        "kwp": _quantidade(dados.get("kwp")),
        "total_produtos": _reais(dados.get("total_produtos")),
        "frete": _reais(dados.get("frete")),
        "total": _reais(dados.get("total")),
    }
    itens = []
    for item in dados.get("itens") or []:
        descricao = _texto(item.get("descricao"))
        if not descricao:
            continue
        itens.append({
            "codigo": _texto(item.get("codigo"), 60),
            "descricao": descricao,
            "quantidade": _quantidade(item.get("quantidade")) or "1",
            "unidade": (_texto(item.get("unidade"), 10) or "un").lower(),
        })
    return cabecalho, itens
