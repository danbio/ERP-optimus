"""Validação e limpeza de dados digitados (D24). Funções puras: sem import de Django.

Cada função `limpar_*` recebe o texto como o vendedor digitou e devolve o valor
pronto para gravar, ou levanta ValueError com a mensagem para mostrar na tela.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

# DDDs em uso no Brasil (Anatel).
DDDS_VALIDOS = {
    11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28,
    31, 32, 33, 34, 35, 37, 38, 41, 42, 43, 44, 45, 46, 47, 48, 49,
    51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69,
    71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85, 86, 87, 88, 89,
    91, 92, 93, 94, 95, 96, 97, 98, 99,
}


def so_digitos(texto):
    """Só os números do texto (vazio se None)."""
    return re.sub(r"\D", "", texto or "")


def nomes_iguais(a, b):
    """Mesmo nome, sem diferença de acento, maiúscula ou espaço: "José  da Silva" = "jose da silva"."""
    def simples(texto):
        sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
        return " ".join(sem_acento.casefold().split())
    return simples(a) == simples(b)


def limpar_nome(texto):
    """Tira espaços sobrando. Nome vazio não é aceito."""
    nome = " ".join((texto or "").split())
    if not nome:
        raise ValueError("Informe o nome.")
    return nome


def _digito_verificador(digitos, pesos):
    soma = sum(int(d) * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def cpf_valido(digitos):
    """True se os 11 dígitos formam um CPF com dígito verificador certo."""
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False
    d1 = _digito_verificador(digitos[:9], range(10, 1, -1))
    d2 = _digito_verificador(digitos[:10], range(11, 1, -1))
    return digitos[9:] == d1 + d2


def cnpj_valido(digitos):
    """True se os 14 dígitos formam um CNPJ com dígito verificador certo."""
    if len(digitos) != 14 or digitos == digitos[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = _digito_verificador(digitos[:12], pesos1)
    d2 = _digito_verificador(digitos[:13], pesos2)
    return digitos[12:] == d1 + d2


def limpar_cpf_cnpj(texto):
    """Devolve só os dígitos ("" se vazio). Recusa letras e dígito verificador errado."""
    texto = (texto or "").strip()
    if not texto:
        return ""
    if "*" in texto:
        raise ValueError("A fatura esconde parte do número. Peça o CPF ou CNPJ completo ao cliente "
                         "ou deixe vazio por enquanto.")
    if re.search(r"[^\d.\-/\s]", texto):
        raise ValueError("CPF ou CNPJ só pode ter números.")
    digitos = so_digitos(texto)
    if len(digitos) == 11:
        if not cpf_valido(digitos):
            raise ValueError("CPF inválido. Confira os números.")
        return digitos
    if len(digitos) == 14:
        if not cnpj_valido(digitos):
            raise ValueError("CNPJ inválido. Confira os números.")
        return digitos
    raise ValueError("CPF tem 11 números e CNPJ tem 14.")


def formatar_cpf_cnpj(digitos):
    """000.000.000-00 ou 00.000.000/0000-00; outro tamanho volta como veio."""
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    return digitos


def limpar_telefone(texto):
    """Devolve DDD + número, só dígitos (10 ou 11). Aceita +55 e zero na frente do DDD."""
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("Informe o telefone com DDD.")
    if re.search(r"[^\d()+\-.\s]", texto):
        raise ValueError("Telefone só pode ter números.")
    digitos = so_digitos(texto)
    if texto.startswith("+55") or (len(digitos) in (12, 13) and digitos.startswith("55")):
        digitos = digitos[2:]
    if len(digitos) in (11, 12) and digitos.startswith("0"):
        digitos = digitos[1:]
    if len(digitos) not in (10, 11):
        raise ValueError("Telefone com DDD: 10 ou 11 números, ex.: (63) 99999-1234.")
    if int(digitos[:2]) not in DDDS_VALIDOS:
        raise ValueError(f"DDD {digitos[:2]} não existe.")
    if len(digitos) == 11 and digitos[2] != "9":
        raise ValueError("Celular com 9 dígitos começa com 9.")
    return digitos


def formatar_telefone(digitos):
    """(00) 00000-0000 ou (00) 0000-0000; outro tamanho volta como veio."""
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return digitos


def limpar_reais(texto):
    """Converte "1.234,56", "R$ 1234,5" ou "1234" em Decimal com 2 casas.

    Vírgula é sempre o separador decimal e ponto o de milhar, como o vendedor escreve.
    """
    texto = (texto or "").replace("R$", "").replace(" ", "").strip()
    if not texto:
        raise ValueError("Informe o valor.")
    if not re.fullmatch(r"-?[\d.]*,?\d*", texto) or not re.search(r"\d", texto):
        raise ValueError("Valor inválido. Use o formato 1.234,56.")
    inteiro, _, centavos = texto.partition(",")
    if len(centavos) > 2:
        raise ValueError("Use no máximo 2 casas depois da vírgula.")
    if "." in inteiro and not re.fullmatch(r"-?\d{1,3}(\.\d{3})+", inteiro):
        raise ValueError("Ponto só separa milhar, ex.: 1.234,56.")
    try:
        valor = Decimal(f"{inteiro.replace('.', '') or '0'}.{centavos or '0'}")
    except InvalidOperation:
        raise ValueError("Valor inválido. Use o formato 1.234,56.")
    return valor.quantize(Decimal("0.01"))


def limpar_percentual(texto, minimo=0.0, maximo=100.0):
    """Converte "18", "18,5" ou "18,5%" na fração 0.185 (D24: mostrado em %, guardado em fração)."""
    texto = (texto or "").replace("%", "").replace(" ", "").strip()
    if not texto:
        raise ValueError("Informe o percentual.")
    if not re.fullmatch(r"-?\d+(,\d+)?", texto):
        raise ValueError("Percentual inválido. Use, por exemplo, 18 ou 18,5.")
    valor = float(texto.replace(",", "."))
    if not minimo <= valor <= maximo:
        raise ValueError(f"Use um valor entre {minimo:g}% e {maximo:g}%.")
    return round(valor / 100, 6)


def formatar_percentual(fracao, casas=2):
    """0.185 → "18,5" (sem zeros sobrando)."""
    texto = f"{fracao * 100:.{casas}f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def formatar_reais(valor):
    """Decimal('1234.5') → "1.234,50"."""
    inteiro, _, centavos = f"{valor:.2f}".partition(".")
    negativo = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return ("-" if negativo else "") + ".".join(grupos or ["0"]) + "," + centavos


# ---------- Textos e arquivos (P1, D41) ----------

def limpar_texto(texto, maximo):
    """Uma linha: tira espaços sobrando (inclusive no meio) e limita o tamanho."""
    limpo = " ".join((texto or "").split())
    if len(limpo) > maximo:
        raise ValueError(f"Use no máximo {maximo} caracteres (tem {len(limpo)}).")
    return limpo


def limpar_linhas(texto, maximo):
    """Texto de várias linhas: tira espaços das pontas de cada linha e as linhas vazias repetidas."""
    linhas, anterior_vazia = [], True
    for linha in (texto or "").splitlines():
        linha = " ".join(linha.split())
        if not linha and anterior_vazia:
            continue
        linhas.append(linha)
        anterior_vazia = not linha
    limpo = "\n".join(linhas).strip()
    if len(limpo) > maximo:
        raise ValueError(f"Use no máximo {maximo} caracteres (tem {len(limpo)}).")
    return limpo


# Extensões aceitas por tipo de arquivo e tamanho máximo em MB.
ARQUIVO_IMAGEM = ({".png", ".jpg", ".jpeg", ".webp"}, 5)
ARQUIVO_PDF = ({".pdf"}, 15)


def conferir_arquivo(nome, tamanho_bytes, tipo):
    """Recusa extensão fora do tipo (imagem ou PDF) e arquivo grande demais. `tipo` é ARQUIVO_IMAGEM ou ARQUIVO_PDF."""
    extensoes, maximo_mb = tipo
    extensao = ("." + nome.rsplit(".", 1)[-1].lower()) if "." in (nome or "") else ""
    if extensao not in extensoes:
        aceitas = ", ".join(sorted(e.lstrip(".").upper() for e in extensoes))
        raise ValueError(f"Envie um arquivo {aceitas}.")
    if tamanho_bytes > maximo_mb * 1024 * 1024:
        raise ValueError(f"Arquivo grande demais: o limite é {maximo_mb} MB.")


def limpar_cep(texto):
    """CEP com 8 números, gravado como 77400-000 ("" se vazio)."""
    digitos = so_digitos(texto)
    if not digitos:
        return ""
    if len(digitos) != 8:
        raise ValueError("O CEP tem 8 números.")
    return f"{digitos[:5]}-{digitos[5:]}"
