# meu_erp — Regras do projeto

ERP interno da **Optimus Energia Solar** (Gurupi-TO). Uso interno, 2–5 usuários, rede local.
Fase atual: **Proposta Solar v2**, redesenho da entrada de dados (ver `docs/spec-proposta-v2.md`, D17–D25). A `docs/spec-fase1.md` continua valendo para o motor de cálculo e o PDF.
**Agora:** correções da revisão de 22/10/2026 e do teste humano de 24/10/2026 (`docs/relatorio-teste-humano-2026-10-24.md`), em rodadas, seguindo `docs/plano-correcoes.md` (D33–D47).
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
│   │   ├── calculo.py   # FUNÇÕES PURAS — sem import de Django (inclui dimensionamento e parcela)
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
├── core/validacoes.py   # CPF/CNPJ, telefone, valores BR — FUNÇÕES PURAS
├── core/dados/          # municipios_to.csv (carga IBGE, D26)
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

## Regras de negócio da proposta solar (resumo; detalhes em `docs/spec-proposta-v2.md`)

O usuário típico é um **vendedor iniciante**, e o cliente muitas vezes **não tem a fatura** na hora. Toda tela nova deve funcionar para esse caso.

- **Fluxo:** 4 passos numa tela (cliente → consumo → sistema e preço → proposta), rascunho salvo a cada passo. Protótipo aprovado: `docs/referencia/prototipo-proposta-v2.html`.
- **Estimativa × confirmada:** sem fatura é estimativa, com aviso fixo no PDF. Com fatura vira nova versão confirmada, mesmo número.
- **Dados mínimos da estimativa:** nome, telefone, município. UC e endereço só na confirmada; CPF/CNPJ só é exigido para emitir a confirmada (D38).
- **Consumo:** por valor da conta (descontando iluminação pública e bandeira), por kWh ou por fatura. Tipo de tarifa do Grupo B escolhido pelo vendedor; valores vêm do banco (ANEEL).
- **Dimensionamento:** sistema sugere kWp, módulo de menor R$/Wp, quantidade (editável) e inversor da fase da ligação com sobrecarga ≤ 1,5.
- **Preço:** kit (faturamento direto do distribuidor, com frete, sem margem) + mão de obra − desconto. Mão de obra sugerida `max(kWp × R$ 500, R$ 4.500)`, solo R$ 700/kWp. Desconto só na mão de obra. Sem imposto na proposta.
- **Kit:** montado pelo catálogo Belenus com preço por item + 7% de frete (D34, regras em `docs/dimensionamento-estruturas.md`); o vendedor troca itens e quantidades. Cotação vinculada substitui o catálogo (D35). Nenhum distribuidor tem API.
- **Financiamento:** taxas por banco e prazo (12 a 72×) mantidas pelo gestor; mostrar a parcela do melhor banco em cada prazo, como aproximada.
- **Quem altera o quê:** premissas técnicas, perfis de simultaneidade, mão de obra, tarifas, Fio B e taxas são do gestor (Configurações). O vendedor escolhe perfil, folga, orientação, estrutura, quantidades, custo do kit, mão de obra e desconto.
- **Modo cliente:** esconde custo do kit, mão de obra, desconto, R$/Wp e alertas internos, sem enviar ao navegador (`{% if not modo_cliente %}`, A29).
- **Dados oficiais** (IBGE, PVGIS, ANEEL) são baixados para o banco com fonte e data; a proposta nunca consulta API na hora. Exceção: no cadastro do cliente, o navegador busca CEP (ViaCEP) e CNPJ (BrasilAPI) (D42).
- **Listas:** busca e filtros atualizam a lista na hora, sem botão (D40: `hx-get` + `hx-select="#resultado"` no próprio formulário).
- **Validação (D41):** toda entrada com limite e limpeza (`higienizar` no `__init__` do formulário); CPF/CNPJ por dígito verificador, telefone com DDD, valores em reais em campo de texto com máscara e conversão no servidor. Rótulos com acento, na língua do vendedor.

## Fluxo de trabalho

1. Ler `docs/plano-correcoes.md` e implementar **uma rodada por vez**, na ordem, marcando os itens feitos. A spec v2 continua valendo onde D33–D35 não mudaram.
2. Ao terminar a fatia: rodar testes, mostrar como validar no navegador, commit.
3. Commits em português, mensagem curta: `fatia 2: motor de cálculo + caso de referência`.
4. Decisão nova ou mudança de rumo → registrar em `docs/decisoes.md` **antes** de codar.
5. Na dúvida sobre regra de negócio, **perguntar**, não inventar.
6. O usuário não programa: explicar o que foi feito e como testar em linguagem direta.
7. Antes de entregar tela nova, percorrer o fluxo no navegador como um vendedor iniciante (inclusive no celular) e com dados malformados.
