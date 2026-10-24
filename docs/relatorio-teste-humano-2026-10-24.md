# Relatório do teste humano · 24/10/2026

**Quem testou:** o usuário (gestor da Optimus), percorrendo a aplicação no navegador em `http://127.0.0.1:8000`, com o código em `1cef85a` (fim da rodada 5) e `DEBUG=0` no `.env`.

**Como ler:** cada achado tem um código `Hxx` (H de "humano", para não confundir com os `Axx` da revisão de 22/10). Para cada um: o que o usuário viu, a causa encontrada no código (quando já foi investigada), o que fazer e as perguntas que precisam de resposta antes de codar. As rodadas estão em `docs/plano-correcoes.md`.

**Gravidade:**
- **Bloqueia:** impede o uso de uma função principal.
- **Erro:** a função funciona, mas faz algo errado ou confuso.
- **Melhoria:** função nova ou mudança de experiência.
- **Premissa:** regra que passa a valer para a aplicação inteira.

## Resumo

| Código | Tela | Achado | Gravidade |
|---|---|---|---|
| H01 | `/admin/` | Admin sem CSS | Erro |
| H02 | `/configuracoes/` | Campos sem validação nem higienização | Erro |
| P1 | toda a aplicação | Toda entrada do usuário com validação e higienização | Premissa |
| H03 | `/configuracoes/` | Checkbox desalinhado do texto | Erro |
| H04 | `/configuracoes/financiamento/` | Taxa sem unidade clara, sem taxa de cadastro, sem impostos | Erro + Melhoria |
| H05 | `/configuracoes/municipios/` | Faltam os municípios de Goiás | Melhoria |
| H06 | `/orcamentos/catalogo/` | Busca deve atualizar enquanto digita | Melhoria |
| H07 | `/orcamentos/catalogo/` | Filtro deve atualizar ao escolher, sem botão | Melhoria |
| P2 | toda a aplicação | Busca e filtros atualizam a lista na hora, sem botão | Premissa |
| H08 | `/propostas/catalogo/<id>/` | Detalhe do produto solar: foto, datasheet e campos por tipo | Melhoria |
| H09 | `/orcamentos/<id>/` | Mostrar ou esconder preço de cada item para o cliente | Melhoria |
| H10 | PDF do orçamento Intelbras | Parcelamento resumido: 3×, 6×, 12×, 21× | Melhoria |
| H11 | orçamento Intelbras | Aviso de "múltiplos" é desnecessário | Erro |
| H12 | cadastro de cliente | Endereço opcional com preenchimento automático; pesquisa sobre CPF | Melhoria |
| H13 | `/propostas/<id>/passo/2/` | Proposta não avança sem CPF | **Bloqueia** |
| H14 | leitura da fatura por IA | CPF vem escondido na fatura | Erro |
| H15 | leitura da fatura por IA | Criar ou atualizar cliente e endereço com os dados da fatura | Melhoria |
| H16 | `/` | Página inicial com dashboard completo | Melhoria |
| H17 | `/orcamentos/catalogo/importar/` | Tela não explica novos, encerrados e inativos | Melhoria (a confirmar) |

**Teste aprovado:** a leitura de fatura com o Gemini (D37) funcionou sem erros e extraiu certo todos os campos, menos o CPF (ver H14).

---

## H01 · Admin sem CSS · Erro

**O que aconteceu:** `/admin/auth/user/` abre como página sem estilo.

**Causa (confirmada no código):** com `DEBUG=0`, o Django não serve arquivos estáticos sozinho. A rodada 2 (D36) criou a rota `arquivo_estatico` em `config/urls.py`, mas ela só procura na pasta `static/` do projeto. O CSS do admin fica dentro do próprio Django (`django/contrib/admin/static/`), então essa rota não acha os arquivos. As telas do ERP funcionam porque o CSS delas está em `static/`.

**O que fazer:** fazer a rota procurar os estáticos em todos os lugares onde o Django guarda arquivos (os "finders" do `staticfiles`), ou rodar `collectstatic` para uma pasta única e servir dela. A primeira opção é mais simples e não exige um passo a mais na instalação. Entra com um teste que abre o CSS do admin com `DEBUG=0`.

