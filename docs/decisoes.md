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

## D09 · 2026-10-15 · Campos extras em `EntradaCalculo` para os alertas de negócio
- **Motivo:** a spec da fatia 1 lista, na mesma seção do motor de cálculo, quatro alertas (razão CC/CA, classe B1 com cliente CNPJ, Fio B estimado, cobertura fora da faixa) — mas o `EntradaCalculo` original só trazia dados para calcular os dois primeiros (CC/CA e cobertura). Classe tarifária e "Fio B foi informado ou estimado" são informações da UC/fatura, inexistentes como models até a fatia 3.
- **Decisão:** acrescentar três campos opcionais, com valor padrão, ao `EntradaCalculo`: `classe` (str), `cliente_pessoa_juridica` (bool), `fiob_informado` (bool). Assim `calcular()` continua uma função pura e autossuficiente, gerando os quatro alertas sozinha, sem o motor de cálculo depender de Django/models.
- **Consequência:** quando a fatia 3 criar `Cliente`/`UnidadeConsumidora`, a view só precisa repassar esses três valores ao montar o `EntradaCalculo`; nenhuma mudança de assinatura é necessária.
- **Alternativa descartada:** mover os alertas de classe/Fio B para fora de `calculo.py` (camada de view) — rejeitada porque fragmentaria a lista de alertas em dois lugares diferentes, dificultando manter `tests/test_caso_referencia.py` como fonte única de verdade dos alertas esperados.

## D10 · 2026-10-15 · Dependência `Pillow`
- **Motivo:** `core.ConfigEmpresa.logo` é um `ImageField` (spec-fase1.md §1), e o `ImageField` do Django exige a biblioteca Pillow instalada — sem ela, o `migrate`/`check` falha.
- **Decisão:** adicionar `Pillow` ao `requirements.txt` a partir da fatia 3.
- **Alternativa descartada:** trocar `logo` por `FileField` para evitar a dependência — rejeitada por fugir da spec sem necessidade; Pillow é leve e amplamente usada em projetos Django.

## D11 · 2026-10-15 · `Proposta` não tem FK própria para `Cliente`
- **Motivo:** `Proposta.cliente` e `Proposta.uc` seriam duas fontes para o mesmo dado (o cliente é sempre o dono da UC escolhida) — risco de inconsistência se alguém trocar a UC sem trocar o cliente, ou vice-versa.
- **Decisão:** remover o campo `cliente` do model `Proposta`. `Proposta.cliente` agora é uma `@property` que retorna `self.uc.cliente`. A tela de nova proposta só pede a UC; o cliente aparece derivado, não é escolhido separadamente.
- **Consequência:** `list_display`/`search_fields` no admin usam `uc__cliente__...` ou o método `cliente()`, já que não é mais um campo de banco filtrável diretamente por `cliente__`.

## D12 · 2026-10-21 · Novo módulo: Orçamentos da revenda Intelbras
- **Motivo:** a Optimus é revenda credenciada Intelbras (PCI). Orçamentos de CFTV, controle de acesso, redes, nobreaks etc. são feitos à mão hoje. Muda o escopo de D02 ("somente solar"): o solar continua sendo a Fase 1, e este é um módulo paralelo e independente.
- **Desenho:** app `orcamentos`, separado de `propostas`. Reaproveita `clientes.Cliente` (sem UC), `core.ConfigEmpresa`, `base.html` e o CSS. Spec em `docs/spec-orcamentos.md`.
- **Fora:** Solar ON GRID, que pelo Manual PCI é orçado obrigatoriamente na Plataforma Solar Intelbras.

## D13 · 2026-10-21 · Catálogo importado da tabela oficial Intelbras (.xlsb)
- **Motivo:** a tabela da Intelbras sai nos dias 1 e 15 de cada mês, em .xlsb (cerca de 70 mil linhas = 2,6 mil produtos × 27 UFs). Cadastrar à mão é inviável.
- **Decisão:** usar o importador `orcamentos/services/tabela_intelbras.py` (função pura) com a dependência **`pyxlsb`**, que lê .xlsb sem Excel. O importador filtra pela **UF de destino** (`ParametrosOrcamento.uf_destino`, padrão TO). Os preços são nacionais: só o ICMS e a origem variam por UF.
- **Custo = PSD** da tabela (definido pelo usuário). Os itens com PSD zerado (licenças, serviços em nuvem, "S/Controle de Venda") entram sem custo e o orçamento alerta.
- Produto que sai da tabela ou aparece na aba *Encerramentos* fica `ativo=False`, com o substituto anotado. Nada é apagado.
- **Descartado:** openpyxl (não lê .xlsb), conversão manual para .xlsx (passo extra todo mês), pandas (dependência pesada sem necessidade).

