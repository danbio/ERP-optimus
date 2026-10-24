"""Emissão e versões da proposta (D07, D31).

Emitir congela o kit e o preço que a tela mostrava, grava o snapshot e guarda o PDF.
Revisar cria a versão seguinte, com o mesmo número, em rascunho.
"""

from decimal import Decimal

from django.core.files.base import ContentFile
from django.utils import timezone

from .models import Proposta
from .montagem import ajustes_do_kit_completo, gravar_resultado, impedimentos_de_emissao, montar, registro_da_emissao


class ErroEmissao(Exception):
    """A proposta não pode ser emitida (ou a ação não vale no status atual)."""


def _reais(valor):
    return Decimal(f"{valor:.2f}")


def preparar_emissao(proposta, usuario=None):
    """Congela kit, preço e snapshot e marca como emitida (sem gravar o PDF ainda).

    Chamar dentro de uma transação: se o PDF não sair, tudo volta a rascunho.
    """
    if proposta.status != Proposta.Status.RASCUNHO:
        raise ErroEmissao("Só um rascunho pode ser emitido.")
    m = montar(proposta)
    motivos = impedimentos_de_emissao(m, proposta)
    if motivos:
        raise ErroEmissao(" ".join(motivos))
    proposta.modulo, proposta.qtd_modulos = m.modulo, m.qtd_modulos
    proposta.inversor, proposta.qtd_inversores = m.inversor, m.qtd_inversores
    proposta.fileiras = m.fileiras_texto
    if not m.kit_da_cotacao:
        proposta.ajustes_kit = ajustes_do_kit_completo(m)  # o kit não muda se o catálogo mudar (D34)
    proposta.custo_kit = _reais(m.custo_kit)
    proposta.mao_de_obra = _reais(m.mao_de_obra)
    proposta.desconto, proposta.desconto_pct = _reais(m.desconto), None
    if m.prazo:
        proposta.prazo_comparacao = m.prazo
    gravar_resultado(proposta, m)  # snapshot das premissas e dos resultados, kit e investimento
    proposta.registro = registro_da_emissao(proposta, m, proposta.premissas)
    if not proposta.numero:
        proposta.numero = Proposta.proximo_numero()  # número definitivo só na primeira emissão (A13)
    proposta.status = Proposta.Status.EMITIDA
    proposta.emissao = timezone.localdate()
    proposta.emitida_por = usuario
    proposta.save()


def concluir_emissao(proposta, pdf):
    """Guarda o PDF gerado e marca como substituídas as versões emitidas anteriores do mesmo número."""
    proposta.pdf.save(f"{proposta.numero}_v{proposta.versao}.pdf", ContentFile(pdf), save=False)
    proposta.save(update_fields=["pdf"])
    _outras_versoes(proposta).filter(status=Proposta.Status.EMITIDA).update(status=Proposta.Status.SUBSTITUIDA)


def _outras_versoes(proposta):
    if not proposta.numero:
        return Proposta.objects.none()
    return Proposta.objects.filter(numero=proposta.numero).exclude(pk=proposta.pk)


def versoes(proposta):
    """Todas as versões do mesmo número, da mais nova para a mais antiga."""
    if not proposta.numero:
        return Proposta.objects.filter(pk=proposta.pk)
    return Proposta.objects.filter(numero=proposta.numero).order_by("-versao")


def descartar(proposta):
    """Apaga um rascunho que não vai virar proposta (A13). Emitidas nunca são apagadas."""
    if proposta.status != Proposta.Status.RASCUNHO:
        raise ErroEmissao("Só um rascunho pode ser descartado.")
    proposta.delete()


def rascunho_aberto(proposta):
    """Versão em rascunho já aberta para o mesmo número, se houver."""
    return _outras_versoes(proposta).filter(status=Proposta.Status.RASCUNHO).first()


def revisar(proposta):
    """Nova versão em rascunho, copiando tudo (inclusive o kit). Devolve a nova proposta."""
    if proposta.status not in (Proposta.Status.EMITIDA, Proposta.Status.PERDIDA, Proposta.Status.ACEITA):
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
    nova.aceite_desfeito_em = None
    nova.motivo_aceite_desfeito = ""
    nova.pdf = ""
    nova.registro = {}
    nova.emitida_por = nova.aceita_por = nova.perdida_por = nova.aceite_desfeito_por = None
    nova.perdida_em = None
    nova.save()
    for item in itens:
        item.pk = None
        item.proposta = nova
        item.save()
    return nova


def aceitar(proposta, data, usuario=None):
    if proposta.status != Proposta.Status.EMITIDA:
        raise ErroEmissao("Só uma proposta emitida pode ser aceita.")
    proposta.status = Proposta.Status.ACEITA
    proposta.data_aceite = data
    proposta.aceita_por = usuario
    proposta.save(update_fields=["status", "data_aceite", "aceita_por"])
    # Só as emitidas e uma aceita antes viram substituídas; um rascunho aberto continua editável (A11).
    _outras_versoes(proposta).filter(
        status__in=[Proposta.Status.EMITIDA, Proposta.Status.ACEITA]
    ).update(status=Proposta.Status.SUBSTITUIDA)


def desfazer_aceite(proposta, motivo, usuario=None):
    """Volta a aceita para emitida, com o motivo (D33: vendedor ou gestor). As versões que o aceite
    substituiu continuam substituídas; para usar uma delas, revise."""
    if proposta.status != Proposta.Status.ACEITA:
        raise ErroEmissao("Só uma proposta aceita pode ter o aceite desfeito.")
    if not motivo.strip():
        raise ErroEmissao("Informe por que o aceite foi desfeito.")
    proposta.status = Proposta.Status.EMITIDA
    proposta.data_aceite = None
    proposta.aceite_desfeito_em = timezone.localdate()
    proposta.motivo_aceite_desfeito = motivo.strip()
    proposta.aceite_desfeito_por = usuario
    proposta.save(update_fields=["status", "data_aceite", "aceite_desfeito_em", "motivo_aceite_desfeito",
                                 "aceite_desfeito_por"])


def marcar_perdida(proposta, motivo, observacao="", usuario=None):
    if proposta.status != Proposta.Status.EMITIDA:
        raise ErroEmissao("Só uma proposta emitida pode ser marcada como perdida.")
    proposta.status = Proposta.Status.PERDIDA
    proposta.motivo_perda = motivo
    proposta.obs_perda = observacao
    proposta.perdida_por = usuario
    proposta.perdida_em = timezone.localdate()
    proposta.save(update_fields=["status", "motivo_perda", "obs_perda", "perdida_por", "perdida_em"])
