# Registro de decisões

Formato: data · decisão · motivo · alternativas descartadas.

---

## D01 · 2026-10-15 · Começar do zero
- **Motivo:** tentativas anteriores falharam; nenhum código legado a respeitar.
- **Consequência:** o módulo de Proposta define o desenho inicial do ERP. Clientes e UCs nascem junto, no tamanho mínimo necessário.

## D02 · 2026-10-15 · Primeiro módulo: Proposta Solar
- **Motivo:** dor real e imediata. Uma proposta gerada manualmente com IA (caso Alesio, 55,35 kWp) foi aprovada e serve de modelo por engenharia reversa.
- **Escopo:** somente energia solar. Outras linhas de negócio fora do radar.
- **Desenho:** `Proposta` (base genérica) + `DimensionamentoSolar` (1:1). Mantém porta aberta sem custo extra.

## D03 · 2026-10-15 · CSS dedicado, sem Tailwind
- **Motivo:** templates limpos, sem build, roda offline, CSS de impressão natural, aderente a "No Magic".
- **Descartado:** Tailwind (verboso, build step), híbrido Tailwind + `@apply` (pior dos dois), Bootstrap.

## D04 · 2026-10-15 · PDF via Playwright (Chromium headless)
- **Motivo:** mesmo motor do navegador → preview = PDF. Instala por `pip` no Windows.
- **Descartado:** WeasyPrint (GTK/Pango no Windows, suporte CSS parcial), ReportLab (layout por coordenadas, inviável de manter), xhtml2pdf (CSS limitado).
- **Cuidados:** `print_background=True`; fontes locais; validar em *Emulate CSS media: print*.

## D05 · 2026-10-15 · Execução em PC Windows, SQLite, waitress
- **Motivo:** não há servidor Linux. Carga de 2–5 usuários é mínima.
- **Risco aceito:** PC desligado = sistema fora. Futuro: mini PC dedicado.
- **Backup:** cópia do arquivo `db.sqlite3` + pasta `media/`.

## D06 · 2026-10-15 · Kit cadastrado manualmente na Fase 1
- **Motivo:** dois distribuidores (Belenus e Intelbras) com formatos diferentes. Parser por distribuidor é frágil.
- **Fase 2:** upload do PDF do kit/fatura com extração via API Claude para formato único.

## D07 · 2026-10-15 · Proposta emitida é imutável
- Cada proposta guarda *snapshot* de premissas e resultados (JSON).
- Qualquer alteração gera **nova versão** (v1, v2…), preservando a anterior.

## D08 · 2026-10-15 · Correções no cálculo em relação ao script original (`gerar2.py`)
| # | Original | Corrigido |
|---|---|---|
| 1 | Fio B escalonado por ano do sistema (lista fixa) | Escalonado por **ano civil** (tabela `FioBEscalonamento`), a partir do ano de conexão — Lei 14.300/2022, art. 27 |
| 2 | Fio B = serviço de distribuição inteiro / kWh | Campo **TUSD Fio B** informado; estimativa pela fatura apenas como fallback (conservadora) |
| 3 | Custo de disponibilidade sempre descontado | Parâmetro `cobrar_disponibilidade` (padrão: sim, conservador) — **regra a validar** |
| 4 | Clipping 1,5% fixo | Parâmetro `perda_clipping` por proposta |
| 5 | Degradação linear 0,4% a.a. | Separada: `degradacao_ano1` + `degradacao_anual` |
| 6 | Classe tarifária ignorada | Alerta quando a classe da UC é incompatível (ex.: B1 residencial em cliente comercial) |
| 7 | Irradiação digitada no código | Tabela `IrradiacaoMunicipio` com fonte registrada |

## Pendências de validação
- [ ] Regra de custo de disponibilidade para GD após a Lei 14.300 (item 3 de D08).
- [ ] Valor da TUSD Fio B vigente na Energisa TO por subgrupo (B1/B2/B3).
- [ ] Irradiação mensal por município: substituir estimativas regionais por CRESESB/SunData.
- [ ] Percentual de Fio B a partir de 2029 (definição ANEEL). Premissa atual: 100%.