## D14 · 2026-10-21 · Formação de preço: markup sobre o custo, PSCF como referência
- `preço = custo × (1 + markup)`. Prioridade do markup: valor editado no item → `MarkupSegmento` → `ParametrosOrcamento.markup_padrao` (30%, que é aproximadamente o PSCF: na tabela de out/2026 a mediana de PSCF/PSD é 1,300).
- O PSCF fica guardado no item e gera um **alerta informativo** quando o preço fica acima dele. O Manual PCI proíbe vender abaixo do PSCF **em anúncios online**, não em proposta privada, então ficar abaixo do PSCF não bloqueia nada.
- Cada item guarda um *snapshot* (código, descrição, custo, preço, PSCF): o orçamento não muda se a tabela mudar. O orçamento emitido é imutável e "Revisar" cria uma nova versão (mesma regra de D07).
- Materiais de outras marcas e serviços de instalação entram como itens próprios (`ItemProprio`) ou avulsos.
- Margem mostrada = **margem bruta antes de impostos** (venda − custo). Impostos da Optimus ficam fora do MVP.

## D15 · 2026-10-21 · Playwright entra agora, em `core/pdf.py`
- **Motivo:** o PDF do orçamento precisa do mesmo motor previsto em D04. Esta é a primeira fatia a gerar PDF de verdade.
- **Decisão:** a função genérica `html_para_pdf()` fica em `core/pdf.py`, porque a fatia 5 da proposta solar vai usar a mesma. Nenhuma outra abstração.
- **Instalação no Windows:** `pip install playwright` + `python -m playwright install chromium` (uma vez).
- `MEDIA_ROOT` foi adicionado ao `settings.py`, porque já havia FileFields sem pasta definida.

## D16 · 2026-10-21 · PDF da proposta: páginas A4 fixas, gráficos matplotlib, anexo com pypdf
- **Páginas fixas:** cada página do PDF é um `<section class="pagina">` de 210 × 297 mm com cabeçalho e rodapé próprios, e o número `n/total` vem do template. Motivo: a capa não tem cabeçalho nem rodapé, o que o rodapé do Chromium (usado no orçamento) não permite, e o preview na tela fica idêntico ao PDF. Risco aceito: texto longo demais é cortado no fim da página em vez de passar para a seguinte; os textos da proposta são curtos.
- **Gráficos:** `matplotlib` gera SVG (texto como texto, fonte Poppins da página). As cores são lidas de `tokens.css`, que continua o único lugar com cores literais.
- **Anexo I:** o HTML já traz uma página "moldura" por página da fatura; depois do Playwright, o `pypdf` carimba cada página da fatura reduzida dentro da moldura. A numeração sai certa numa única renderização.
- **Textos padrão:** migration `core/0003` preenche benefícios, escopo, etapas e "Sobre" da `ConfigEmpresa` com os textos da proposta Alesio v2, só onde estiverem vazios. Editáveis no admin.
- **Nesta fatia o PDF é gerado sob demanda e não é guardado.** Gravar o PDF, congelar o snapshot e numerar versões é a fatia 6.

## Pendências de validação
- [ ] Regra de custo de disponibilidade para GD após a Lei 14.300 (item 3 de D08).
- [ ] Valor da TUSD Fio B vigente na Energisa TO por subgrupo (B1/B2/B3).
- [ ] Irradiação mensal por município: substituir estimativas regionais por CRESESB/SunData.
- [ ] Percentual de Fio B a partir de 2029 (definição ANEEL). Premissa atual: 100%.
- [ ] Orçamentos: confirmar se o PSD da tabela corresponde ao preço real de compra no distribuidor (D13).
- [ ] Orçamentos: incluir impostos sobre a venda (regime da Optimus) no cálculo de margem (D14).
- [ ] Orçamentos: obter o selo oficial "Parceiro Credenciado Intelbras" (Portal Sou Parceiro) para a capa do PDF, seguindo o manual de diretrizes da marca.