## H02 · Configurações sem validação · Erro

**O que aconteceu:** os campos de `/configuracoes/` aceitam qualquer coisa.

**Causa (confirmada no código):** o `EmpresaForm` (`core/forms.py`) não valida nenhum campo. CNPJ e telefone são texto livre, embora `core/validacoes.py` já tenha as funções de CPF/CNPJ e telefone (D24) que o cadastro de cliente usa. Os textos longos (sobre, benefícios, etapas) não passam por limpeza de espaços nem por limite. As outras abas (premissas, tarifas, financiamento) têm limites numéricos, mas precisam ser conferidas campo a campo.

**O que fazer:** aplicar no `EmpresaForm` as validações que já existem (CNPJ por dígito verificador, telefone com DDD, e-mail) e limpar espaços sobrando. Na rodada da premissa P1, conferir campo a campo todos os formulários, nas cinco abas de Configurações e no resto do sistema.

## P1 · Premissa: toda entrada do usuário com validação e higienização

**O que o usuário pediu:** que vire regra que toda entrada do usuário tenha validação e higienização, em qualquer tela.

**Situação atual:** D24 já registra a regra para os formulários da proposta e do cliente, mas ela não foi aplicada no resto (H02 é o exemplo).

**O que fazer:**
1. Registrar a premissa em `docs/decisoes.md`, ampliando o alcance de D24, e no `CLAUDE.md`.
2. Fazer uma varredura de todos os formulários (Configurações, catálogo solar, cotações, cliente, orçamento Intelbras, importações), com uma lista do que cada campo aceita.
3. Texto: tirar espaços sobrando e limitar o tamanho. Números e dinheiro: faixa mínima e máxima. Documentos: dígito verificador. Arquivos: tipo e tamanho.
4. Um teste por formulário com dados malformados.

## H03 · Checkbox desalinhado em Configurações · Erro

**O que aconteceu:** em `/configuracoes/` há um checkbox longe do texto dele, e não dá para saber o que ele faz.

**Causa provável (a confirmar na tela):** a única caixa dessa aba é a "Limpar" do campo Logo, que o Django gera sozinho para apagar o logo já enviado. Ela sai sem o estilo do projeto, porque o modelo `core/_campo.html` foi feito para campos simples.

**O que fazer:** um modelo de campo próprio para arquivo, com o logo atual em miniatura e a opção "Remover logo" alinhada, e um estilo único de checkbox em `components.css` para todas as telas.

## H04 · Configurações de financiamento confusas · Erro + Melhoria

**O que aconteceu:**
- **H04a:** não fica claro se a taxa é mensal, anual ou outra coisa.
- **H04b:** falta a taxa de cadastro (TAC), que o mercado costuma cobrar.
- **H04c:** os impostos da operação (IOF) entram no valor financiado e mudam a parcela.

**Situação atual:** a taxa é mensal (D22). Isso só aparece no título do card ("% ao mês"). Os campos da tabela mostram só o prazo (12×, 24×...). Hoje a parcela é calculada sobre o valor do sistema, sem TAC e sem IOF, então sai **menor do que a real**.

**O que fazer:** mostrar "% ao mês" em cada campo, com o equivalente ao ano ao lado, calculado. Incluir a TAC e o IOF no valor financiado, num cálculo em `calculo.py` com teste. A proposta continua marcando a parcela como "aproximada".

**Perguntas:**
1. A TAC é um valor fixo em reais ou um percentual? Muda por banco?
2. O imposto é o IOF padrão (0,38% fixo mais 0,0082% ao dia, com teto de um ano) ou cada banco informa o seu?
3. No PDF, TAC e IOF aparecem separados para o cliente ou só embutidos na parcela?

## H05 · Municípios de Goiás · Melhoria

**O que o usuário pediu:** incluir os municípios de Goiás.

**Situação atual:** a carga vem de `core/dados/municipios_to.csv`, com os 139 municípios do Tocantins (D26). Goiás tem 246.

