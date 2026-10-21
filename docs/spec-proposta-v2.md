# Especificação — Proposta Solar v2 (redesenho da entrada)

**Objetivo:** um vendedor iniciante monta uma proposta em poucos minutos com o dado que o cliente tiver na hora (valor da conta, kWh ou fatura), e o sistema faz a parte técnica.

**Decisões:** D17 a D25 em `docs/decisoes.md`. **Protótipo aprovado:** `docs/referencia/prototipo-proposta-v2.html` (abrir no navegador).

**Continua valendo:** o motor de cálculo (`calculo.py`), o PDF da fatia 5 e o caso Alesio (`tests/test_caso_referencia.py`). Esta spec muda a entrada de dados, não o cálculo financeiro.

**Fora do escopo agora:** Grupo A, autoconsumo remoto, leitura de PDF por IA (fatia v2.8), preço por item no catálogo, andamento do financiamento, proposta por link.

---

## 1. Fluxo do vendedor

Uma tela, 4 passos, rascunho salvo a cada passo. Resumo lateral sempre visível. Chave **Modo cliente** no topo.

| Passo | O vendedor informa | O sistema faz |
|---|---|---|
| 1. Cliente | Nome*, telefone*, município* (lista), ligação, tipo de tarifa. CPF/CNPJ opcional | Valida CPF/CNPJ e telefone; acha cliente já cadastrado pelo CPF ou telefone |
| 2. Consumo | Um destes: valor da conta + iluminação pública + bandeira, **ou** kWh/mês, **ou** fatura (o vendedor digita kWh, dias do ciclo e valor total, e anexa o PDF; a leitura por IA da v2.8 só preenche esses campos). Folga (%) e perfil de uso | Converte R$ em kWh; mostra consumo estimado e com folga |
| 3. Sistema e preço | Orientação do telhado, estrutura. Ajusta quantidade de módulos, cabos, módulo/inversor pelo catálogo, custo real do kit, mão de obra, desconto | Sugere kWp, módulo (menor R$/Wp), quantidade, inversor (fase + sobrecarga ≤ 1,5), estrutura, custo do kit pela memória, mão de obra; mostra alertas |
| 4. Proposta | Escolhe o prazo de financiamento para comparar | Investimento, economia, retorno, conta hoje × com sistema × com parcela, tabela de financiamento 12–72×; gera o PDF |

\* obrigatório para a estimativa. Para a proposta **confirmada** (com fatura): CPF/CNPJ, número da UC e endereço também.

## 2. Regras de negócio

**Consumo (D19)**
- `kwh = (conta − iluminação pública) / (tarifa com tributos + adicional da bandeira)`.
- `consumo_alvo = consumo × (1 + folga)`; `geração_necessária = consumo_alvo − disponibilidade` (30/50/100 kWh).
- A economia é medida contra o consumo atual (a folga não gera economia).

**Dimensionamento (D19)**
- `kWp_necessário = geração_necessária / (irradiação média × dias × (1 − perdas) × (1 − clipping) × fator_orientação)`.
- Módulo: menor R$/Wp entre as cotações recentes do distribuidor do módulo. Quantidade = `ceil(kWp × 1000 / potência)`, editável.
- Inversor: só os da fase da ligação (mono/bi → 220 V; tri → 380 V); o menor com `kWp / kW_CA ≤ 1,5`. Se nenhum couber, mais de uma unidade.
- Estrutura: a do tipo escolhido (cerâmica, fibrocimento, metálica, laje, solo).

**Preço (D18)**
- `investimento = custo_do_kit + mão_de_obra − desconto`.
- Custo do kit: valor da cotação real (com frete). Enquanto não há cotação para esta proposta: `kWp × 1000 × R$/Wp` da última cotação do distribuidor, com aviso.
- `mão_de_obra_sugerida = max(kWp × valor_por_kWp, mínimo)`; valor por kWp R$ 500 (solo R$ 700), mínimo R$ 4.500. Editável.
- Desconto em % ou R$, só sobre a mão de obra.

**Financiamento (D22)**
- Para cada prazo (12, 24, 36, 48, 60, 72): parcela Price com a taxa do gestor; mostra o banco de menor parcela.

**Alertas**
- Sobrecarga acima de 1,5 (erro) ou abaixo de 0,8 (aviso).
- Inversor de fase diferente da ligação (erro).
- Custo do kit estimado, sem cotação desta proposta (aviso, só vendedor).
- Preço de referência com mais de 15 dias (aviso, só vendedor).
- Mão de obra com desconto abaixo do mínimo (aviso, só vendedor).
- Estimativa sem fatura (aviso).
- Alertas do motor atual (cobertura, classe B1 com CNPJ, Fio B estimado) continuam, mas só para o vendedor.

