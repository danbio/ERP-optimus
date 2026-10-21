"""Emissão e versões da proposta (D07, D31).

Emitir congela o kit e o preço que a tela mostrava, grava o snapshot e guarda o PDF.
Revisar cria a versão seguinte, com o mesmo número, em rascunho.
"""

from decimal import Decimal

from django.core.files.base import ContentFile
from django.utils import timezone

from .models import Proposta
from .montagem import gravar_resultado, montar


class ErroEmissao(Exception):
    """A proposta não pode ser emitida (ou a ação não vale no status atual)."""


def _reais(valor):
    return Decimal(f"{valor:.2f}")


def preparar_emissao(proposta):
    """Congela kit, preço e snapshot e marca como emitida (sem gravar o PDF ainda).

    Chamar dentro de uma transação: se o PDF não sair, tudo volta a rascunho.
    """
    if proposta.status != Proposta.Status.RASCUNHO:
        raise ErroEmissao("Só um rascunho pode ser emitido.")
    if proposta.eh_antiga:
        if not proposta.investimento or not proposta.itens_kit.exists():
            raise ErroEmissao("Preencha o kit e o investimento antes de emitir.")
    else:
        m = montar(proposta)
        if not m.resultado:
            raise ErroEmissao(m.mensagem or "Complete os passos da proposta antes de emitir.")
        proposta.modulo, proposta.qtd_modulos = m.modulo, m.qtd_modulos
        proposta.inversor, proposta.qtd_inversores = m.inversor, m.qtd_inversores
        proposta.cabo_preto_m, proposta.cabo_vermelho_m = m.cabo_preto, m.cabo_vermelho
        proposta.custo_kit = _reais(m.custo_kit)
        proposta.mao_de_obra = _reais(m.mao_de_obra)
        proposta.desconto, proposta.desconto_pct = _reais(m.desconto), None
        if m.prazo:
            proposta.prazo_comparacao = m.prazo
        gravar_resultado(proposta, m)  # snapshot das premissas e dos resultados, kit e investimento
    proposta.status = Proposta.Status.EMITIDA
    proposta.emissao = timezone.localdate()
    proposta.save()


def concluir_emissao(proposta, pdf):
    """Guarda o PDF gerado e marca como substituídas as versões emitidas anteriores do mesmo número."""
    proposta.pdf.save(f"{proposta.numero}_v{proposta.versao}.pdf", ContentFile(pdf), save=False)
    proposta.save(update_fields=["pdf"])
    _outras_versoes(proposta).filter(status=Proposta.Status.EMITIDA).update(status=Proposta.Status.SUBSTITUIDA)


def _outras_versoes(proposta):
    return Proposta.objects.filter(numero=proposta.numero).exclude(pk=proposta.pk)


def rascunho_aberto(proposta):
    """Versão em rascunho já aberta para o mesmo número, se houver."""
    return _outras_versoes(proposta).filter(status=Proposta.Status.RASCUNHO).first()


def revisar(proposta):
    """Nova versão em rascunho, copiando tudo (inclusive o kit). Devolve a nova proposta."""
    if proposta.status not in (Proposta.Status.EMITIDA, Proposta.Status.PERDIDA):
        raise ErroEmissao(f"Uma proposta {proposta.get_status_display().lower()} não pode ser revisada.")
    aberto = rascunho_aberto(proposta)
    if aberto:
        return aberto
    itens = list(proposta.itens_kit.all())
    nova = Proposta.objects.get(pk=proposta.pk)
    nova.pk = None
    nova._state.adding = True
    nova.versao = Proposta.objects.filter(numero=proposta.numero).order_by("-versao").first().versao + 1
    nova.origem = proposta
    nova.status = Proposta.Status.RASCUNHO
    nova.emissao = None
    nova.data_aceite = None
    nova.motivo_perda = ""
    nova.obs_perda = ""
    nova.pdf = ""
    nova.save()
    for item in itens:
        item.pk = None
        item.proposta = nova
        item.save()
    return nova


def aceitar(proposta, data):
    if proposta.status != Proposta.Status.EMITIDA:
        raise ErroEmissao("Só uma proposta emitida pode ser aceita.")
    proposta.status = Proposta.Status.ACEITA
    proposta.data_aceite = data
    proposta.save(update_fields=["status", "data_aceite"])
    _outras_versoes(proposta).update(status=Proposta.Status.SUBSTITUIDA)


def marcar_perdida(proposta, motivo, observacao=""):
    if proposta.status != Proposta.Status.EMITIDA:
        raise ErroEmissao("Só uma proposta emitida pode ser marcada como perdida.")
    proposta.status = Proposta.Status.PERDIDA
    proposta.motivo_perda = motivo
    proposta.obs_perda = observacao
    proposta.save(update_fields=["status", "motivo_perda", "obs_perda"])
