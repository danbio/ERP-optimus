# Plano de correções e evolução da proposta solar

**Origem:** revisão de 22/10/2026 do módulo de propostas (código em `a004074`), em três visões: vendedor iniciante, gestor e dev sênior. Relatório completo, com evidência de cada achado: https://claude.ai/artifact/7A9kG1TrDXG18isqDAX392

**Decisões do usuário:** D33 a D35 em `docs/decisoes.md`.

**Como usar este arquivo:** cada rodada vira uma fatia com PR próprio, na ordem abaixo. Ao terminar uma rodada, marcar os itens com `[x]` e o número do PR. Os códigos `Axx` são os do relatório.

---

## Rodada 1 · Travas de cálculo e emissão (PR #13)

Objetivo: nenhuma proposta errada sai sem aviso. Cada item entra com o teste que reproduz o caso do relatório (A16).

- [x] **A03** Disponibilidade fora do dimensionamento e da economia (D33): `geracao_necessaria = consumo × (1 + folga)`; premissa padrão `cobrar_disponibilidade = False`. Caso Alesio inalterado.
- [x] **A02** Emissão bloqueada com alerta de erro, economia ≤ 0 ou mão de obra zerada. Acima de 75 kWp: só aviso (D33). Motivo do bloqueio no topo do passo 4.
- [x] **A01** Cotação vinculada com kWp diferente do sistema (mais de 5%): erro que bloqueia a emissão, com a opção "usar a quantidade da cotação". O select mostra só cotações do distribuidor do módulo e dentro da validade.
- [x] **A04** Cliente achado pelo telefone ou CPF: perguntar "É esta pessoa?" em vez de sobrescrever nome e município. Nome e município só mudam na tela do cliente.
- [x] **A06** Plausibilidade: aviso com confirmação para conta ou consumo acima do limite (limites em Configurações); erro para fatura com R$/kWh a mais de 30% da tarifa vigente, mês futuro ou com mais de 13 meses, UC fora do formato.
- [x] **A11** Aceite substitui só as emitidas. "Desfazer aceite" para vendedor e gestor, com motivo (D33). Aceita pode ser revisada.
- [x] **A14** Ligação e tipo de tarifa começam em "Escolha", com ajuda de como identificar.
- [x] **A15** Passo 4: erros no topo, dois botões ("Pré-visualizar" e "Emitir e baixar PDF") com confirmação, vírgula decimal e textos na língua do vendedor.
- [x] **A09** Pré-visualização do rascunho com marca d'água "RASCUNHO"; PDF limpo só da emitida.
- [x] **A23** Passo fora de 1–4, "voltar" externo no modo cliente e ações sem `@require_POST`.

## Rodada 2 · Login e registro (D36, PR #14)

Precisa estar pronta antes de liberar o acesso pelo celular fora da loja.

- [x] **A05** Login (`LoginRequiredMiddleware`, nativo no Django 5.1+), grupo "gestor" para Configurações e catálogo, `SECRET_KEY` e `DEBUG` no `.env`, mídia só para usuário logado. Acesso externo por VPN ou túnel.
- [x] **A10** Registro completo na emissão: todas as entradas e saídas de `montar()` em JSON; `emitida_por`, `aceita_por`, `perdida_por`, `aceite_desfeito_por`. Tarifas e taxas ganham linha nova por vigência em vez de serem sobrescritas.
- [x] **A12** PDF gerado fora da transação; SQLite em modo WAL.
- [x] **A13** Número definitivo só na primeira emissão; botão "Descartar rascunho".
- [x] **A17** Ano de conexão derivado da data de emissão + prazo de homologação (Configurações).
- [x] **A30** `waitress` no `requirements.txt`.

## Rodada 3 · Limpeza antes das regras novas (feita)

Feita antes do dimensionamento pelo catálogo, porque ele reescreve `montar()`.

- [x] **A24** Remover o fluxo da fatia 4 (formulário antigo, `_montar_entrada`, `recalcular`, `kit_nova_linha`, `fatura_novo`, `_contexto_antigo`, ramos `eh_antiga`, campos de fatura só dele). Fica `calcular()` e o teste do caso Alesio.
- [x] **A26** `montar()` em etapas pequenas (consumo → sistema → preço → financeiro), calculado uma vez por requisição, sem `ZeroDivisionError` como controle de fluxo.
- [x] **A25** Uma função por regra (geração por kWp, fase do inversor); limites de cobertura e sobrecarga mínima em Configurações.
- [x] **A27** `views.py` dividido (passos, emissão, catálogo, documento do PDF).
- [x] **A28** Lista com kWp gravado, paginação e filtro por mês.

