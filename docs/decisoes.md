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

## D17 · 2026-10-21 · Redesenho da entrada da proposta: estimativa sem fatura, em 4 passos
- **Motivo:** auditoria de usabilidade de 21/10 ([relatório](https://claude.ai/artifact/FDuVTqm3hdxy8ozVCPwaQB)): um vendedor iniciante não consegue terminar uma proposta. A fatura era obrigatória (7 campos técnicos), o município era texto livre, o sistema não dimensionava e o cadastro ficava espalhado em 4 telas. Os casos "minha conta vem R$ 500" e "quero gerar 800 kWh" eram impossíveis.
- **Decisão:** a proposta nasce em 4 passos numa tela só (cliente → consumo → sistema e preço → proposta), salvando o rascunho a cada passo. A fatura deixa de ser obrigatória e vira refinamento. Spec em `docs/spec-proposta-v2.md`; protótipo aprovado em `docs/referencia/prototipo-proposta-v2.html`.
- **Consequência:** a fatia 6 e o resto do plano ficaram congelados até o fluxo novo funcionar. O motor de cálculo, o PDF e o caso Alesio continuam valendo. As telas da `spec-fase1.md` §4 são substituídas pela spec v2.

## D18 · 2026-10-21 · Preço = kit + mão de obra − desconto
- O kit é vendido por **faturamento direto** do distribuidor ao cliente (isento de imposto; se a Optimus emitisse a nota, pagaria 4% no Simples). Não há margem sobre o kit.
- **Mão de obra sugerida** = `max(kWp × R$ 500, R$ 4.500)`; estrutura de solo: R$ 700/kWp. Valores no `ConfigEmpresa`, editáveis pelo gestor; o vendedor edita livremente na proposta.
- **Desconto** só sobre a mão de obra. A proposta não mostra imposto.
- O custo do kit inclui o frete da cotação.

## D19 · 2026-10-21 · Dimensionamento automático
- **Consumo** a partir de um destes: valor da conta (R$), kWh/mês ou fatura. Conversão R$ → kWh: `(conta − iluminação pública) / (tarifa com tributos do tipo escolhido + adicional da bandeira)`.
- **Tipo de tarifa:** todo o Grupo B (B1 residencial, B1 baixa renda, B2 rural, B3 demais), escolhido pelo vendedor. Grupo A fica para o futuro.
- **Folga** para consumo futuro, em %, editável. **Simultaneidade** escolhida pelo vendedor por perfil (os percentuais de cada perfil são do gestor). As demais premissas técnicas só o gestor altera.
- **Geração necessária** = `consumo × (1 + folga) − disponibilidade`. **kWp** = geração necessária / (irradiação × dias × (1 − perdas) × (1 − clipping) × fator de orientação). Orientação: 4 opções (norte; nordeste/noroeste; leste/oeste; sul), fatores no `ConfigEmpresa`.
- **Módulo:** o de menor R$/Wp nas cotações recentes (D20). Quantidade de módulos sugerida e editável.
- **Inversor:** filtrado pela ligação (mono e bifásica: 220 V; trifásica: 380 V) e escolhido com sobrecarga CC/CA ≤ 1,5. A premissa padrão `razao_cc_ca_max` passa de 1,30 para 1,50 (o caso Alesio guarda as suas próprias premissas e não muda). Tensão e MPPT ficam para o projeto elétrico.
- A economia é medida contra a conta de hoje: a geração compensada é limitada ao consumo atual, não ao consumo com folga.

## D20 · 2026-10-21 · Catálogo de referência + memória de cotações
- Nenhum distribuidor (Belenus, Intelbras) tem API. As cotações saem em PDF e trazem **só o preço total**, sem preço por item.
- **Catálogo:** módulos, inversores, estruturas (por tipo de telhado) e cabos, com dados técnicos e distribuidor. Mantido pelo gestor. A tabela Intelbras dos Orçamentos traz os equipamentos solares, mas sem preço.
- **Memória de cotações:** cada cotação real fica guardada (distribuidor, data, número, PDF, itens, total com frete, kWp). O preço de referência é o **R$/Wp do kit inteiro** por distribuidor; acima de 15 dias o sistema avisa que o preço está velho.
- Fase seguinte (decidida, não agora): preço individual por item no catálogo.
- Quantidades de módulos e de cabos (múltiplos de 25 m) são editáveis na proposta.
- **Descartado:** robô nas plataformas (quebra fácil e pode violar os termos de uso); catálogo só manual (desatualiza).

## D21 · 2026-10-21 · Dados oficiais gravados no banco
- **Irradiação:** PVGIS (Comissão Europeia, API sem chave) como fonte principal, por coordenada do município. O Atlas Brasileiro de Energia Solar (INPE, 2017) pode ser usado para conferência: uso interno, sem revenda dos dados, com a fonte citada (licença CC BY-NC-ND).
- **Tarifas:** dados abertos da ANEEL (TUSD e TE por distribuidora, subgrupo e classe). O Fio B não vem separado: o gestor digita o valor uma vez por ano, depois do reajuste da Energisa TO. Alíquota efetiva de tributos por tipo de tarifa mantida pelo gestor.
- **Municípios:** lista oficial do IBGE (código, UF, coordenadas); o município passa a ser escolhido, nunca digitado. **CEP e CNPJ:** BrasilAPI, como ajuda de preenchimento.
- Tudo é baixado por comando ou botão em Configurações, com `urllib` da biblioteca padrão (sem dependência nova), e gravado no banco com a fonte e a data. A proposta só lê o banco e guarda fonte e data no snapshot.

## D22 · 2026-10-21 · Financiamento por tabela do gestor
- BV e Santander não têm API pública de taxa nem de pré-aprovação; isso só sai no portal de parceiro. Consulta de crédito (Serasa e similares) é paga e o banco já faz a análise.
- **Decisão:** o gestor mantém a taxa mensal por banco e prazo (12, 24, 36, 48, 60 e 72 meses). A proposta mostra, para cada prazo, a parcela do melhor banco, marcada como "aproximada, sujeita à análise de crédito", e compara com a conta de luz.
- Registro do andamento do financiamento (enviado, aprovado, recusado): depois.

## D23 · 2026-10-21 · Estimativa, proposta confirmada e modo cliente
- Proposta sem fatura = **estimativa**, com o aviso: "Valores estimados a partir de dados informados pelo cliente, sem análise da fatura. Sujeitos a discrepâncias com os dados reais." Quando a fatura chega, vira **nova versão confirmada**, com o mesmo número (regra da fatia 6).
- Dados mínimos da estimativa: nome, telefone e município. CPF/CNPJ, UC e endereço só para a proposta confirmada.
- **Modo cliente:** a mesma tela, escondendo custo do kit, mão de obra, desconto e R$/Wp, para o vendedor poder mostrar ao cliente.
- A proposta do ERP **substitui** as propostas geradas pelas plataformas dos distribuidores.

## D24 · 2026-10-21 · Validação e higienização de campos
- Validações em `core/validacoes.py`, funções puras: CPF/CNPJ pelos dígitos verificadores (guardados só com dígitos, CPF único), telefone com DDD + 8 ou 9 dígitos, nome sem espaços sobrando.
- Valores em reais e percentuais em campos de texto com máscara em JS puro, convertidos no servidor (`1.234,56`), sem depender do idioma do navegador. Percentuais mostrados em %, guardados em fração.
- Rótulos com acento e em linguagem do vendedor em todos os formulários.

## D25 · 2026-10-21 · Revisão de D11: `Proposta` volta a ter FK para `Cliente`
- **Motivo:** a estimativa (D23) existe sem UC. Com `cliente` derivado de `uc.cliente`, uma proposta sem UC ficaria sem cliente.
- **Decisão:** `Proposta.cliente` volta a ser FK obrigatória; `uc` e `fatura` passam a ser opcionais. O risco de inconsistência que motivou D11 é tratado no form: a UC escolhida precisa ser do mesmo cliente.
- **Migração:** preencher `cliente` das propostas existentes a partir de `uc.cliente`.

## D26 · 2026-10-21 · Detalhes da fatia v2.1 (municípios, CPF único, menu)
- **Municípios:** a API de localidades do IBGE não traz coordenadas, e o PVGIS precisa delas. A carga inicial vem de `core/dados/municipios_to.csv` (139 municípios do TO, código IBGE, latitude e longitude), extraído de `kelvins/municipios-brasileiros` (licença MIT, dados do IBGE). Entra no banco por migration, sem rede. Outras UFs ficam para o comando `importar_municipios` (v2.2).
- **Nome antigo:** "São Valério da Natividade" hoje se chama "São Valério" no IBGE. A migration reconhece o nome antigo ao converter UCs e irradiação.
- **CPF/CNPJ único:** verificado no formulário, não por restrição no banco, para a migration não falhar se o banco do PC já tiver CPF repetido.
- **Menu:** "Configurações" sai do menu até a tela existir (v2.2). O admin continua em /admin/ para manutenção.

## D27 · 2026-10-21 · Irradiação pela NASA POWER (revisão de D21)
- **Motivo:** o domínio do PVGIS (re.jrc.ec.europa.eu) responde "This url is blocked" (403) para a rede da loja, inclusive no site, com qualquer User-Agent. Testado em 21/10/2026 a partir do PC.
- **Decisão:** a irradiação vem da **NASA POWER** (API pública, sem chave): climatologia mensal `ALLSKY_SFC_SW_DWN` em kWh/m²·dia, plano horizontal, média 2001–2025, por coordenada do município. O PVGIS fica como alternativa se o bloqueio cair.
- **Tarifas ANEEL:** conjunto "Tarifas de Aplicação", distribuidora `ETO`, modalidade Convencional, linha sem detalhe (a linha "SCEE" é a da energia compensada). Valores em R$/MWh, convertidos para R$/kWh. B1 baixa renda usa a subclasse "Baixa Renda" (sem as faixas do desconto social).
- **Bandeiras:** conjunto "Bandeira Tarifária - Adicional" da ANEEL (resolução mais recente), em vez de digitação.

## D28 · 2026-10-21 · Catálogo solar e memória de cotações (fatia v2.4)
- **Catálogo Belenus:** a listagem logada da Belenus traz preço unitário (conta Optimus, sem frete), foto e datasheet (URL pública). O comando `importar_belenus` lê o CSV gerado por `importar/extrair_belenus.py` (pasta fora do Git) e grava `Equipamento` com `preco_referencia` e a data. Fotos e datasheets são copiados de `importar/belenus/` para `media/`. O preço por item ainda **não** entra no custo do kit (D18 continua: custo do kit = cotação real ou R$/Wp da última cotação). Fica só como referência na tela.
- **Tipo `microinversor`:** separado de `inversor`, para o dimensionamento (que escolhe um inversor string por sobrecarga) não sugerir microinversor.
- **Fase e tensão** do inversor e **tipo de estrutura** são lidos da descrição do distribuidor ("Monofasico 220v", "Trifasico 380v", "Colonial", "Fibrocimento", "Telha Metalica", "Laje", "Solo"). O que não for reconhecido fica vazio e pode ser corrigido na tela.
- **Cotação:** `rs_por_wp = total / (kWp × 1000)`, com frete. A referência de cada distribuidor é a cotação mais recente. Ela fica "velha" depois de `ConfigEmpresa.dias_preco_velho` dias (15).
- **Menu:** "Catálogo solar" (equipamentos e cotações), separado do "Catálogo Intelbras" dos orçamentos.

## D29 · 2026-10-21 · Detalhes da tela de 4 passos (fatia v2.5)
- **Rotas:** "Nova proposta" abre os 4 passos (`/propostas/nova/` → `/propostas/<id>/passo/<n>/`). Cada passo é um formulário normal que salva o rascunho e vai para o próximo; o resumo lateral e os números do passo são recalculados por HTMX enquanto o vendedor digita. As propostas antigas (fatia 4, com UC e fatura completas) continuam abrindo no formulário antigo (`origem_consumo` vazio).
- **Cliente:** no passo 1, se o CPF/CNPJ ou o telefone já existem, a proposta usa a ficha existente (sem duplicar) e completa o que faltava. Ligação e tipo de tarifa ficam na proposta.
- **Fatura (proposta confirmada):** no passo 2, a aba "Tenho a fatura" pede número da UC, endereço, mês, kWh, dias do ciclo, valor total e o PDF; cria a UC (se nova) e a `FaturaReferencia`. Tarifa, serviço de distribuição e tributos da fatura passam a ser opcionais: a v2 usa `TarifaVigente`. Exige CPF/CNPJ do cliente.
- **Sem tributos ou sem Fio B na tarifa** (Configurações → Tarifas), o sistema não calcula a economia e diz onde preencher. Não há valor inventado.
- **Módulo sugerido:** o da cotação de referência de menor R$/Wp (`Cotacao.referencias()`); inversor do mesmo distribuidor e da fase da ligação (se não houver, de qualquer distribuidor). Cabos: as metragens da mesma cotação.
- **Custo do kit** em branco: `kWp × 1000 × R$/Wp` da cotação de referência do distribuidor do módulo, com aviso. Escolher uma cotação para a proposta usa o total dela.
- **Desconto:** um campo só, em % ("5%") ou em reais ("300,00"), aplicado só na mão de obra e guardado em reais.
- **Modo cliente:** chave guardada na sessão do navegador; esconde tudo marcado como interno.
- **Prazo de comparação:** o vendedor toca num prazo da tabela de financiamento; fica salvo na proposta (`prazo_comparacao`) para o PDF.

## D30 · 2026-10-21 · PDF da proposta v2 (fatia v2.6)
- **Mesmas 7 páginas** da fatia 5. Os números vêm de `montagem.montar()` (os mesmos da tela de 4 passos), não de `_montar_entrada()` da proposta antiga.
- **Página 3:** com fatura, continua "Análise da fatura de referência". Sem fatura, vira "Consumo considerado": de onde veio o consumo (valor da conta ou kWh informado), a tarifa vigente usada, a folga e a conta estimada de hoje.
- **Estimativa:** faixa com `ConfigEmpresa.aviso_estimativa` na capa e no resumo.
- **Investimento:** só o total, sem R$/Wp (é dado interno, como no modo cliente). Embaixo vem a tabela de financiamento 12–72× com o melhor banco em cada prazo e a parcela marcada como aproximada. Sem taxas cadastradas, a tabela não aparece.
- **Anexo I** só quando a fatura tem PDF.
- Enquanto a emissão (v2.7) não chega, o PDF sai do rascunho pelo botão do passo 4.

## D31 · 2026-10-21 · Emissão e versões (fatia v2.7, antiga fatia 6)
Detalha D07 com o alinhamento de 21/10 (versão nova mantém o número, aceite substitui as outras versões, motivo da perda, data do aceite, "vencida" automática).
- **Número e versão:** a revisão mantém o número e soma 1 à versão (`OPT-2026-0008 v2`). A unicidade passa a ser de número + versão.
- **Emitir** (só rascunho com resultado calculado):
  - congela o kit e o preço da tela: módulo, inversor, quantidades, cabos, custo do kit, mão de obra e investimento;
  - grava o snapshot de premissas e resultados;
  - gera o PDF e o guarda na proposta.
  Se o PDF não sair, a proposta continua rascunho. A versão emitida anterior do mesmo número passa a "substituída".
- **PDF da emitida:** é sempre o arquivo guardado na emissão; não se recalcula.
- **Revisar** (emitida, vencida ou perdida): cria uma cópia em rascunho com a versão seguinte e abre no passo 4 (ou no formulário antigo, se for proposta da fatia 4). "Recebi a fatura" faz o mesmo e abre no passo 2, para a estimativa virar confirmada.
- **Aceita:** grava a data do aceite (hoje, editável), e todas as outras versões do mesmo número passam a "substituída".
- **Perdida:** grava o motivo (preço, concorrente, financiamento negado, cliente desistiu ou adiou, sem retorno, outro) e uma observação opcional.
- **Vencida:** não é gravada. É a emitida com a validade (emissão + dias) já passada, calculada na hora em que se mostra; continua podendo ser aceita ou revisada.
- **Tela da proposta emitida:** resumo, PDF e os botões acima. A lista mostra a situação, inclusive "vencida", e filtra por ela.

## D32 · 2026-10-22 · Tributos, Fio B e iluminação pública conferidos
Conferido em 4 faturas reais (Out/26 e Jul/26, com e sem GD) e nas fontes oficiais.
- **Tributos = 27,40%** no campo "tributos" da tarifa (`(TUSD+TE)/(1−a)`):
  - ICMS 20% (Lei TO 1.287/2001, art. 27, II; os 25% caíram pela ADI 7.113);
  - PIS 1,65% e COFINS 7,60% sobre a base sem ICMS: `1 − 0,9075 × 0,80 = 0,274`.
  - Conferência B1 Out/26: `0,992780 / 0,726 = 1,367460`, igual à fatura.
  - B2 rural com inscrição de produtor tem base de ICMS de 48% (17,96%); a carga usa 27,40% (sem inscrição) e o gestor ajusta se quiser. Baixa renda é isenta de ICMS até 80 kWh; acima, 27,40%.
- **Fio B = 0,441478 R$/kWh** para B1, baixa renda, B2 e B3. Fonte: ANEEL, dados abertos "Componentes Tarifárias", REH 3.323/2026 (vigência 26/08/2026). Na fatura de Out/26, `60% × 0,441478 = 0,264887` contra 0,264904 cobrado. A ANEEL publica o Fio B, ao contrário do que se supunha em D29.
- A migration grava esses valores **só onde o gestor ainda não preencheu** (tributos 0 ou Fio B vazio), na tarifa de vigência 26/08/2026.
- **Iluminação pública (CIP/COSIP) não é percentual.** Em Gurupi (LC 38/2022, arts. 113–125, Anexo VII) é um valor fixo por faixa de consumo medido, em UFIRG (R$ 4,61 em 2026). Conferido: 380 kWh → 6,40 UFIRG = R$ 29,50; 897 e 905 kWh → 11,75 UFIRG = R$ 54,17.
  - Nova tabela `FaixaIluminacao` (município, classe residencial ou não residencial, até quantos kWh, valor em unidades fiscais) e o valor da unidade fiscal no `Municipio`. Gurupi entra por migration. Outros municípios: o gestor cadastra no admin, ou o vendedor digita.
  - Classe: B1 e baixa renda usam a tabela residencial; B3, a não residencial. B2 rural não tem estimativa automática (depende da localização do imóvel).
  - Se o vendedor deixar a iluminação em branco no passo 2, o sistema estima pela tabela (pelo valor da conta, resolve o consumo e a faixa juntos). Se digitar um valor, inclusive 0, vale o digitado.
- **ICMS sobre a TUSD compensada: o motor NÃO desconta (decisão do usuário, 22/10/2026).** Hoje a Energisa só isenta a TE (RICMS-TO art. 2º, CXXXI, § 15; ~R$ 0,19/kWh compensado), mas clientes vêm ganhando na Justiça o estorno, e foi noticiado que a partir de janeiro de 2027 a Energisa aplicará a regra mais benéfica. Reavaliar se isso não se confirmar.

## D33 · 2026-10-22 · Revisão do módulo de propostas: decisões do usuário
Revisão em três visões (vendedor iniciante, gestor, dev sênior), com 30 achados: [relatório](https://claude.ai/artifact/7A9kG1TrDXG18isqDAX392). Plano de correção em `docs/plano-correcoes.md`.
- **Custo de disponibilidade (A03):** não entra no dimensionamento nem na economia. A geração necessária passa a ser `consumo × (1 + folga)`, e a premissa padrão `cobrar_disponibilidade` passa a `False`. O caso Alesio guarda as próprias premissas e não muda. Encerra o item 3 de D08.
- **Kit estimado (A08):** deixa de existir o custo do kit por `kWp × R$/Wp` da última cotação. O sistema monta o kit sugerido a partir do catálogo com preço por item (D28); a cotação real, quando houver, substitui o catálogo (ver D35). Revisa D18 ("custo do kit = cotação real ou R$/Wp") e D20 ("preço por item: fase seguinte").
- **Desfazer aceite (A11):** vendedor e gestor podem desfazer, com motivo registrado. O aceite passa a substituir só as versões emitidas; um rascunho aberto continua editável.
- **Acima de 75 kWp (A02):** só aviso por enquanto ("acima de 75 kWp deixa de ser microgeração"). Proposta do Grupo A vira módulo próprio no futuro. Os demais bloqueios de emissão de A02 valem (alerta de erro, economia ≤ 0, mão de obra zerada).

## D34 · 2026-10-22 · Dimensionamento a partir do catálogo
- O kit sugerido (módulo, inversor, estrutura, cabos, conectores e proteções) sai do catálogo, com o preço de cada item. Substitui a sugestão "módulo da cotação de menor R$/Wp" de D19/D29.
- Tem muitas regras de negócio: antes de codar, fechar as perguntas da seção "Dimensionamento pelo catálogo" de `docs/plano-correcoes.md` e registrar as respostas aqui.

**Respostas do usuário (22/10/2026, 19:37)** e como entram no sistema:
- **Distribuidor:** o kit sai sempre de um só, a Belenus (`ConfigEmpresa.distribuidor_kit`). Intelbras não entra no dimensionamento por enquanto; quando o catálogo Intelbras tiver preços, o vendedor poderá escolher.
- **Ordem:** o vendedor aprova ou escolhe primeiro o **módulo e a quantidade**, porque eles definem o resto do kit. O sugerido é o de menor R$/Wp entre todos os módulos ativos com preço (empate: o de maior potência).
- **Inversor:** sem marca preferida. Uma chave **String × Microinversor** escolhe o tipo. O sugerido é o mais barato da fase da ligação com sobrecarga entre a mínima e a máxima de Configurações; se nenhum couber nessa faixa, o menor que aguenta o sistema (D19). Microinversor: quantidade = módulos ÷ módulos por micro, arredondado para cima.
- **Estrutura:** regras completas e exemplo em `docs/dimensionamento-estruturas.md`. O vendedor informa as fileiras (ex.: `6+5`); em branco, o sistema divide igual entre as strings.
- **Cabos:** 15 m de cabo solar vermelho e 15 m de preto por string do inversor (`metros_cabo_por_string`).
- **Conectores:** 2 pares por string do inversor (`pares_conector_por_string`) e 4 pares por microinversor (`pares_conector_por_micro`), mais 1 suporte de fixação por micro.
- **Proteções** (string box, DPS, disjuntores): a Optimus compra à parte e o custo está na mão de obra. Não entram no kit.
- **Frete:** 7% sobre a soma dos itens do kit, sem a mão de obra (`frete_kit`).
- **Preço do catálogo:** a reimportação da Belenus continua manual; o preço fica velho com 30 dias (`dias_catalogo_velho`). O prazo de 15 dias da cotação (D28) continua.
- **Vendedor troca qualquer item ou quantidade** do kit e pode acrescentar itens do catálogo. O que ele não mexe segue a sugestão. Na emissão, o kit inteiro é congelado na proposta.
- **Cotação vinculada substitui o catálogo** (D35): kit = itens da cotação, custo = total da cotação.
- Quando a leitura por IA existir (rodada 5), o dimensionamento vem da cotação lida e os dados da fatura alimentam o consumo; estas regras valem para a proposta montada pelo sistema.

**Respostas às 9 propostas (22/10/2026, 20:00):** trilho de 2,70 m, 1 por módulo; grampo intermediário N − 1 pacotes de 2 por fileira; junção de trilho por emendas na fileira (3–4 módulos = 1, 5–6 = 2, 7–8 = 3...); grampo final pela espessura cadastrada no módulo (comprimento, largura e espessura passam a ser cadastrados), 30 mm sem cadastro; fixação igual à quantidade de trilhos: gancho na cerâmica, pé em L + haste solar 10 × 250 mm inox no fibrocimento, suporte na laje; telha metálica com mini trilho de 550 mm (2 peças), N + 1 por fileira; solo só com grampos; strings 1 por MPPT, de 4 a 12 módulos; microinversor sem cabo solar, 4 pares de conector e 1 suporte por micro. O usuário pediu um documento só para o dimensionamento de estruturas: `docs/dimensionamento-estruturas.md`.

## D35 · 2026-10-22 · Leitura por IA de fatura e de cotação
- **Fatura:** a IA lê o PDF e preenche os campos do passo 2 (UC, endereço, mês, kWh, dias, valor, CPF/CNPJ). O vendedor confere antes de salvar. Era a fatia v2.8.
- **Cotação:** a IA lê o PDF da cotação (Belenus, Intelbras) e grava `Cotacao` + `ItemCotado`. **Quando a proposta tem cotação lida, o kit e o custo vêm só da cotação e o catálogo é ignorado** para essa proposta. Itens da cotação que não estão no catálogo entram assim mesmo, pela descrição.
- Ambas dependem da chave da API Anthropic (`.env`, fora do Git).

## D36 · 2026-10-22 · Login, registro da emissão e número definitivo (rodada 2)
- **Login (A05):** todo o ERP exige login (`LoginRequiredMiddleware` do Django). Usuários e senhas no admin do Django (`/admin/`); o primeiro é criado com `python manage.py createsuperuser`. Grupo **gestor** (ou superusuário) é o único que altera Configurações, cadastra ou edita equipamentos do Catálogo solar e importa a tabela Intelbras. O vendedor consulta os catálogos e registra cotações de kit (é ele quem cota com o distribuidor). Mídia (faturas, PDFs) também exige login.
- **`.env` (A05):** `SECRET_KEY` e `DEBUG` saem do código e vão para o arquivo `.env` na raiz (fora do Git), lido por uma função de 10 linhas em `config/settings.py`, sem dependência nova. Sem `.env`, o sistema roda em modo desenvolvimento (DEBUG ligado, chave de desenvolvimento) e avisa no console. Com `DEBUG=0`, os arquivos de `static/` são servidos pelo próprio Django, como já é feito com a mídia (uso interno, 2–5 usuários).
- **Acesso externo (celular):** por VPN ou túnel (ex.: Tailscale), nunca abrindo a porta do PC na internet. Configuração fora do código.
- **Registro (A10):** cada emissão grava em `registro` (JSON) as entradas e as saídas do cálculo: dados do cliente e do consumo, tarifa com tributos e Fio B, município e irradiação, premissas, kit com códigos, cotação, preço, resultados, financiamento e alertas. A proposta guarda quem emitiu, aceitou, marcou perdida e desfez o aceite. Tarifas e taxas continuam editadas no lugar (as tarifas já têm linha por vigência ANEEL): o histórico que importa é o do JSON de cada emissão, que guarda os valores exatos usados. Assim não é preciso tabela de histórico nem regra para "taxa encerrada". Revisa o item A10 do plano.
- **PDF na emissão (A12):** continua dentro da transação, de propósito: se o PDF falhar, nada é gravado. O SQLite passa a modo WAL com espera de 20 s, para que leituras não travem enquanto o PDF é gerado. **Backup:** com o servidor parado, copiar `db.sqlite3` (com o servidor ligado, copiar também `db.sqlite3-wal` e `db.sqlite3-shm`) e a pasta `media/`. Revisa D05.
- **Número (A13):** o rascunho não tem número; o número `OPT-AAAA-NNNN` é dado na primeira emissão e mantido nas versões (D31). Rascunho pode ser descartado (apagado) pelo vendedor. Propostas do formulário antigo continuam como estão até a rodada 3.
- **Ano de conexão (A17):** deixa de ser premissa fixa. No rascunho, é o ano de hoje + prazo de homologação (dias, em Configurações, padrão 60). A emitida guarda o ano no snapshot.

## D37 · 2026-10-22 · Leitura por IA com Gemini (revisa D35)
- **Provedor:** Google Gemini (Gemini API do Google AI Studio), no lugar da API Anthropic de D35. Motivo: o usuário não conseguiu pagar créditos da Anthropic com os meios da Optimus, e já tem uma chave Gemini. O resto de D35 continua: a IA lê fatura e cotação, o vendedor confere antes de salvar, e cotação lida substitui o catálogo.
- **Sem dependência nova:** a chamada é um POST HTTP com a biblioteca padrão do Python (`urllib`) para `generateContent`, com o PDF em base64 e a resposta em JSON por esquema (`responseSchema`). Fica em `core/ia.py` (`ler_pdf`). O que pedir e como converter a resposta em campos do formulário fica em `propostas/services/leitura_ia.py` (funções puras).
- **Configuração no `.env`:** `GEMINI_API_KEY` (obrigatória para ler) e `GEMINI_MODELO` (opcional; padrão `gemini-flash-lite-latest`; ver o teste abaixo). Sem chave, o botão avisa que a leitura não está configurada; o resto do sistema funciona igual.
- **Nada é gravado direto:** a leitura só preenche os campos da tela (passo 2 ou cotação). O vendedor confere e salva como sempre, com as mesmas validações.
- **Modelo e nova tentativa (teste real em 22/10/2026, no PC-Escritorio):** com uma fatura fictícia, `gemini-flash-lite-latest` leu todos os campos certos em 1,7 s; `gemini-flash-latest` deu 503 (sobrecarga) e chegou a 70 s; `gemini-2.5-flash` não está mais disponível para chaves novas (404). Por isso o padrão é o *lite*. Quando o Google responde 503, o sistema espera 3 s e tenta mais uma vez antes de mostrar o aviso ao vendedor.
- **LGPD:** a chave atual está no nível gratuito, em que o Google pode usar o conteúdo enviado para melhorar seus produtos. No desenvolvimento, testar só com faturas próprias ou autorizadas; antes de usar com clientes, ativar o faturamento da chave (nível pago) ou rever o provedor.

## D38 · 2026-10-24 · CPF/CNPJ exigido só na emissão da proposta confirmada (revisa D23)
- **Motivo (H13, teste humano de 24/10):** a fatura da Energisa traz o CPF mascarado (`***.456.789-**`), então o vendedor com a fatura na mão não tem o número e o passo 2 travava.
- **Decisão (usuário, 24/10, opção a):** o passo 2 aceita a fatura sem CPF/CNPJ. O passo 4 mostra que ele falta e **bloqueia a emissão da proposta confirmada** até ser preenchido no passo 1 ou 2. Pré-visualização continua liberada. Estimativa (sem fatura) segue sem exigir CPF.
- CPF digitado com asterisco é recusado com a mensagem de que a fatura não traz o número completo. A leitura por IA deixa o campo vazio e avisa o vendedor para pedir ao cliente.

## D39 · 2026-10-24 · Múltiplos da tabela Intelbras não valem para a Optimus (revisa D13/D14)
- **Motivo (H11):** a "Qtd. Múltipla" da tabela Intelbras vale para a compra do distribuidor na fábrica. O distribuidor vende unidade avulsa para a Optimus.
- **Decisão:** sem aviso de múltiplos no orçamento e sem selo "múltiplo N" na busca. O campo continua importado e visível só na tabela do catálogo, como informação.

## Pendências de validação
- [x] Regra de custo de disponibilidade para GD após a Lei 14.300 (item 3 de D08): fora do motor (D33).
- [x] Valor da TUSD Fio B vigente na Energisa TO por subgrupo (B1/B2/B3): 0,441478 R$/kWh (D32).
- [ ] Irradiação mensal por município: substituir estimativas regionais pelo PVGIS (D21).
- [ ] Percentual de Fio B a partir de 2029 (definição ANEEL). Premissa atual: 100%.
- [ ] Orçamentos: confirmar se o PSD da tabela corresponde ao preço real de compra no distribuidor (D13).
- [ ] Orçamentos: incluir impostos sobre a venda (regime da Optimus) no cálculo de margem (D14).
- [ ] Orçamentos: obter o selo oficial "Parceiro Credenciado Intelbras" (Portal Sou Parceiro) para a capa do PDF, seguindo o manual de diretrizes da marca.
