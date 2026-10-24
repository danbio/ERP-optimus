"""Leitura da tabela de preços oficial da Intelbras (.xlsb).

Função pura, sem import de Django: recebe o caminho do arquivo e a UF de
destino e devolve os produtos já filtrados. Quem grava no banco é
`orcamentos/importacao.py`.

Estrutura da tabela (out/2026):
- aba "Tabela": 1 linha por produto x UF destino; cabeçalho na 3ª linha.
- aba "Encerramentos": produtos encerrados e o substituto direto.
- aba "Orientacoes": traz o texto "Tabela referente ao mês de OUTUBRO".

As colunas são localizadas pelo NOME do cabeçalho, não pela posição: se a
Intelbras inserir uma coluna nova, o importador continua funcionando.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from pyxlsb import open_workbook

# nome no cabeçalho da planilha -> nome do campo no Produto
COLUNAS_TABELA = {
    "Código Produto": "codigo",
    "Descrição do Produto": "descricao",
    "Produto/Resumo": "resumo",
    "BU": "bu",
    "Segmento": "segmento",
    "Família": "familia",
    "UF Origem": "uf_origem",
    "UF Destino": "uf_destino",
    "IPI": "ipi",
    "ICMS": "icms",
    "PSD": "psd",
    "PSCF": "pscf",
    "Qtd. Múltipla": "qtd_multipla",
    "Preço Referência": "preco_referencia",
    "Observações": "observacoes",
    "NCM": "ncm",
}
COLUNAS_OBRIGATORIAS = ["Código Produto", "Descrição do Produto", "UF Destino", "PSD", "PSCF"]


class TabelaInvalida(Exception):
    """O arquivo não tem o formato esperado da tabela Intelbras."""


@dataclass
class LeituraTabela:
    referencia: str  # ex.: "OUTUBRO"
    produtos: list[dict] = field(default_factory=list)
    encerrados: dict[str, str] = field(default_factory=dict)  # codigo -> substituto


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _decimal(valor, casas="0.01") -> Decimal:
    if valor in (None, "", "-"):
        return Decimal("0")
    try:
        return Decimal(str(valor)).quantize(Decimal(casas))
    except InvalidOperation:
        return Decimal("0")


def _inteiro(valor) -> int:
    try:
        return max(int(float(valor)), 1)
    except (TypeError, ValueError):
        return 1


def _linhas(workbook, aba):
    with workbook.get_sheet(aba) as planilha:
        for linha in planilha.rows():
            yield [celula.v for celula in linha]


def _mapa_cabecalho(linhas_iniciais, obrigatorias):
    """Procura, nas primeiras linhas, a que contém os títulos das colunas."""
    for indice, linha in enumerate(linhas_iniciais):
        textos = [_texto(v) for v in linha]
        if all(nome in textos for nome in obrigatorias):
            return indice, {nome: textos.index(nome) for nome in textos if nome}
    raise TabelaInvalida(
        f"Cabeçalho não encontrado. Colunas esperadas: {', '.join(obrigatorias)}."
    )


def _ler_referencia(workbook) -> str:
    try:
        for linha in _linhas(workbook, "Orientacoes"):
            for valor in linha:
                texto = _texto(valor)
                if "referente ao mês de" in texto:
                    return texto.split("mês de", 1)[1].strip().upper()
    except Exception:  # aba ausente: referência fica em branco, não impede a importação
        pass
    return ""


def _ler_encerrados(workbook) -> dict[str, str]:
    if "Encerramentos" not in workbook.sheets:
        return {}
    linhas = list(_linhas(workbook, "Encerramentos"))
    indice, cab = _mapa_cabecalho(linhas[:10], ["Código Produto", "Substituto Direto"])
    encerrados = {}
    for linha in linhas[indice + 1:]:
        codigo = _texto(linha[cab["Código Produto"]])
        if not codigo:
            continue
        substituto = _texto(linha[cab["Substituto Direto"]])
        encerrados[codigo] = "" if substituto.strip(" -") == "" else substituto
    return encerrados


def ler_tabela(caminho, uf_destino: str) -> LeituraTabela:
    """Lê o .xlsb da Intelbras e devolve os produtos da UF de destino e os encerrados (D13). Arquivo errado: TabelaInvalida."""
    uf_destino = uf_destino.strip().upper()
    try:
        workbook = open_workbook(str(caminho))
    except Exception as erro:
        raise TabelaInvalida(f"Não foi possível abrir o arquivo como .xlsb ({erro}).") from erro

    with workbook:
        if "Tabela" not in workbook.sheets:
            raise TabelaInvalida('Aba "Tabela" não encontrada no arquivo.')

        linhas = _linhas(workbook, "Tabela")
        iniciais = []
        for _ in range(10):
            iniciais.append(next(linhas, []))
        indice_cab, cab = _mapa_cabecalho(iniciais, COLUNAS_OBRIGATORIAS)
        presentes = {nome: campo for nome, campo in COLUNAS_TABELA.items() if nome in cab}

        def registros():
            yield from iniciais[indice_cab + 1:]
            yield from linhas

        produtos = {}
        for linha in registros():
            if len(linha) <= cab["UF Destino"]:
                continue
            if _texto(linha[cab["UF Destino"]]).upper() != uf_destino:
                continue
            bruto = {campo: linha[cab[nome]] for nome, campo in presentes.items()}
            codigo = _texto(bruto["codigo"])
            if not codigo:
                continue
            produtos[codigo] = {
                "codigo": codigo,
                "descricao": _texto(bruto.get("descricao"))[:500],
                "resumo": _texto(bruto.get("resumo"))[:255],
                "bu": _texto(bruto.get("bu")),
                "segmento": _texto(bruto.get("segmento")),
                "familia": _texto(bruto.get("familia")),
                "uf_origem": _texto(bruto.get("uf_origem")),
                "ipi": _decimal(bruto.get("ipi"), "0.0001"),
                "icms": _decimal(bruto.get("icms"), "0.0001"),
                "psd": _decimal(bruto.get("psd")),
                "pscf": _decimal(bruto.get("pscf")),
                "qtd_multipla": _inteiro(bruto.get("qtd_multipla")),
                "preco_referencia": _texto(bruto.get("preco_referencia")),
                "observacoes": _texto(bruto.get("observacoes")),
                "ncm": _texto(bruto.get("ncm")),
            }

        if not produtos:
            raise TabelaInvalida(f"Nenhum produto encontrado para a UF de destino {uf_destino}.")

        return LeituraTabela(
            referencia=_ler_referencia(workbook),
            produtos=list(produtos.values()),
            encerrados=_ler_encerrados(workbook),
        )