## Rodada 4 · Dimensionamento pelo catálogo (D34)

Substitui o kit estimado por R$/Wp (A07, A08) e faz o kit do PDF bater com o que será comprado (A21). Respostas de 22/10 registradas em D34; regras do kit em `docs/dimensionamento-estruturas.md`.

### Perguntas de negócio

1. **Distribuidor:** o kit sai sempre de um distribuidor só (faturamento direto)? Como escolher: menor custo total do kit, ou um distribuidor preferido com o outro como alternativa?
2. **Módulo:** menor R$/Wp entre todos, ou uma lista de módulos aprovados pelo gestor? O estoque (SP/ES/GO) pesa?
3. **Inversor:** além da sobrecarga ≤ 1,5 e da fase, vale preferência de marca? Quando sugerir microinversor em vez de string?
4. **Estrutura:** qual a regra de quantidade por tipo de telhado (ex.: um kit para cada N módulos, trilho por metro)? Uma regra por tipo: cerâmica, fibrocimento, metálica, laje, solo.
5. **Cabos:** como estimar a metragem (fixa por faixa de kWp, por distância informada, múltiplos de 25 m)?
6. **Conectores:** pares por string, por inversor ou quantidade fixa?
7. **Proteções** (string box, DPS, disjuntores): entram no kit do distribuidor ou a Optimus compra à parte?
8. **Frete:** percentual médio sobre o kit, valor por distribuidor, ou digitado pelo vendedor?
9. **Preço do catálogo:** a reimportação da Belenus continua manual? Com quantos dias o preço fica "velho"?
10. **Intelbras:** entra no dimensionamento? Hoje a tabela Intelbras dos Orçamentos não traz preço dos itens solares.

### Itens
- [x] Respostas registradas em D34.
- [x] Sugestão do kit completo com preço por item; vendedor troca qualquer item ou quantidade.
- [x] Cotação vinculada substitui o catálogo (D35).
- [x] **A21** Kit do PDF = itens do kit montado ou da cotação.
- [x] Confirmar com o usuário as propostas de D34 (respostas de 22/10, 20:00) e documentar em `docs/dimensionamento-estruturas.md`.

**Resolvido na rodada 4:** módulo de menor R$/Wp do catálogo Belenus; chave String × Microinversor; inversor mais barato dentro da faixa de sobrecarga (corrige o inversor grande demais em sistema pequeno); strings por MPPT; fileiras do vendedor ou sugeridas; estrutura, cabos e conectores pelas regras de D34; frete de 7%; preço do catálogo velho com 30 dias; troca de item, quantidade e itens a mais no passo 3; kit congelado na emissão; papel de cada item no catálogo editável pelo gestor.

## Rodada 5 · Leitura por IA (D35, D37)

Usa o Gemini (D37), com a chave `GEMINI_API_KEY` no `.env`.

- [x] Fatura: PDF → campos do passo 2, com conferência do vendedor.
- [x] Cotação: PDF → `Cotacao` + `ItemCotado`; a proposta com cotação lida usa só a cotação, ignorando o catálogo.
- [ ] Testes com as faturas e cotações reais de outubro/2026. (Teste real com fatura fictícia feito em 22/10 no PC-Escritorio: todos os campos certos.)

## Teste humano de 24/10/2026 (rodadas 6 a 13)

Achados `Hxx` e premissas `P1`/`P2` do teste feito pelo usuário no navegador. Relatório com causa, proposta e perguntas de cada um: `docs/relatorio-teste-humano-2026-10-24.md`; conferência no código e ajustes de ordem: `docs/parecer-teste-humano-2026-10-24.md`. Item com **(pergunta)** só começa depois da resposta do usuário, registrada em `docs/decisoes.md`.

## Rodada 6 · Bloqueio e erros rápidos (PR #21)

