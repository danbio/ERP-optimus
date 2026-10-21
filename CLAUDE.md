# meu_erp — Regras do projeto

ERP interno da **Optimus Energia Solar** (Gurupi-TO). Uso interno, 2–5 usuários, rede local.
Fase atual: **módulo de Proposta Solar** (ver `docs/spec-fase1.md`).
Módulo paralelo: **Orçamentos da revenda Intelbras** (ver `docs/spec-orcamentos.md`, D12–D15).

## Princípio número 1

**Simples é melhor que complicado. SEMPRE.**
- Sem abstração "para o futuro". Resolva o problema de hoje.
- Sem dependência nova sem justificativa registrada em `docs/decisoes.md`.
- Código legível por quem não programa todo dia. Nomes em português no domínio (`Proposta`, `geracao_mensal`).
- *No Magic*: nada de metaprogramação, signals escondidos ou mixins encadeados. Fluxo explícito.

## Stack (fechada — não trocar sem decisão registrada)

| Camada | Escolha |
|---|---|
| Backend | Python 3.12+ / Django 5.x |
| Banco | SQLite |
| Interação | HTMX (sem framework JS; JS puro) |
| Estilo | **CSS dedicado, sem build. NÃO usar Tailwind, Bootstrap ou qualquer framework CSS** |
| PDF | Playwright (Chromium headless) → `page.pdf()` |
| Gráficos | matplotlib → SVG |
| Anexos PDF | pypdf |
| Servidor | `waitress` em PC Windows na rede local |
| Testes | pytest + pytest-django |

## Ambiente

- Desenvolvimento e produção em **Windows**. Usar `pathlib`, nunca caminhos com `/` ou `\` fixos.
- Comandos documentados para PowerShell.
- Rodar: `python manage.py runserver 0.0.0.0:8000` (dev) / `waitress-serve --port=8000 config.wsgi:application` (produção).

## Estrutura

```
meu_erp/
├── config/              # settings, urls, wsgi
├── core/                # ConfigEmpresa, base.html, componentes comuns
├── clientes/            # Cliente, UnidadeConsumidora
├── propostas/
│   ├── models.py
│   ├── services/
│   │   ├── calculo.py   # FUNÇÕES PURAS — sem import de Django
│   │   ├── graficos.py  # matplotlib → SVG (string)
│   │   └── pdf.py       # Playwright + mescla de anexo
│   ├── views.py
│   └── templates/propostas/
│       ├── ...          # telas
│       └── pdf/         # 1 template por página do PDF
├── orcamentos/          # revenda Intelbras: catálogo, orçamento, PDF
│   ├── services/
│   │   ├── tabela_intelbras.py  # leitura do .xlsb — FUNÇÃO PURA
│   │   └── calculo.py           # preço/markup/totais — FUNÇÕES PURAS
│   ├── importacao.py    # grava a leitura no banco
│   └── templates/orcamentos/pdf/
├── core/pdf.py          # html_para_pdf() — Playwright, usado por todos os PDFs
├── static/css/          # ver regras de CSS
├── static/fonts/        # Poppins local
├── tests/
└── docs/
```

## Regras de CSS (obrigatórias)

```
static/css/
├── tokens.css      # ÚNICO lugar com valores literais de cor, fonte, espaçamento
├── base.css        # reset, tipografia, layout geral
├── components.css  # .btn, .card, .kpi, .tabela, .campo, .badge
├── app.css         # telas do ERP (sidebar, topbar, listas)
└── proposta.css    # SÓ o PDF: @page A4, quebras, capa
```

1. **Cores e tamanhos só via variáveis.** Nenhum `#123643` fora de `tokens.css`.
2. **`@layer`** declarado no topo de `tokens.css`: `@layer tokens, base, components, app, proposta;`. Cada arquivo dentro da sua camada. **Proibido `!important`.**
3. **Nomes por componente**, variantes por modificador: `.kpi`, `.kpi--escuro`.
4. **Nesting nativo** permitido. Atenção: `&--escuro` NÃO funciona em CSS nativo; usar `&.kpi--escuro`.
5. `proposta.css` é carregado **só** nos templates de PDF.
6. Nenhum `style=""` inline, exceto valores dinâmicos calculados (ex.: largura de barra de gráfico).

### Tokens do brandbook Optimus

```css
--navy: #123643;  --gold: #D4A429;  --ink: #1E2A30;
--muted: #6B7A80; --light: #F3F5F6; --line: #DCE2E4;
--soft: #C9D3D6;  --ok: #2E7D4F;    --erro: #B4442F;
fonte: Poppins (Regular, Medium, Bold) — arquivos locais em static/fonts/
```

## Regras de cálculo

- Toda a lógica de dimensionamento e financeiro fica em `propostas/services/calculo.py`, **funções puras** com dataclasses de entrada e saída.
- **Nenhuma constante de negócio no código.** Premissas vêm de `ConfigEmpresa` / tabelas, e cada proposta guarda um *snapshot* delas.
- Dinheiro: `Decimal` nos models; `float` permitido dentro do motor de cálculo, arredondando só na saída.
- O teste `tests/test_caso_referencia.py` (caso Alesio, ver `docs/caso-referencia.md`) **deve passar sempre**. Se um número mudar, é bug até prova em contrário.

## Fluxo de trabalho

1. Ler `docs/spec-fase1.md` e implementar **uma fatia por vez**, na ordem.
2. Ao terminar a fatia: rodar testes, mostrar como validar no navegador, commit.
3. Commits em português, mensagem curta: `fatia 2: motor de cálculo + caso de referência`.
4. Decisão nova ou mudança de rumo → registrar em `docs/decisoes.md` **antes** de codar.
5. Na dúvida sobre regra de negócio, **perguntar**, não inventar.
6. O usuário não programa: explicar o que foi feito e como testar em linguagem direta.
