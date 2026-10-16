# Especificação — Fase 1: Proposta Solar

**Objetivo:** gerar, no ERP, uma proposta solar em PDF equivalente à proposta v2 do caso Alesio, sem tocar em código, a partir de: cliente + fatura + kit + premissas.

**Fora do escopo:** IA (Fase 2), funil comercial e catálogo de equipamentos (Fase 3), outras linhas de negócio, login multiusuário elaborado (usar o auth padrão do Django).

---

## 1. Models

### `core.ConfigEmpresa` (registro único)
| Campo | Tipo | Observação |
|---|---|---|
| razao_social, nome_fantasia, cnpj, endereco, telefone, email | texto | rodapé e aceite |
| logo | ImageField | |
| projetos_entregues | int | ex.: 800 → "+800 projetos entregues" |
| anos_atuacao | int | |
| texto_sobre | texto | bloco "Sobre a Optimus" |
| beneficios_padrao | texto (1 por linha) | |
| escopo_padrao | texto (1 por linha) | itens do "Escopo incluso" |
| etapas_padrao | texto (1 por linha, `Título | descrição`) | |
| validade_padrao_dias | int | 15 |
| premissas_padrao | JSON | ver §2 |

### `clientes.Cliente`
`nome`, `razao_social` (opcional), `cpf_cnpj`, `telefone`, `email`, `observacoes`, `criado_em`.

### `clientes.UnidadeConsumidora`
| Campo | Tipo |
|---|---|
| cliente | FK Cliente |
| numero_uc | texto |
| endereco, municipio, uf | texto |
| concessionaria | texto (padrão "Energisa TO") |
| classe | choices: B1 residencial, B2 rural, B3 comercial/outros |
| ligacao | choices: mono (30 kWh), bi (50 kWh), tri (100 kWh) |

### `propostas.FaturaReferencia`
| Campo | Tipo |
|---|---|
| uc | FK UnidadeConsumidora |
| competencia | data (mês/ano) |
| kwh, dias_ciclo | int |
| valor_total, tarifa_kwh, valor_distribuicao, impostos | Decimal |
| tusd_fiob_kwh | Decimal, opcional |
| composicao | JSON opcional: `[{"item": "...", "pct": 31.68}, ...]` |
| arquivo | FileField (PDF da fatura, vira anexo) |

### `propostas.IrradiacaoMunicipio`
`municipio`, `uf`, `valores` (JSON com 12 floats, kWh/m²·dia, plano horizontal), `fonte` (texto).

### `propostas.FioBEscalonamento`
`ano` (int, único), `percentual` (Decimal). Carga inicial: 2023 15 · 2024 30 · 2025 45 · 2026 60 · 2027 75 · 2028 90 · 2029 100 (premissa).

### `propostas.Proposta`
| Campo | Tipo | Observação |
|---|---|---|
| numero | texto, único | sequencial `OPT-2026-0001` |
| versao | int | 1, 2, 3… |
| origem | FK self, opcional | versão anterior |
| cliente, uc, fatura | FKs | |
| status | choices | `rascunho`, `emitida`, `aceita`, `perdida` |
| emissao | data | |
| validade_dias | int | |
| investimento | Decimal | |
| forma_pagamento | texto | |
| beneficios, escopo, texto_sobre | texto | pré-preenchidos de ConfigEmpresa, editáveis |
| premissas | JSON | snapshot no momento da emissão |
| resultados | JSON | snapshot no momento da emissão |
| pdf | FileField | gerado ao emitir |

**Regra:** só `rascunho` é editável. "Revisar" uma emitida cria nova versão em rascunho copiando tudo.

### `propostas.ItemKit`
`proposta` (FK), `tipo` (modulo, inversor, estrutura, cabeamento, outro), `descricao`, `modelo`, `quantidade`, `potencia_w` (opcional), `ordem`.

**Derivados:** `kWp = Σ(qtd × potencia_w dos módulos) / 1000`; `kW CA = Σ(qtd × potencia_w dos inversores) / 1000`.

---

## 2. Premissas (JSON)

```json
{
  "perdas": 0.18,
  "perda_clipping": 0.015,
  "ano_conexao": 2027,
  "simultaneidade": 0.50,
  "reajuste_anual": 0.04,
  "degradacao_ano1": 0.01,
  "degradacao_anual": 0.004,
  "cobrar_disponibilidade": true,
  "horizonte_anos": 25,
  "razao_cc_ca_max": 1.30
}
```

---

## 3. Motor de cálculo — `propostas/services/calculo.py`

Funções puras, sem Django. Fórmulas exatas em `docs/caso-referencia.md`.

