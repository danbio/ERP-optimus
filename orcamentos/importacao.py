"""Grava no banco o resultado de `services.tabela_intelbras.ler_tabela` (D13).

Regras:
- produto novo é criado; produto existente é atualizado;
- produto que não veio na tabela nova fica `ativo=False` (nada é apagado);
- produto listado na aba Encerramentos fica `em_encerramento=True`, com o substituto;
- o resumo (novos, preços alterados, saíram) fica gravado na TabelaPreco.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Produto, TabelaPreco
from .services.tabela_intelbras import LeituraTabela

CAMPOS_ATUALIZAVEIS = [
    "descricao", "resumo", "bu", "segmento", "familia", "uf_origem", "ipi", "icms",
    "psd", "pscf", "qtd_multipla", "preco_referencia", "observacoes", "ncm",
    "ativo", "em_encerramento", "substituto", "tabela",
]
LIMITE_VARIACOES_NO_RESUMO = 30


def _variacao_pct(antes: Decimal, depois: Decimal):
    if not antes:
        return None
    return float((depois / antes - 1) * 100)


@transaction.atomic
def aplicar_importacao(leitura: LeituraTabela, tabela: TabelaPreco) -> dict:
    existentes = {p.codigo: p for p in Produto.objects.all()}
    novos, alterados, variacoes = [], [], []

    for dados in leitura.produtos:
        codigo = dados["codigo"]
        substituto = leitura.encerrados.get(codigo)
        dados = dados | {
            "ativo": True,
            "em_encerramento": substituto is not None,
            "substituto": substituto or "",
            "tabela": tabela,
        }
        produto = existentes.pop(codigo, None)
        if produto is None:
            novos.append(Produto(**dados))
            continue
        if produto.psd != dados["psd"] or produto.pscf != dados["pscf"]:
            variacoes.append({
                "codigo": codigo,
                "produto": dados["resumo"] or dados["descricao"],
                "psd_antes": str(produto.psd),
                "psd_depois": str(dados["psd"]),
                "variacao_pct": _variacao_pct(produto.psd, dados["psd"]),
            })
        for campo in CAMPOS_ATUALIZAVEIS:
            setattr(produto, campo, dados[campo])
        produto.atualizado_em = timezone.now()
        alterados.append(produto)

    Produto.objects.bulk_create(novos, batch_size=500)
    Produto.objects.bulk_update(alterados, CAMPOS_ATUALIZAVEIS + ["atualizado_em"], batch_size=500)

    sairam = [p for p in existentes.values() if p.ativo]
    for produto in sairam:
        produto.ativo = False
    Produto.objects.bulk_update(sairam, ["ativo"], batch_size=500)

    variacoes.sort(key=lambda v: abs(v["variacao_pct"] or 0), reverse=True)
    resumo = {
        "total": len(leitura.produtos),
        "novos": len(novos),
        "atualizados": len(alterados),
        "precos_alterados": len(variacoes),
        "sairam": len(sairam),
        "em_encerramento": sum(1 for d in leitura.produtos if d["codigo"] in leitura.encerrados),
        "maiores_variacoes": variacoes[:LIMITE_VARIACOES_NO_RESUMO],
        "codigos_que_sairam": [p.codigo for p in sairam][:LIMITE_VARIACOES_NO_RESUMO],
    }
    tabela.resumo = resumo
    tabela.save(update_fields=["resumo"])
    return resumo