**O que isso puxa** (é maior do que parece):
- **Distribuidora e tarifa:** Goiás é atendido pela Equatorial Goiás, não pela Energisa TO. As tarifas (`TarifaVigente.distribuidora`), o Fio B e as bandeiras precisam existir para ela.
- **Iluminação pública:** cada município tem sua lei e suas faixas (`FaixaIluminacao`).
- **Irradiação:** baixar da NASA POWER para cada município novo (D27).
- **Proposta:** a distribuidora passa a vir do município, não mais fixa.

**Perguntas:**
1. O estado inteiro ou só a região que a Optimus atende?
2. Quais tipos de tarifa da Equatorial Goiás entram (B1 residencial, B2 rural, B3 comercial)?

## H06 e H07 · Busca e filtro do catálogo Intelbras · Melhoria

**O que o usuário pediu:** em `/orcamentos/catalogo/`, os resultados aparecem enquanto o usuário digita (H06), a lista atualiza ao escolher o segmento (H07) e o botão "Filtrar" sai.

**Situação atual:** é um formulário comum, com o botão "Filtrar" (`orcamentos/templates/orcamentos/catalogo.html`).

**O que fazer:** HTMX (já usado no editor do orçamento). A busca espera cerca de 0,3 s depois da última tecla, troca só a tabela e atualiza o endereço da página, para o "voltar" do navegador e o link copiado continuarem funcionando. Sem JavaScript, o formulário continua funcionando.

**O usuário pediu explicitamente:** o mesmo vale para o **catálogo solar** (`/propostas/catalogo/`), que também tem o botão "Filtrar".

## P2 · Premissa: busca e filtros dinâmicos em toda a aplicação

**O que o usuário pediu:** nenhuma lista com botão de filtrar ou atualizar. Busca e filtros atualizam na hora.

**Listas com filtro hoje:** clientes, propostas, orçamentos, catálogo Intelbras e catálogo solar.

**O que fazer:** registrar em `docs/decisoes.md` e no `CLAUDE.md`. Aplicar o mesmo padrão nas cinco listas, com um modelo parcial de tabela para cada uma.

## H08 · Página de detalhe do produto solar · Melhoria

**O que o usuário pediu:** reformular `/propostas/catalogo/<id>/` pensando na experiência de quem usa.
- **H08a:** a foto e o datasheet em destaque.
- **H08b:** só os campos do tipo do produto. Por exemplo, dados de módulo não aparecem em inversor nem em estrutura.

**Situação atual:** essa página é só o formulário de edição do gestor (`EquipamentoForm`), com todos os campos para todos os tipos. Não existe uma página "de ver" o produto.

**Fotos e datasheets no banco hoje:**

| Tipo | Itens | Com foto | Com datasheet |
|---|---|---|---|
| Módulo | 21 | 20 | 20 |
| Inversor | 69 | 68 | 66 |
| Microinversor | 10 | 10 | 9 |
| Estrutura | 42 | 42 | 1 |
| Cabo | 16 | 16 | 10 |
| Conector | 2 | 2 | 1 |
| Outro | 49 | 49 | 27 |

**Campos por tipo** (proposta inicial, a aprovar):
- **Módulo:** potência (W), dimensões, espessura da moldura, área.
- **Inversor:** potência, fase, tensão, número de MPPTs.
- **Microinversor:** potência, fase, módulos por micro.
- **Estrutura:** tipo de telhado, papel no kit, peças por embalagem.
- **Cabo e conector:** papel no kit, peças por embalagem.
- **Todos:** fabricante, modelo, código, distribuidor, preço e data do preço.

**O que fazer:** uma página para ver o produto (foto grande, datasheet aberto na própria página ou com botão em destaque, ficha só com os campos do tipo) e a edição, só para o gestor, mostrando também só os campos do tipo. Antes do código, um protótipo em HTML para aprovação, como na proposta v2. Produto sem foto ou sem datasheet mostra um espaço reservado.

## H09 · Mostrar ou esconder preço por item no orçamento Intelbras · Melhoria

**O que o usuário pediu:** uma opção em `/orcamentos/<id>/` para mostrar ou não os preços individuais no orçamento que vai ao cliente.

**O que fazer:** um campo no `Orcamento`, marcado na tela e respeitado no PDF.

