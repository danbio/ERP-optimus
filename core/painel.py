"""Painel da página inicial (H16, A19, A20, D46): números do mês, "ligar hoje" e propostas paradas.

O vendedor vê só o que é dele; o gestor vê tudo e a tabela por vendedor. Volume pequeno (~50 propostas
por mês): as contas são feitas em Python sobre listas, para ficarem legíveis.
"""

from datetime import timedelta

from django.urls import reverse

from orcamentos.models import Orcamento
from propostas.models import Proposta


def _ultima_versao(objetos):
    """Uma linha por número (a versão mais alta); rascunho sem número conta sozinho."""
    por_numero = {}
    for objeto in objetos:
        chave = objeto.numero or f"pk{objeto.pk}"
        if chave not in por_numero or objeto.versao > por_numero[chave].versao:
            por_numero[chave] = objeto
    return list(por_numero.values())


def _nome(usuario):
    return (usuario.get_full_name() or usuario.username) if usuario else "Sem vendedor"


def _ligar_hoje(propostas, orcamentos, hoje):
    linhas = []
    abertas = propostas.filter(status__in=[Proposta.Status.RASCUNHO, Proposta.Status.EMITIDA],
                               proximo_contato__lte=hoje)
    for p in _ultima_versao(abertas.select_related("cliente")):
        linhas.append({"tipo": "Proposta solar", "titulo": p.identificacao, "cliente": p.cliente,
                       "data": p.proximo_contato, "atrasado": p.proximo_contato < hoje,
                       "url": reverse("propostas:detalhe", args=[p.pk])})
    abertos = orcamentos.filter(status__in=[Orcamento.Status.RASCUNHO, Orcamento.Status.EMITIDO],
                                proximo_contato__lte=hoje)
    for o in _ultima_versao(abertos.select_related("cliente")):
        linhas.append({"tipo": "Orçamento Intelbras", "titulo": f"{o.numero} v{o.versao}", "cliente": o.cliente,
                       "data": o.proximo_contato, "atrasado": o.proximo_contato < hoje,
                       "url": reverse("orcamentos:editor", args=[o.pk])})
    return sorted(linhas, key=lambda linha: linha["data"])


def montar_painel(usuario, gestor, hoje, config):
    """Números do painel do mês para `usuario` (todos, se `gestor`). `hoje` é a data de referência; prazos vêm de `config`."""
    propostas = Proposta.objects.all()
    orcamentos = Orcamento.objects.all()
    if not gestor:
        propostas = propostas.filter(vendedor=usuario)
        orcamentos = orcamentos.filter(vendedor=usuario)
    inicio_mes = hoje.replace(day=1)

    emitidas = _ultima_versao(propostas.filter(emissao__gte=inicio_mes, emissao__lte=hoje).select_related("vendedor"))
    aceitas = list(propostas.filter(status=Proposta.Status.ACEITA, data_aceite__gte=inicio_mes)
                   .select_related("vendedor"))
    perdidas = _ultima_versao(propostas.filter(status=Proposta.Status.PERDIDA, perdida_em__gte=inicio_mes))
    motivos = {}
    for p in perdidas:
        rotulo = p.get_motivo_perda_display() or "Sem motivo"
        motivos[rotulo] = motivos.get(rotulo, 0) + 1

    em_aberto = list(propostas.filter(status=Proposta.Status.EMITIDA).select_related("cliente"))
    limite_vencimento = hoje + timedelta(days=config.dias_aviso_vencimento)
    vencendo = sorted((p for p in em_aberto if hoje <= p.validade_ate <= limite_vencimento),
                      key=lambda p: p.validade_ate)
    limite_parada = hoje - timedelta(days=config.dias_sem_retorno)
    paradas = [p for p in em_aberto if not p.vencida and not p.proximo_contato and p.emissao <= limite_parada]

    orcamentos_abertos = _ultima_versao(
        orcamentos.filter(status__in=[Orcamento.Status.RASCUNHO, Orcamento.Status.EMITIDO]))
    orcamentos_aceitos = _ultima_versao(
        orcamentos.filter(status=Orcamento.Status.ACEITO, emissao__gte=inicio_mes))

    painel = {
        "inicio_mes": inicio_mes,
        "ligar_hoje": _ligar_hoje(propostas, orcamentos, hoje),
        "emitidas": len(emitidas),
        "aceitas": len(aceitas),
        "perdidas": len(perdidas),
        "conversao": len(aceitas) / len(emitidas) * 100 if emitidas else None,
        "kwp_aceito": sum(p.kwp or 0 for p in aceitas),
        "valor_aceito": sum(p.investimento or 0 for p in aceitas),
        "motivos": sorted(motivos.items(), key=lambda item: -item[1]),
        "vencendo": vencendo,
        "paradas": paradas,
        "dias_aviso_vencimento": config.dias_aviso_vencimento,
        "dias_sem_retorno": config.dias_sem_retorno,
        "orcamentos_abertos": len(orcamentos_abertos),
        "orcamentos_abertos_valor": sum(o.total for o in orcamentos_abertos),
        "orcamentos_aceitos": len(orcamentos_aceitos),
        "orcamentos_aceitos_valor": sum(o.total for o in orcamentos_aceitos),
    }
    if gestor:
        por_vendedor = {}
        for p in emitidas:
            por_vendedor.setdefault(_nome(p.vendedor), {"emitidas": 0, "aceitas": 0, "valor": 0})["emitidas"] += 1
        for p in aceitas:
            linha = por_vendedor.setdefault(_nome(p.vendedor), {"emitidas": 0, "aceitas": 0, "valor": 0})
            linha["aceitas"] += 1
            linha["valor"] += p.investimento or 0
        painel["por_vendedor"] = sorted(por_vendedor.items())
    return painel