**Modo cliente (D23):** esconde custo do kit, mão de obra, desconto, R$/Wp e alertas internos.

## 3. Models

### Novos ou alterados em `core`
| Model | Campos | Observação |
|---|---|---|
| `Municipio` | `codigo_ibge` (único), `nome`, `uf`, `latitude`, `longitude`, `irradiacao` (JSON, 12 valores), `fonte_irradiacao`, `atualizado_em` | substitui `IrradiacaoMunicipio` (migrar Gurupi e São Valério) |
| `ConfigEmpresa` (+) | `mo_por_kwp`, `mo_por_kwp_solo`, `mo_minima`, `fatores_orientacao` (JSON), `perfis_simultaneidade` (JSON), `dias_preco_velho` (15), `aviso_estimativa` (texto) | premissa padrão `razao_cc_ca_max` → 1,50 |

### `clientes`
- `Cliente`: obrigatórios só `nome` e `telefone`. `cpf_cnpj` só dígitos, validado, único quando preenchido. `municipio` FK `Municipio`.
- `UnidadeConsumidora`: `municipio` FK `Municipio` no lugar de texto + `uf`. Continua exigida só na proposta confirmada.

### `propostas`
| Model | Campos principais |
|---|---|
| `TarifaVigente` | `distribuidora`, `tipo` (B1, B1_BAIXA_RENDA, B2, B3), `tusd`, `te`, `aliquota_tributos`, `tarifa_com_tributos`, `fiob_kwh` (digitado pelo gestor), `vigencia_inicio`, `fonte`, `atualizado_em` |
| `Bandeira` | `nome`, `adicional_kwh`, `vigencia` |
| `Equipamento` (catálogo) | `tipo` (modulo, inversor, estrutura, cabo, conector, outro), `distribuidor`, `codigo`, `fabricante`, `modelo`, `descricao`, `potencia_w`, `fase` (mono/tri, inversor), `tensao`, `tipo_estrutura`, `area_m2`, `ativo` |
| `Cotacao` (memória) | `distribuidor`, `numero`, `data`, `validade`, `arquivo` (PDF), `kwp`, `total_produtos`, `frete`, `total`, `rs_por_wp` (calculado), `proposta` (FK opcional) |
| `ItemCotado` | `cotacao`, `equipamento` (FK opcional), `descricao`, `codigo`, `quantidade`, `unidade` |
| `TaxaFinanciamento` | `banco`, `prazo_meses`, `taxa_mensal`, `vigente_desde` |
| `Proposta` (+) | `nivel` (estimativa/confirmada), `origem_consumo` (rs/kwh/fatura), `conta_informada`, `iluminacao_publica`, `bandeira`, `kwh_informado`, `ligacao` (mono/bi/tri; copiada da UC quando houver, define disponibilidade e inversor), `folga`, `perfil_simultaneidade`, `tipo_tarifa` (FK `TarifaVigente`), `orientacao`, `tipo_estrutura`, `custo_kit`, `cotacao` (FK opcional), `mao_de_obra`, `desconto`, `passo_atual`; `uc` e `fatura` passam a ser opcionais. Rascunho: os campos de consumo e de preço (`custo_kit`, `mao_de_obra`, `desconto`, `investimento`) são opcionais (`null=True, blank=True`) para salvar os passos 1–2 sem preço; emitir exige preço preenchido |
| `ItemKit` (+) | `equipamento` (FK opcional); cabos com `quantidade` em metros |

`Proposta.cliente` deixa de ser só `uc.cliente` (D11): na estimativa não há UC. Volta a FK `cliente`, e a UC, quando existir, precisa ser do mesmo cliente (validado no form). Ver D25.

## 4. Motor de cálculo (funções puras novas em `calculo.py`)

```python
def kwh_pela_conta(conta, iluminacao_publica, tarifa, adicional_bandeira) -> float
def kwp_necessario(consumo_kwh, folga, disponibilidade, irradiacao, perdas, clipping, fator_orientacao) -> float
def quantidade_modulos(kwp, potencia_w) -> int
def sugerir_inversor(kwp, inversores, fase, sobrecarga_max=1.5) -> tuple[dict, int]   # (inversor, quantidade)
def mao_de_obra_sugerida(kwp, solo, por_kwp, por_kwp_solo, minima) -> float
def parcela_price(valor, taxa_mensal, meses) -> float
```

A estimativa reaproveita `calcular()`: `kwh_fatura` = consumo estimado, `dias_ciclo` = 30, `tarifa` e `fiob_kwh` de `TarifaVigente`. `EntradaCalculo` ganha `fator_orientacao` (padrão 1,0), aplicado também na `geracao_mensal` de `calcular()`, para a geração da economia e do PDF bater com o dimensionamento; com fator 1 o caso Alesio não muda. Cada função com teste próprio; o caso Alesio continua passando sem mudar número.