**Perguntas:**
1. A opção vale para o orçamento inteiro ou item a item?
2. Escondendo o preço, a quantidade continua aparecendo?
3. Os subtotais por grupo (produtos, materiais, serviços) continuam aparecendo?

## H10 · Parcelamento no PDF do orçamento Intelbras · Melhoria

**O que o usuário pediu:** mostrar o parcelamento em até 21×, resumido: 3×, 6×, 12× e 21×.

**Situação atual:** o orçamento só tem o campo de texto "forma de pagamento".

**Perguntas:**
1. É cartão de crédito (maquininha) ou boleto/carnê?
2. Tem juros? Qual a taxa de cada prazo? Pela regra do projeto, quem cadastra é o gestor em Configurações.
3. Algum prazo sai sem juros (por exemplo, 3×)?
4. Os prazos 3, 6, 12 e 21 ficam fixos ou o gestor pode mudar?
5. O vendedor pode esconder o parcelamento num orçamento específico?

## H11 · Aviso de múltiplos desnecessário · Erro

**O que aconteceu:** o orçamento avisa "Distribuidor vende em múltiplos de N un." quando a quantidade não é múltipla.

**Causa (confirmada):** a regra de múltiplos (`qtd_multipla` da tabela Intelbras) só vale na compra do distribuidor junto à fábrica. O distribuidor vende unidade avulsa para a Optimus. O aviso está em `orcamentos/services/calculo.py:91`, e o selo "múltiplo N" está na busca de produtos (`_busca_produtos.html:18`).

**O que fazer:** registrar a correção da regra em `docs/decisoes.md` (revisa D13/D14). Tirar o aviso e o selo. A coluna pode continuar no catálogo como informação, ou sair também.

## H12 · Endereço no cadastro de cliente · Melhoria

**O que o usuário pediu:** campos de endereço, todos opcionais, com o máximo de preenchimento automático. E pesquisar o preenchimento pelo CPF.

**Situação atual:** o `Cliente` não tem endereço (`clientes/models.py`). Só a unidade consumidora tem, num campo de texto único.

**O que fazer:**
- **H12a:** CEP, rua, número, complemento, bairro, município e UF, todos opcionais. Digitando o CEP, o sistema preenche o resto pelo ViaCEP ou pela BrasilAPI (gratuitos, sem chave). É uma consulta à internet na hora do cadastro e precisa ser registrada como exceção à regra de "não consultar API na hora", que hoje vale para a proposta. Sem internet, o vendedor preenche à mão.
- **H12b, pesquisa sobre o preenchimento por documento:**
  - **CNPJ:** viável e gratuito, porque os dados de empresas são públicos (BrasilAPI, ReceitaWS). Traz razão social, endereço e telefone.
  - **CPF:** não há fonte pública e gratuita. As opções são pagas (Serpro, birôs de crédito) e exigem uma base legal da LGPD para consultar dados pessoais. A pesquisa vai levantar custo, termos e exigências, para o usuário decidir.

## H13 · Proposta não avança sem CPF · Bloqueia

**O que aconteceu:** no passo 2 (`/propostas/<id>/passo/2/`), o sistema não deixa avançar sem o CPF, e a proposta não pode ser concluída.

**Causa (confirmada no código):** em `propostas/forms.py`, quando o consumo vem da opção "Tenho a fatura", o CPF/CNPJ está na lista de campos obrigatórios. Isso segue D23 ("CPF/CNPJ só na proposta confirmada", e a proposta com fatura é a confirmada). O problema é que a própria fatura **não traz o CPF inteiro** (H14), então o vendedor com a fatura na mão não tem o dado. Além disso, se a IA preenche o CPF com asteriscos, a validação recusa ("CPF ou CNPJ só pode ter números").

Nas opções "Valor da conta" e "kWh por mês", o CPF não é exigido e o passo avança.

**O que fazer:** depende da pergunta abaixo. Em todos os casos entra um teste que cria uma proposta com fatura e sem CPF.

