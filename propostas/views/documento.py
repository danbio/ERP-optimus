"""PDF da proposta (fatia 5, D30): contexto das páginas, pré-visualização e download."""

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import ConfigEmpresa
from core.pdf import ErroPDF, html_para_pdf

from ..models import FioBEscalonamento, Proposta
from ..montagem import montar, premissas_da_proposta
from ..services import graficos
from ..services.pdf import ErroAnexo, contar_paginas, ler_cores, mesclar_anexo


# ---------------------------------------------------------------- PDF (fatia 5)

PAGINAS_FIXAS = 7  # capa, resumo, fatura, geração, financeiro, técnica, investimento
ANOS_DA_TABELA = [1, 2, 3, 5, 10, 15, 20, 25]
LIGACAO_POR_EXTENSO = {"mono": "monofásica", "bi": "bifásica", "tri": "trifásica"}


def _linhas_de_texto(texto):
    return [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]


def _etapas(texto):
    """'Título | descrição' por linha → [{"titulo": ..., "descricao": ...}]."""
    etapas = []
    for linha in _linhas_de_texto(texto):
        titulo, _, descricao = linha.partition("|")
        etapas.append({"titulo": titulo.strip(), "descricao": descricao.strip()})
    return etapas


def _texto_fiob(tabela, ano_conexao):
    """Ex.: '75% (2027), 90% (2028) e 100% (2029 em diante)'."""
    if not tabela:
        return ""
    ultimo_ano = max(tabela)
    partes = []
    ano = ano_conexao
    while ano < ultimo_ano and tabela.get(ano, 0) < tabela[ultimo_ano]:
        partes.append(f"{tabela.get(ano, 0) * 100:.0f}% ({ano})")
        ano += 1
    partes.append(f"{tabela[ultimo_ano] * 100:.0f}% ({max(ano, ano_conexao)} em diante)")
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " e " + partes[-1]


def _paginas_da_fatura(fatura):
    """Bytes e número de páginas do PDF da fatura, ou (None, 0) se não houver arquivo."""
    if not fatura or not fatura.arquivo:
        return None, 0
    with fatura.arquivo.open("rb") as arquivo:
        conteudo = arquivo.read()
    return conteudo, contar_paginas(conteudo)


def _contexto_comum(proposta, resultado, premissas, para_pdf, n_paginas_anexo):
    """O que as páginas do PDF usam igual na proposta antiga e na v2."""
    estatico = Path(settings.BASE_DIR) / "static"
    cores = ler_cores(estatico / "css" / "tokens.css")
    emissao = proposta.emissao or timezone.localdate()
    empresa = ConfigEmpresa.obter()
    meses = [
        {"mes": mes, "geracao": g, "consumo": c, "saldo": g - c}
        for mes, g, c in zip(graficos.MESES, resultado.geracao_mensal, resultado.consumo_mensal)
    ]
    return {
        "proposta": proposta,
        "empresa": empresa,
        "cliente": proposta.cliente,
        "uc": proposta.uc,
        "fatura": proposta.fatura,
        "itens_kit": proposta.itens_kit.all(),
        "r": resultado,
        "geracao_media": resultado.geracao_anual / 12,
        "consumo_medio": resultado.consumo_anual / 12,
        "texto_fiob": _texto_fiob(
            {f.ano: float(f.percentual) / 100 for f in FioBEscalonamento.objects.all()}, premissas["ano_conexao"]
        ),
        "pct": {chave: valor * 100 for chave, valor in premissas.items() if isinstance(valor, float)},
        "premissas": premissas,
        "meses": meses,
        "fluxo_tabela": [linha for linha in resultado.fluxo if linha["ano"] in ANOS_DA_TABELA],
        "fluxo_final": resultado.fluxo[-1],
        "economia_total": sum(linha["economia"] for linha in resultado.fluxo),
        "grafico_geracao": graficos.grafico_geracao_consumo(resultado.geracao_mensal, resultado.consumo_mensal, cores),
        "grafico_fluxo": graficos.grafico_fluxo_acumulado(resultado.fluxo, cores),
        "beneficios": _linhas_de_texto(proposta.beneficios),
        "escopo": _linhas_de_texto(proposta.escopo),
        "etapas": _etapas(empresa.etapas_padrao if empresa else ""),
        "emissao": emissao,
        "validade_ate": emissao + timezone.timedelta(days=proposta.validade_dias),
        "paginas_anexo": range(1, n_paginas_anexo + 1),
        "n_paginas_anexo": n_paginas_anexo,
        "total_paginas": PAGINAS_FIXAS + n_paginas_anexo,
        "base_estatico": estatico.as_uri() if para_pdf else "/" + settings.STATIC_URL.strip("/"),
        "para_pdf": para_pdf,
    }