## 5. Atualização dos dados oficiais (D21)

Comandos (também botões em Configurações), com `urllib`:

- `importar_municipios` — IBGE: municípios do TO (ou de todas as UFs) com coordenadas.
- `atualizar_irradiacao` — PVGIS por coordenada, só municípios sem dado ou com dado de mais de 1 ano.
- `atualizar_tarifas` — ANEEL, filtrado por Energisa TO e Grupo B, vigência mais recente.

Cada execução grava fonte e data. Falha de rede não apaga dado antigo; a tela mostra a data do último sucesso.

## 6. Telas

| Tela | Conteúdo |
|---|---|
| Nova proposta | 4 passos (seção 1), HTMX, resumo lateral, modo cliente. Layout que funciona no celular |
| Lista de propostas | número/versão, cliente, nível (estimativa/confirmada), kWp, investimento, status; busca por nome ou telefone |
| Clientes | lista, busca, ficha com UCs e propostas |
| Catálogo | equipamentos por tipo e distribuidor; cotações com R$/Wp e idade |
| Configurações | empresa e textos; premissas e perfis; mão de obra; tarifas e Fio B; bandeiras; taxas de financiamento; botões de atualização |

Menu sem links mortos. O admin do Django fica só para manutenção.

## 7. PDF

Mesma estrutura da fatia 5, com:
- faixa com o aviso de estimativa (capa e página de resumo) quando `nivel = estimativa`;
- página de investimento sem custo de kit nem mão de obra separados; tabela de financiamento 12–72× com a parcela do melhor banco;
- sem Anexo I quando não há fatura.

## 8. Fatias de implementação

| # | Fatia | Pronto quando… |
|---|---|---|
| v2.1 | **Validações e clientes:** `core/validacoes.py`, `Municipio` (carga IBGE do TO), cadastro e lista de clientes, menu corrigido, layout base no celular | CPF "123abc" é recusado; cliente cadastrado em uma tela; menu sem link morto |
| v2.2 | **Configurações e dados oficiais:** `TarifaVigente`, `Bandeira`, `TaxaFinanciamento`, campos novos de `ConfigEmpresa`, comandos de atualização, tela de Configurações | Tarifas da ANEEL e irradiação do PVGIS gravadas, com fonte e data |
| v2.3 | **Motor:** funções puras da seção 4 + testes | Testes novos e caso Alesio passando |
| v2.4 | **Catálogo e memória de cotações:** `Equipamento`, `Cotacao`, `ItemCotado`, telas, carga inicial com as cotações de 21/10 | R$/Wp do kit aparece com a idade |
| v2.5 | **Nova proposta em 4 passos** (seção 1), rascunho automático, modo cliente | Os 3 cenários da auditoria (com fatura digitada, R$ 500, 800 kWh) terminam em menos de 3 minutos |
| v2.6 | **PDF da v2** (seção 7) | PDF de estimativa com aviso e tabela de financiamento |
| v2.7 | **Emissão e versões** (antiga fatia 6) | Emitir, revisar, estimativa → confirmada, aceita/perdida/vencida |
| v2.8 | **IA:** leitura do PDF da cotação e da fatura (chave da API da Anthropic) | Cotação Belenus e Intelbras lidas e conferidas |

Cada fatia: testes passando → instruções de teste no navegador → commit → PR.

## 9. Dados reais de partida (cotações de 21/10/2026)

| Distribuidor | Documento | Equipamentos | kWp | Total | R$/Wp |
|---|---|---|---|---|---|
| Belenus | WEB-007005988 | 21 × Huansheng HSM-ND66-GR610-Y 610 W; 1 × Deye SUN-10K-G02P1-EU-CM2-P 10 kW mono 220 V 2 MPPT; estrutura de solo mesa 8 módulos isopleta 45 m/s; cabos 4 mm 100 m preto + 100 m vermelho; 10 pares de conectores | 12,81 | R$ 27.666,44 (produtos R$ 25.683,58 + frete R$ 1.982,86) | 2,16 |
| Intelbras | PROJ26101627017 | 26 × Intelbras EMSC-620B 620 W; 1 × Intelbras IONS-12K T2 AFCI tri 380 V; 5 × mesa modular Dynamo 6 módulos 45 m/s + 1 finalizador de solo; cabos 4 mm 100 m + 100 m; 3 pares MC4 | 16,12 | Só o kit: R$ 34.874,60 (a plataforma mostra R$ 46.158,60, que inclui a mão de obra da Optimus: 16,12 × R$ 700 = R$ 11.284,00). Na carga inicial, `total` = só o kit | 2,16 |
