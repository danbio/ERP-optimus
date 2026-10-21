"""Busca de município pelo nome digitado (usado nas migrations que convertem texto em FK)."""

import unicodedata

# Nomes antigos que ainda aparecem em faturas e cadastros.
NOMES_ANTIGOS = {
    "sao valerio da natividade": "sao valerio",
}


def chave_nome(nome):
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    chave = " ".join(sem_acento.lower().split())
    return NOMES_ANTIGOS.get(chave, chave)