def _contexto_documento(proposta, para_pdf, n_paginas_anexo):
    """Contexto das páginas do PDF: os números são os mesmos da tela, vindos de montar() (D30)."""
    config = ConfigEmpresa.obter()
    m = montar(proposta, config)
    if not m.resultado:
        return None, m.mensagem or "Complete os passos da proposta antes de gerar o PDF."
    tarifa = proposta.tipo_tarifa
    fatura = proposta.fatura
    contexto = _contexto_comum(proposta, m.resultado, premissas_da_proposta(proposta, config), para_pdf, n_paginas_anexo)
    contexto |= {
        "m": m,
        "estimativa": proposta.nivel == Proposta.Nivel.ESTIMATIVA,
        "aviso_estimativa": config.aviso_estimativa,
        "municipio": m.municipio,
        "kwp": m.kwp,
        "kw_ca": m.kw_ca,
        "razao_cc_ca": m.sobrecarga,
        "qtd_modulos": m.qtd_modulos,
        "potencia_modulo": m.modulo.potencia_w,
        "media_diaria": fatura.kwh / fatura.dias_ciclo if fatura else m.consumo / 30,
        "tarifa_kwh": m.tarifa_kwh,
        "base_tarifa": f"tarifa {tarifa.get_tipo_display()} vigente da {tarifa.distribuidora}, ANEEL",
        "fiob_kwh": float(tarifa.fiob_kwh),
        "ligacao": LIGACAO_POR_EXTENSO.get(proposta.ligacao, ""),
        "disponibilidade_kwh": m.disponibilidade,
        "fonte_irradiacao": m.municipio.fonte_irradiacao,
        "financiamento": m.financiamento,
        "folga_pct": float(proposta.folga or 0) * 100,
    }
    return contexto, None


def preview(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        _, n_paginas_anexo = _paginas_da_fatura(proposta.fatura)
    except ErroAnexo as erro:
        return HttpResponse(str(erro), status=422, content_type="text/plain; charset=utf-8")
    contexto, erro = _contexto_documento(proposta, para_pdf=False, n_paginas_anexo=n_paginas_anexo)
    if erro:
        return HttpResponse(erro, status=422, content_type="text/plain; charset=utf-8")
    contexto["rascunho"] = proposta.status == Proposta.Status.RASCUNHO  # marca d'água (A09)
    return render(request, "propostas/pdf/proposta.html", contexto)


def gerar_pdf(proposta):
    """Bytes do PDF completo (proposta + Anexo I). Usado pela view e, na fatia 6, pela emissão."""
    pdf_fatura, n_paginas_anexo = _paginas_da_fatura(proposta.fatura)
    contexto, erro = _contexto_documento(proposta, para_pdf=True, n_paginas_anexo=n_paginas_anexo)
    if erro:
        raise ErroPDF(erro)
    pdf = html_para_pdf(render_to_string("propostas/pdf/proposta.html", contexto))
    if pdf_fatura:
        pdf = mesclar_anexo(pdf, pdf_fatura)
    return pdf


def pdf(request, pk):
    proposta = get_object_or_404(Proposta, pk=pk)
    if proposta.status == Proposta.Status.RASCUNHO:
        # A09: o PDF que vai para o cliente é só o da emitida; o rascunho tem a pré-visualização.
        return HttpResponse("Emita a proposta para baixar o PDF. Antes disso, use Pré-visualizar.",
                            status=409, content_type="text/plain; charset=utf-8")
    try:
        if proposta.pdf:
            with proposta.pdf.open("rb") as arquivo:  # emitida: sempre o PDF guardado na emissão (D31)
                conteudo = arquivo.read()
        else:
            conteudo = gerar_pdf(proposta)
    except (ErroPDF, ErroAnexo) as erro:
        return HttpResponse(str(erro), status=422, content_type="text/plain; charset=utf-8")
    nome = f"Proposta_{proposta.numero}_v{proposta.versao}_{proposta.cliente.nome}.pdf".replace(" ", "_")
    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="{nome}"'
    return resposta