- [x] **H13** CPF/CNPJ exigido só na emissão da proposta confirmada (D38, revisa D23): o passo 2 aceita a fatura sem CPF; o passo 4 avisa e bloqueia a emissão. Teste: proposta com fatura e sem CPF.
- [x] **H14** Já tratado na leitura (`leitura_ia.py`: CPF mascarado volta vazio, com teste). Falta: aviso "a fatura não traz o CPF completo, peça ao cliente" e instrução no esquema da IA para devolver vazio quando mascarado.
- [x] **H01** Admin sem CSS com `DEBUG=0`: a rota de estáticos procura com os finders do `staticfiles` (`finders.find`), sem dependência nova. Teste pedindo o CSS do admin com `DEBUG=0`.
- [x] **H03** Campo de logo próprio (miniatura + "Remover logo") e estilo único de checkbox. Causa: `.campo input { width: 100% }` estica a caixa "Limpar" do Django.
- [x] **H11** Tirar o aviso e o selo de múltiplos do orçamento Intelbras (D39, revisa D13/D14), com os dois testes que afirmam o aviso.
- [x] **H17** Resumo da importação Intelbras lista os códigos novos e os que saíram, com texto explicando novo, em encerramento e inativo.
- [x] Tarifa vigente escolhida por distribuidora (`TarifaVigente.vigentes()` e `dados_oficiais`), para a entrada de outra distribuidora (H05) não misturar tarifas.

## Rodada 7 · Premissas da aplicação inteira e modo cliente (PR #22)