**Pergunta (decisão de negócio, muda D23):** onde o CPF passa a ser exigido?
- **(a)** Só na emissão da proposta confirmada. O passo 2 aceita a fatura sem CPF, e o passo 4 avisa que ele falta e bloqueia a emissão.
- **(b)** Em nenhum momento da proposta. O CPF fica para o contrato.
- **(c)** Continua no passo 2, mas com um aviso claro de que a fatura não traz o número e que é preciso pedir ao cliente.

## H14 · CPF escondido na fatura · Erro

**O que aconteceu:** a fatura traz o CPF parcialmente escondido (por exemplo `***.456.789-**`), e a IA não tem como ler o número inteiro.

**O que fazer:** em `propostas/services/leitura_ia.py`, reconhecer o CPF incompleto, deixar o campo vazio e mostrar o aviso "A fatura não traz o CPF completo. Peça ao cliente." Nunca gravar um CPF pela metade. Teste com a resposta da IA contendo asteriscos.

## H15 · Leitura da fatura atualiza o cadastro de clientes · Melhoria

**O que o usuário pediu:**
- **H15a:** aproveitar a leitura da fatura para completar ou atualizar o endereço do cliente.
- **H15b:** criar ou atualizar o cliente e a unidade consumidora automaticamente a partir da fatura.

**Situação atual:** a leitura só preenche os campos do passo 2 (D37: "nada é gravado direto"). O endereço da fatura vai para a unidade consumidora, não para o cliente.

**O que fazer:** depende de H12 (endereço no cliente) e das perguntas abaixo. Muda D37, então precisa ser registrado antes.

**Perguntas:**
1. O vendedor confere antes de gravar (vê os dados e aceita ou corrige) ou grava direto?
2. Como reconhecer o cliente já cadastrado, se o CPF vem incompleto? Pelo número da UC, pelo nome, pelo telefone?
3. Quando o dado da fatura é diferente do cadastro: substituir, perguntar ou manter?
4. O endereço da fatura (o da instalação) vai para o cliente, só para a UC ou para os dois? Podem ser diferentes, por exemplo quando o cliente mora na cidade e instala na fazenda.

## H16 · Dashboard na página inicial · Melhoria

**O que o usuário pediu:** um dashboard completo em `/`.

**Situação atual:** `core/inicio.html` tem 19 linhas, sem números. O plano já previa o painel do gestor (A19, rodada 6 antiga) e a lista "ligar hoje" (A20), que entram aqui.

**Indicadores sugeridos** (a escolher):
- **Propostas solares:** emitidas, aceitas e perdidas no mês, conversão, kWp e valor, motivos de perda, propostas vencendo em 3 dias, desconto médio.
- **Orçamentos Intelbras:** abertos, aprovados, valor do mês.
- **Por vendedor:** propostas, aceites, valor.
- **Parados:** propostas e orçamentos sem retorno há N dias, e a lista "ligar hoje".
- **Alertas do gestor:** tabela Intelbras desatualizada, tarifa ANEEL antiga, catálogo Belenus velho.

**Perguntas:**
1. Quais indicadores entram na primeira versão?
2. O vendedor e o gestor veem o mesmo painel? O vendedor vê só os números dele?

Antes do código, um protótipo para aprovação.

## H17 · Tela de importação da tabela Intelbras · Melhoria (a confirmar)

**O que o usuário perguntou:** como o sistema trata produtos novos e encerrados na importação.

**Como funciona hoje** (`orcamentos/importacao.py`):
- **Novo:** é cadastrado e entra na contagem de "novos" do resumo.
- **Já existia:** os preços são atualizados, e o resumo mostra as 30 maiores variações.
- **Em encerramento** (aba "Encerramentos" da planilha): continua vendável, com aviso e substituto no orçamento.
- **Saiu da tabela:** não é apagado. Fica inativo, some da busca do orçamento e volta sozinho se reaparecer numa tabela futura. Orçamentos antigos guardam a própria cópia e mostram o aviso "fora da tabela".

**Possível achado:** a tela de importação não explica nada disso, e o resumo só mostra números, sem listar os produtos novos.

**Pergunta:** isso vira correção (texto explicativo na tela e lista de novos e de que saíram no resumo) ou fica como está?