```python
@dataclass
class EntradaCalculo:
    kwp: float
    kw_ca: float
    irradiacao: list[float]          # 12 valores
    kwh_fatura: float
    dias_ciclo: int
    tarifa: float
    fiob_kwh: float                  # já resolvido (informado ou fallback)
    disponibilidade_kwh: int         # 30/50/100
    investimento: float
    fiob_pct_por_ano: dict[int, float]
    premissas: dict

@dataclass
class ResultadoCalculo:
    geracao_mensal: list[float]
    consumo_mensal: list[float]
    geracao_anual: float
    consumo_anual: float
    cobertura: float
    produtividade: float             # kWh/kWp·mês
    custo_mensal_atual: float
    custo_mensal_com_sistema: float
    economia_mensal_ano1: float
    payback_meses: float
    rs_por_wp: float
    fluxo: list[dict]                # [{"ano": 1, "economia": ..., "acumulado": ...}, ...]
    alertas: list[str]

def fiob_fallback(valor_distribuicao, kwh, valor_total, impostos) -> float: ...
def calcular(e: EntradaCalculo) -> ResultadoCalculo: ...
```

**Alertas:**
- Razão CC/CA acima de `razao_cc_ca_max`.
- Classe B1 com cliente que possui CNPJ.
- Fio B estimado pela fatura (TUSD Fio B não informada).
- Cobertura acima de 130% (possível superdimensionamento) ou abaixo de 80%.

---

## 4. Telas

| Tela | Conteúdo |
|---|---|
| **Lista de propostas** | número/versão, cliente, kWp, investimento, status, data; filtro por status; busca por cliente |
| **Nova proposta** (passo único, seções) | Cliente (selecionar ou cadastrar inline) · UC · Fatura (upload + campos) · Kit (linhas adicionáveis via HTMX) · Premissas (pré-preenchidas) · Comercial · Textos |
| **Painel de resultados** (lateral ou abaixo do form) | KPIs + alertas, **recalculado via HTMX** a cada alteração de campo relevante (`hx-trigger="change delay:400ms"`) |
| **Preview** | o próprio HTML do PDF, em nova aba |
| **Detalhe** | dados, PDF, botões: Emitir · Revisar (nova versão) · Marcar aceita/perdida |
| **Configurações** | ConfigEmpresa, Irradiação, Fio B |

Admin do Django liberado para cadastros auxiliares (irradiação, Fio B) — sem tela própria se não for necessário.

---

## 5. PDF — estrutura de páginas

Templates em `propostas/templates/propostas/pdf/`, um por página, montados por `proposta.html`. CSS: `tokens.css` + `components.css` + `proposta.css`.

| # | Página | Conteúdo |
|---|---|---|
| 1 | **Capa** | Logo, "Proposta Comercial", "Sistema Fotovoltaico On-grid X kWp", cliente, município, UC/endereço, número, emissão, validade (X dias — até dd/mm/aaaa), "+N projetos · +N anos" |
| 2 | **Resumo** | 6 KPIs (kWp, geração média, consumo médio, economia mensal, payback, investimento); benefícios; bloco "Sobre" |
| 3 | **Análise da fatura** | 4 KPIs da fatura; tabela de dados da UC; barra de composição (se houver); nota sobre Fio B |
| 4 | **Geração × consumo** | Gráfico de barras (geração) + linha (consumo); tabela 12 meses (geração, consumo, saldo); 3 KPIs; tabela de metodologia |
| 5 | **Análise financeira** | 3 KPIs (custo atual, custo com sistema, economia); gráfico do fluxo acumulado 25 anos; tabela anos 1/2/3/5/10/15/20/25; premissas em texto pequeno |
| 6 | **Solução técnica e escopo** | Cards do kit (qtd + item + modelo); escopo incluso com checks; frase "sem custos adicionais" |
| 7 | **Investimento e aceite** | Valor em destaque + R$/Wp; etapas (linha do tempo 1–5); tabela de condições; assinaturas |
| 8+ | **Anexo I** | Fatura de referência, mesclada com pypdf, uma página por página da fatura, com cabeçalho/rodapé da proposta |

**Elementos fixos de todas as páginas (exceto capa):** faixa navy no topo, logo pequeno, "PROPOSTA Nº X · CLIENTE" à direita, rodapé com dados da empresa e `n/total`.

**Gráficos:** SVG gerado por `graficos.py`, inserido inline no template. Cores dos tokens (passadas como parâmetro).

**Referência visual:** `docs/referencia/proposta_alesio_v2.pdf` (copiar quando disponível).

---

## 6. Fatias de implementação

| # | Fatia | Pronto quando… |
|---|---|---|
| 1 | **Esqueleto:** projeto Django, apps vazios, `base.html`, CSS base com tokens e layers, fontes locais, tela inicial, `requirements.txt`, instruções de instalação no README | Abre no navegador de outro PC da rede |
| 2 | **Motor de cálculo** + `tests/test_caso_referencia.py` | Teste passa com os números de `caso-referencia.md` |
| 3 | **Models + admin + carga inicial** (ConfigEmpresa, Fio B, irradiação de São Valério e Gurupi) | Cadastro do caso Alesio pelo admin |
| 4 | **Tela de proposta** com resultados ao vivo via HTMX | Alterar a simultaneidade e ver o payback mudar sem recarregar |
| 5 | **PDF**: templates, gráficos SVG, Playwright, anexo | PDF do caso Alesio visualmente equivalente à v2 |
| 6 | **Emissão e versões**: snapshot, numeração, revisar, status | Emitir, revisar e manter as duas versões |

Cada fatia: testes passando → instruções de validação para o usuário → commit.