- [x] **P1** (D41) Registrar em `decisoes.md` e `CLAUDE.md`: toda entrada do usuário com validação e higienização (amplia D24).
- [x] **P2** Registrar em `decisoes.md` e `CLAUDE.md`: busca e filtros atualizam a lista na hora, sem botão (D40).
- [x] **H02** `EmpresaForm`: CNPJ e telefone com as validações de `core/validacoes.py`, limite de tamanho nos textos, linhas vazias fora das listas "um por linha".
- [x] **A22** Travas nas Configurações (mínimo de um perfil, orientação 50–100%, validade 5–60 dias). Mesmo trabalho do H02.
- [x] **P1** Varredura de todos os formulários (tabela campo × regra), com teste de dados malformados em cada um.
- [x] **H06/H07/P2** (PR #21, D40) Busca e filtros com HTMX em clientes, propostas, orçamentos, catálogo Intelbras e catálogo solar; endereço da página atualizado; filtro volta à página 1 e a paginação mantém os filtros.
- [x] **A29** Modo cliente volta para a página em que estava e não envia ao navegador o que esconde (antes de mostrar a tela a cliente no celular).
- [ ] **(com você)** Antes de usar fatura de cliente real: ativar o nível pago da chave Gemini ou rever o provedor (D37, LGPD). Configuração, não código.

## Rodada 8 · Cliente com endereço e leitura da fatura (PR #23, D42)

- [x] **H12a** Endereço no `Cliente` (CEP, rua, número, complemento, bairro), todos opcionais, reaproveitando o `municipio` que o cliente já tem. CEP consultado no ViaCEP pelo navegador (JS puro), casando o código IBGE com `Municipio`; sem internet, preenche à mão (registrar a exceção à regra de não consultar API na hora).
- [x] **H12b** Preenchimento por CNPJ (BrasilAPI, gratuito). Por CPF não há fonte gratuita e legal: descartar e registrar o motivo **(pergunta: confirmar o descarte)**.
- [x] **H15** UC e fatura já são gravadas no passo 2. Falta: endereço da fatura no cliente e conferência do titular **(perguntas: confirmação, como achar o cliente, conflito, qual endereço; revisa D37)**. Corrigir: o CPF do titular não pode ir para o cliente quando o titular é outra pessoa.

## Rodada 9 · Financiamento da proposta solar

- [x] **H04a** Taxa com "% ao mês" em cada campo e o equivalente anual ao lado.
- [x] **H04b/c** (D43) TAC e IOF no valor financiado, no `calculo.py`, com teste; melhor banco escolhido depois de somar TAC e IOF; `registro` da emissão guarda os dois **(perguntas: a taxa cadastrada é nominal ou CET; TAC fixa ou %, por banco; IOF padrão PF/PJ; separado ou embutido no PDF)**.

## Rodada 10 · Orçamento Intelbras

- [x] **H09** (D44) Mostrar ou esconder o preço dos itens no PDF **(perguntas: orçamento inteiro ou por item; quantidade e subtotais)**.
- [x] **H10** (D44) Parcelamento 3×, 6×, 12×, 21× no PDF do orçamento **(perguntas: cartão ou boleto, juros por prazo, prazos fixos, vendedor pode esconder)**. Mesmo PDF e mesma migração do H09.

## Rodada 11 · Detalhe do produto solar

- [x] **H08** ~~Protótipo HTML para aprovação~~ dispensado (D45): foto e datasheet em destaque, ficha só com os campos do tipo.
- [x] **H08** (D45) Página de ver o produto, aberta também ao vendedor (hoje a única página é a edição, só do gestor) + edição do gestor com os campos do tipo; espaço reservado sem foto ou datasheet.

## Rodada 12 · Painel e ferramentas do gestor e do vendedor

- [ ] **A20** Vendedor responsável e "próximo contato", com lista "ligar hoje". Vem antes do painel.
- [ ] **H16/A19** Dashboard na página inicial, com protótipo antes; gestor vê todos, vendedor vê os dele (`eh_gestor`); orçamento Intelbras ganha campo de vendedor se entrar no "por vendedor" **(perguntas: indicadores da primeira versão; painel do vendedor × do gestor)**.
- [ ] **A18** Barra fixa no celular com kWp, investimento e parcela; menu recolhido.

## Rodada 13 · Goiás

- [ ] **H05** Municípios de Goiás com irradiação, distribuidora (Equatorial Goiás, sigla ANEEL própria), tarifas com tributos de GO, Fio B e iluminação pública por município; distribuidora da proposta vinda da UC/município; tirar o "Energisa TO" fixo do código e das telas. Bandeira é nacional, não muda **(perguntas: estado inteiro ou região; tipos de tarifa)**.

## Rodada 14 · Higienização e documentação

- [ ] Varredura de código morto, nomes e imports.
- [ ] Cores literais (`#fff`) fora de `tokens.css` trocadas por token; texto de ajuda do Fio B atualizado (a ANEEL publica, D32).
- [ ] Docstring em português em toda função pública: o que faz, entradas com unidade (kWh, R$, fração), saída e a decisão `Dxx` de origem. Comentário só onde a regra não é óbvia.
- [ ] README atualizado: instalar, rodar, atualizar dados oficiais, fazer backup.
- [ ] CLAUDE.md e specs conferidos contra o código final.

---

## Resolvido na rodada 6

- **H13:** o passo 2 com fatura aceita CPF/CNPJ vazio e não procura "dono" com CPF vazio; o passo 4 lista o CPF como motivo de bloqueio só na proposta confirmada (D38).
- **H03:** `core/_campo.html` põe checkbox ao lado do texto em todo o sistema; `core/_campo_arquivo.html` serve para qualquer campo de arquivo com miniatura e "Remover".
- **H11:** o campo `qtd_multipla` continua importado e na tabela do catálogo, só como informação (D39).

## Resolvido na rodada 1

- **Conta com o sistema (A03):** a conta exibida tem como piso a disponibilidade (30, 50 ou 100 kWh × tarifa) mais a iluminação pública. A economia e o dimensionamento continuam sem a disponibilidade (D33).
- **A01:** o select de cotações esconde as vencidas; cotação de outro distribuidor aparece, mas vira erro que bloqueia a emissão (o filtro por distribuidor entra com o kit do catálogo, rodada 4).
- **A09:** o PDF de rascunho só é recusado nas propostas v2; o formulário antigo continua com PDF até ser removido (rodada 3).

## Resolvido na rodada 2 (D36)

- **A10:** o histórico de tarifas e taxas fica no JSON `registro` de cada emissão, com os valores usados; as tabelas continuam editadas no lugar.
- **A12:** o PDF continua dentro da transação (se falhar, nada é gravado); o SQLite em WAL evita travar as leituras.
- Os limites das travas da rodada 1 ficaram editáveis em Configurações → Premissas.

## Resolvido na rodada 3

- **A24:** propostas antigas já emitidas continuam com o PDF guardado; um rascunho antigo abre nos 4 passos e precisa ser completado.
- **A25:** cobertura mínima e máxima e sobrecarga mínima do inversor estão em Configurações → Premissas. Snapshots antigos sem essas chaves usam 80%, 130% e 0,8.
- **A26:** sem economia, o retorno fica 0 ("não se paga") em vez de erro de divisão; a emissão continua bloqueada (A02).
- **A27:** `propostas/views/` com `passos.py`, `versoes.py` (lista e ações), `catalogo.py` e `documento.py` (PDF).
- **A28:** kWp gravado na proposta, 50 por página e filtro pelo mês de emissão.
