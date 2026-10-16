# Caso de referência — Alesio Matte (55,35 kWp)

Proposta real aprovada em 15/10/2026. Vira o teste `tests/test_caso_referencia.py`.
Todos os resultados abaixo devem ser reproduzidos com **tolerância de ±0,5%** (valores em R$ e kWh) e **±0,2 mês** (payback).

---

## Entradas

### Cliente e UC
| Campo | Valor |
|---|---|
| Cliente | Alesio Matte — Distribuidora Stilus |
| Município | São Valério da Natividade – TO |
| UC | 20.008.015-05 |
| Endereço | Av. Tocantins, 1255, Qd. 40, Lt. 16 – Centro |
| Classe na fatura | B1 Residencial (⚠️ deve disparar alerta: cliente comercial) |
| Ligação | Trifásica → disponibilidade 100 kWh |

### Fatura de referência (set/2026)
| Campo | Valor |
|---|---|
| Consumo faturado | 5.560 kWh |
| Dias do ciclo | 28 |
| Valor total | R$ 7.762,74 |
| Tarifa com tributos | R$ 1,372680/kWh |
| Serviço de distribuição (sem tributos) | R$ 2.458,63 |
| Impostos | R$ 2.128,86 |
| TUSD Fio B informada | *vazio* → usar fallback |

### Kit
| Qtd | Item | Potência |
|---|---|---|
| 90 | Módulo Huansheng HSM-ND66-GR615-Y (N-type bifacial) | 615 W |
| 2 | Inversor Deye SUN-20K-G05 (trifásico 380 V) | 20.000 W CA |
| 1 | Estrutura fibrocimento/madeira (alumínio + inox) | — |
| 1 | Cabos solares 6 mm² + conectores | — |

### Irradiação (plano horizontal, kWh/m²·dia) — estimativa regional
`[4.95, 5.05, 4.95, 5.15, 5.35, 5.40, 5.65, 6.05, 5.90, 5.45, 5.10, 4.85]`

### Premissas
| Premissa | Valor |
|---|---|
| Perdas do sistema | 18% |
| Perda por clipping | 1,5% |
| Ano de conexão | 2027 |
| Fio B escalonado | 2027: 75% · 2028: 90% · 2029+: 100% |
| Simultaneidade (autoconsumo instantâneo) | 50% |
| Reajuste tarifário | 4% a.a. |
| Degradação 1º ano / anual | 1,0% / 0,4% |
| Cobrar disponibilidade | Sim |
| Dias por mês | calendário de 2027 |

### Comercial
| Campo | Valor |
|---|---|
| Investimento | R$ 92.502,81 |
| Validade | 15 dias |
| Pagamento | A combinar |

---

## Fórmulas

- **Fio B fallback (R$/kWh c/ tributos)** = `distribuicao / kwh × valor_total / (valor_total − impostos)`
- **Consumo mensal** = `kwh_fatura / dias_ciclo × dias_do_mes`
- **Geração mensal** = `kWp × irradiacao × dias_do_mes × (1 − perdas) × (1 − clipping)`
- **Ano y (0-based)**:
  - `tarifa_y = tarifa × (1 + reajuste)^y` · `fiob_y = fiob × (1 + reajuste)^y`
  - `geracao_y = geracao_anual × (1 − degr_ano1) × (1 − degr_anual)^y`
  - `compensado = min(geracao_y, consumo_anual)`
  - `economia_y = compensado × tarifa_y − disponibilidade × 12 × tarifa_y − pct_fiob(ano_civil) × fiob_y × compensado × (1 − simultaneidade)`
- **Economia mensal (ano 1)** = `economia_0 / 12`
- **Payback (meses)** = `investimento / economia_mensal_ano1`
- **Custo atual** = `consumo_anual × tarifa / 12` · **Custo com sistema** = `custo_atual − economia_mensal_ano1`

---

## Resultados esperados

| Resultado | Valor |
|---|---|
| Fio B fallback | R$ 0,6093/kWh |
| Geração anual | 86.848 kWh |
| Geração média mensal | 7.237 kWh |
| Consumo anual | 72.479 kWh |
| Consumo médio mensal | 6.040 kWh |
| Cobertura | 119,8% |
| Produtividade | 130,8 kWh/kWp·mês |
| Custo mensal atual | R$ 8.290,82 |
| Custo mensal com sistema (ano 1) | R$ 1.517,29 |
| Economia mensal (ano 1) | R$ 6.773,54 |
| Payback | 13,7 meses |
| R$/Wp | R$ 1,67 |
| Economia acumulada 25 anos | R$ 3.163.008,08 |
| Saldo líquido 25 anos | R$ 3.070.505,27 |

### Geração e consumo mensais (kWh)
| | Jan | Fev | Mar | Abr | Mai | Jun | Jul | Ago | Set | Out | Nov | Dez |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Geração | 6.860 | 6.321 | 6.860 | 6.907 | 7.415 | 7.242 | 7.830 | 8.385 | 7.913 | 7.553 | 6.840 | 6.722 |
| Consumo | 6.156 | 5.560 | 6.156 | 5.957 | 6.156 | 5.957 | 6.156 | 6.156 | 5.957 | 6.156 | 5.957 | 6.156 |

### Fluxo de caixa (R$)
| Ano | Economia no ano | Saldo acumulado |
|---|---|---|
| 1 | 81.282,43 | −11.220,38 |
| 2 | 81.089,19 | 69.868,81 |
| 3 | 81.944,55 | 151.813,36 |
| 5 | 88.631,23 | 325.666,92 |
| 10 | 107.833,44 | 824.924,45 |
| 15 | 131.195,87 | 1.432.347,57 |
| 20 | 159.619,83 | 2.171.370,67 |
| 25 | 194.201,93 | 3.070.505,27 |

### Alertas esperados
- Classe B1 residencial em cliente comercial.
- Razão CC/CA = 55,35 / 40 = **1,38**: alertar se acima do limite cadastrado do inversor.
