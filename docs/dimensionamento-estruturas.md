# Dimensionamento do kit: estrutura, cabos e conectores

Regras que o sistema usa para montar o kit pelo catálogo, quando a proposta não tem cotação vinculada. Foram definidas pelo usuário em 22/10/2026 e estão registradas em D34 (`docs/decisoes.md`). Quando a leitura de cotação por IA existir (rodada 5), o kit de uma proposta com cotação lida virá da cotação, e estas regras não se aplicam a ela (D35).

O código está em `propostas/services/calculo.py`, nas funções `quantidades_estrutura`, `emendas_na_fileira` e `quantidades_eletricas`. A escolha de cada item do catálogo fica em `propostas/montagem.py`, nas funções `item_do_catalogo` e `_kit_do_catalogo`.

## 1. Ordem da montagem

1. **Módulo e quantidade.** O sistema sugere o módulo de menor R$/Wp do distribuidor do kit (Belenus) e a quantidade que gera o consumo com folga. O vendedor pode trocar os dois, e tudo o que vem depois é recalculado.
2. **Inversor.** O vendedor escolhe na chave entre *Inversor string* e *Microinversor*.
   - **String:** o sistema sugere o mais barato da fase da ligação com sobrecarga entre a mínima (0,8) e a máxima (1,5). Se nenhum estiver nessa faixa, sugere o menor que aguenta o sistema.
   - **Micro:** o sistema sugere o de menor custo total, com quantidade = módulos ÷ módulos por micro, arredondado para cima.
3. **Strings.**
   - **Inversor string:** 1 string por MPPT, desde que cada string tenha pelo menos 4 módulos. O sistema passa do número de MPPT só quando uma string ficaria com mais de 12 módulos. Os limites de 4 e 12 ficam em Configurações.
   - **Microinversor:** cada micro conta como uma string.
4. **Fileiras.** O vendedor digita os módulos de cada fileira, por exemplo `6+5`. Se deixar em branco, o sistema divide os módulos igualmente entre as strings (no micro, em fileiras de até 12) e avisa para conferir no telhado. Se as fileiras não somarem a quantidade de módulos, a proposta não pode ser emitida.
5. **Estrutura, cabos e conectores**, pelas regras abaixo.
6. **Custo do kit** = soma de quantidade × preço de cada item + **7% de frete**. A mão de obra não entra nessa soma.

## 2. Estrutura (por fileira de N módulos)

| Item | Cerâmica | Fibrocimento | Laje | Telha metálica | Solo |
|---|---|---|---|---|---|
| Trilho de 2,70 m | N | N | N | — | — |
| Junção de trilho | emendas (ver abaixo) | emendas | emendas | — | — |
| Fixação no telhado | N ganchos | N pés em L | N suportes de laje | — | — |
| Haste solar 10 × 250 mm inox | — | N | — | — | — |
| Mini trilho 550 mm (2 peças) | — | — | — | N + 1 | — |
| Grampo final (pacote de 4) | 1 | 1 | 1 | 1 | 1 |
| Grampo intermediário (pacote de 2) | N − 1 | N − 1 | N − 1 | N − 1 | N − 1 |
| Garra de aterramento | 1 | 1 | 1 | 1 | 1 |

- **Fixação no telhado:** a quantidade é igual à de trilhos. O tipo segue o telhado: gancho colonial na cerâmica, pé em L com haste no fibrocimento e suporte ajustável na laje.
- **Junções (emendas):** dependem dos módulos da fileira.

  | Módulos na fileira | 1–2 | 3–4 | 5–6 | 7–8 | 9–10 |
  |---|---|---|---|---|---|
  | Emendas | 0 | 1 | 2 | 3 | 4 |

  Fórmula: `(N − 1) ÷ 2`, arredondado para baixo, a partir de 3 módulos. Cada emenda conta como 1 junção do catálogo.
- **Grampo final:** é o da espessura da moldura do módulo, que vem do cadastro do módulo. Sem espessura cadastrada, usa o de 30 mm (Configurações).
- **Grampo intermediário:** 2 por emenda entre módulos (um em cada trilho), ou seja 2 × (N − 1) peças, o que dá N − 1 pacotes de 2.
- **Solo:** o kit leva só os grampos e o aterramento. O vendedor acrescenta o resto da estrutura à mão, em "Trocar itens ou quantidades do kit".
- Telha zipada, telha shingle e mini trilho alto não entram sozinhos no kit. O vendedor acrescenta esses itens à mão.

## 3. Cabos, conectores e microinversor

| Item | Inversor string | Microinversor |
|---|---|---|
| Cabo solar vermelho | 15 m por string | — |
| Cabo solar preto | 15 m por string | — |
| Conector (pacote de 2 pares) | 2 pares por string | 4 pares por micro |
| Suporte de fixação do micro | — | 1 por micro |

- Proteções (string box, DPS, disjuntores) **não entram no kit**: a Optimus compra à parte, e o custo está na mão de obra.
- Os metros de cabo e os pares de conector ficam em Configurações → Premissas → Kit montado pelo catálogo.

## 4. Exemplo: 11 módulos em cerâmica, fileiras 6+5, inversor de 2 MPPT

| Item | Conta | Quantidade |
|---|---|---|
| Trilho 2,70 m | 6 + 5 | 11 |
| Junção | 2 + 2 | 4 |
| Gancho | igual aos trilhos | 11 |
| Grampo final (pct. 4) | 1 por fileira | 2 |
| Grampo intermediário (pct. 2) | (6 − 1) + (5 − 1) | 9 |
| Garra de aterramento | 1 por fileira | 2 |
| Cabo solar vermelho e preto | 2 strings × 15 m | 30 m de cada |
| Conector (pct. 2 pares) | 2 strings × 2 pares ÷ 2 | 2 |

O mesmo sistema em **fibrocimento** troca os 11 ganchos por 11 pés em L e acrescenta 11 hastes. Em **telha metálica**, sai trilho, junção e fixação, e entram (6 + 1) + (5 + 1) = 13 mini trilhos de 550 mm.

## 5. Escolha do item no catálogo

- Cada equipamento tem um **papel no kit**: trilho, junção, fixação, haste, mini trilho, grampo final, grampo intermediário, aterramento, suporte do micro, cabo preto, cabo vermelho ou conector. O papel é lido da descrição na importação da Belenus. O gestor pode corrigi-lo em Catálogo solar → equipamento, e a correção fica mesmo depois de reimportar o catálogo.
- Entre os itens com o mesmo papel, o sistema escolhe o do tipo de telhado da proposta e, no grampo final, o da espessura certa. Se ainda sobrar mais de um, fica o mais barato por peça.
- As quantidades dos grampos são contadas em peças e convertidas em embalagens pelo campo **peças por embalagem** ("4 Pecas" = 4). O conector é contado em pares ("C/2 Pares" = 2). Os demais itens são contados na unidade em que o catálogo vende.
- O vendedor pode trocar qualquer item, mudar qualquer quantidade (0 tira o item do kit) e acrescentar itens do catálogo. Na emissão, o kit inteiro fica congelado na proposta, e uma mudança posterior no catálogo não altera uma proposta emitida.
- **Medidas do módulo** (comprimento, largura e espessura, em mm) vêm do datasheet e são cadastradas pelo gestor. A espessura escolhe o grampo final, e comprimento × largura dá a área aproximada do sistema.
