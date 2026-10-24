# Parecer sobre o relatório e o plano do teste humano · 24/10/2026

**Base:** `docs/relatorio-teste-humano-2026-10-24.md` e `docs/plano-correcoes.md` (versões locais, sem commit) conferidos contra o código em `1cef85a` (main, fim da rodada 5). Referências `arquivo:linha` desse commit.

**Resultado:** 14 achados confirmados, 3 confirmados com correção de escopo (H05, H14, H15), nenhum refutado por inteiro. O plano está bem montado; proponho 7 ajustes de ordem e escopo e 6 itens que faltam.

---

## 1. Achados, um a um

| Código | Veredito | Evidência e observação |
|---|---|---|
| **H01** | Confirmado | `config/urls.py:31-34`: `arquivo_estatico` serve só de `BASE_DIR / "static"`. O CSS do admin está em `django/contrib/admin/static/`. **Detalhe de implementação:** `django.contrib.staticfiles.views.serve` recusa servir com `DEBUG=0` (exige `insecure=True`); o caminho simples é `finders.find(caminho)` e devolver o arquivo achado com `FileResponse`/`serve` da pasta dele. Sem dependência nova (WhiteNoise seria a alternativa padrão, mas é dependência). |
| **H02** | Confirmado, com ressalva | `core/forms.py:64-82`: nenhum `clean_*`. CNPJ (`core/models.py:27`) e telefone (`:29`) são texto livre, embora `limpar_cpf_cnpj` e `limpar_telefone` existam em `core/validacoes.py:65` e `:92`. **Ressalva:** o e-mail já é validado (`EmailField`, `core/models.py:30`) e o Django já tira espaços das pontas dos textos (`strip=True` padrão). O que falta nos textos é limite de tamanho (os `TextField` não têm) e limpar linhas vazias nas listas "um por linha". `validade_padrao_dias` (`core/models.py:40`) aceita 0 ou 9999: é a mesma trava do **A22**. |
| **P1** | Confirmado | D24 (`docs/decisoes.md:142`) fala só da proposta e do cliente. São 19 formulários e 26 `clean*` no projeto; a varredura precisa de uma tabela campo × regra para não virar "achismo". |
| **H03** | Confirmado, causa exata | O widget de arquivo do Django (`ClearableFileInput`) gera "Atualmente: link · checkbox · Limpar · Modificar: arquivo". Em `static/css/components.css:106` a regra `.campo input { width: 100% }` estica o checkbox para a linha inteira, e `.campo label { display: block }` (`:98`) joga o "Limpar" para outra linha. Por isso a caixa fica longe do texto. A classe `.campo--checkbox` (`app.css:372`) existe, mas não é aplicada a esse campo. |
| **H04** | Confirmado | `propostas/services/calculo.py:382-399`: `parcela_price(valor, taxa, meses)` sobre o valor do sistema, sem TAC nem IOF. Título "% ao mês" só no card (`config_financiamento.html:5`). Ver correções técnicas na seção 3. |
| **H05** | Confirmado, escopo corrigido | Só `core/dados/municipios_to.csv`. **Correção:** bandeira tarifária é nacional (ANEEL), a mesma para todas as distribuidoras; não precisa de bandeira por distribuidora. **O que o relatório não viu:** `TarifaVigente.vigentes()` (`propostas/models.py:314-319`) e `dados_oficiais.py:114` ignoram a distribuidora: no dia em que entrar a Equatorial, a proposta passa a pegar a tarifa mais recente de qualquer uma. Também fixos em "Energisa TO": `propostas/models.py:275`, `clientes/models.py:54`, `propostas/views/documento.py:130`, `config_tarifas.html:6` e `core/dados_oficiais.py:23` (sigla ANEEL). |
| **H06/H07** | Confirmado | Botão "Filtrar" em `orcamentos/templates/orcamentos/catalogo.html:26` e `propostas/templates/propostas/catalogo/equipamentos.html:15`. |
| **P2** | Confirmado | As cinco listas com `<form method="get">`: clientes, propostas, orçamentos, catálogo Intelbras e catálogo solar. Atenção: propostas tem paginação de 50 (A28); ao filtrar, a página volta para 1. |
| **H08** | Confirmado | `propostas/urls.py:30` leva direto ao formulário de edição; `EquipamentoForm` (`propostas/forms.py:31-37`) tem todos os campos de todos os tipos. A view é `@so_gestor` (`propostas/views/catalogo.py:52`): **o vendedor hoje não consegue ver o produto**, recebe a página "só gestor". Reforça a página "de ver". |
| **H09** | Confirmado | `orcamentos/templates/orcamentos/pdf/orcamento.html:58-59` imprime preço unitário e total sempre. |
| **H10** | Confirmado | Só o texto livre `Orcamento.forma_pagamento` (`orcamentos/models.py:151`). |
| **H11** | Confirmado | Aviso em `orcamentos/services/calculo.py:91-92`, selo em `_busca_produtos.html:18`, coluna em `catalogo.html:50`. **Faltou no plano:** dois testes afirmam o aviso e precisam mudar junto (`tests/test_orcamentos_calculo.py:63`, `tests/test_orcamentos_fluxo.py:85`). |
| **H12** | Confirmado | `Cliente` sem endereço (`clientes/models.py:7-17`). **Mas** o cliente já tem `municipio` (FK para `Municipio`, `:13`): o endereço deve reaproveitar essa FK em vez de criar "município" e "UF" em texto. O ViaCEP devolve o código IBGE, que casa direto com `Municipio.codigo_ibge`. |
| **H13** | Confirmado | `propostas/forms.py:281`: `cpf_cnpj` na lista de obrigatórios da origem "fatura". `core/validacoes.py:70-71` recusa asterisco. **Correção:** quem manda asterisco é o vendedor copiando a fatura à mão, não a IA (ver H14). Com a leitura por IA, o bloqueio aparece como "Preencha este campo" no CPF vazio, sem explicar por quê. |
| **H14** | **Já resolvido em boa parte** | `propostas/services/leitura_ia.py:111` e `:121`: a resposta da IA passa por `so_digitos` e, se não tiver 11 ou 14 dígitos, o CPF fica vazio. Já há teste: `tests/test_leitura_ia.py:53-56` (`"***.982.247-**"` → vazio). **O que falta:** (1) o aviso ao vendedor ("a fatura não traz o CPF completo, peça ao cliente"), (2) dizer no esquema (`leitura_ia.py:26`) que CPF mascarado volta vazio, para a IA não "completar" com zeros ou inventar dígitos. |
| **H15** | Confirmado, escopo menor | **Já existe:** ao salvar o passo 2 com fatura, o sistema cria ou atualiza a UC pelo número e grava a `FaturaReferencia` (`propostas/views/passos.py:224-243`), e compara o titular lido com o nome do cliente (`passos.py:290-292`). **O que falta de fato:** endereço no cliente (depende de H12) e usar a fatura antes do passo 1 (hoje a leitura é no passo 2, quando o cliente já existe). **Risco não citado:** `passos.py:222` grava o CPF do titular no cliente mesmo quando o titular é outra pessoa (cônjuge, pai, empresa). |
| **H16** | Confirmado | `core/templates/core/inicio.html` (21 linhas, sem números). `Proposta` já guarda `emitida_por`, `aceita_por`, `perdida_por` (`propostas/models.py:173-183`): o "por vendedor" do solar sai sem esperar o A20. `Orcamento` não tem usuário nenhum (`orcamentos/models.py:133-161`): o "por vendedor" do Intelbras exige campo novo. |
| **H17** | Confirmado, quase pronto | `orcamentos/importacao.py:80` já calcula `codigos_que_sairam`, mas `importar.html:23-31` só mostra os números. Os códigos novos não são guardados. É correção pequena, sem pergunta de negócio: proponho entrar já. |

**Fora do teste, achado na conferência:**
- `#fff` literal em 9 lugares de `app.css` e `components.css` (ex.: `components.css:114`), contra a regra 1 de CSS do `CLAUDE.md`.
- Texto de ajuda desatualizado: `propostas/models.py:286` diz que "a ANEEL não publica" o Fio B; desde D32 sabemos que publica.
- D37 (`docs/decisoes.md`, item LGPD): a chave Gemini está no nível gratuito, em que o Google pode usar o conteúdo. Se a fatura de hoje é de cliente real, isso já conta. O plano não tem item para ativar o nível pago antes do uso com clientes.

---

## 2. Ajustes no plano

1. **Rodada 6 enxuga e ganha o H17.** H14 vira só "aviso + instrução no esquema". H11 inclui os dois testes. H01 com a nota do `finders.find`. H17 (lista de novos e de saídos na importação) entra aqui, porque o dado já existe.
2. **A22 sai do painel e vai para a rodada 7.** É validação de Configurações, o mesmo trabalho do H02/P1 (`validade_padrao_dias` é campo do `EmpresaForm`).
3. **A29 sobe para antes do uso com cliente** (rodada 7 ou 8). O modo cliente manda ao navegador o custo do kit e a mão de obra escondidos: qualquer cliente curioso vê no celular do vendedor. É mais urgente que o dashboard.
4. **H10 junta com H09 na rodada do orçamento Intelbras.** Os dois mexem no mesmo PDF e no mesmo modelo (`Orcamento`); uma migração só. A rodada 9 fica só com o financiamento solar.
5. **Rodada 8: H12b sem pesquisa de CPF.** Não existe fonte pública e gratuita de CPF com endereço; as pagas pedem base legal da LGPD e contrato. Recomendo descartar agora e registrar o motivo, em vez de gastar uma pesquisa. CNPJ pela BrasilAPI (gratuita) continua. Para CEP, consultar o ViaCEP **pelo navegador** (JS puro), não pelo servidor: o servidor não depende de internet e a exceção à regra "nada de API na hora" fica restrita ao cadastro.
6. **Rodada 12: A20 antes do H16** e o painel nasce com `eh_gestor` (`core/permissoes.py:10`) decidindo o que cada um vê. Orçamento Intelbras precisa de campo de vendedor se entrar no "por vendedor".
7. **Rodada 13 (Goiás) com a lista concreta:** `vigentes()` e `dados_oficiais` filtrando por distribuidora (vale corrigir já na rodada 6, é bug latente), sigla ANEEL da Equatorial Goiás, os 5 pontos fixos em "Energisa TO", tributos de GO (a alíquota já é por linha de tarifa, então não precisa de campo novo), iluminação por município e distribuidora vindo da UC/município. Sem bandeira por distribuidora.

**Itens que faltam no plano:**
- Ativar o nível pago da chave Gemini (ou trocar o provedor) antes de qualquer fatura de cliente real (D37). Item de configuração, não de código.
- Rodada 5: o teste de hoje foi com fatura real da Energisa? Se foi, o item "testes com faturas reais" pode ser marcado na parte da fatura; a cotação continua pendente.
- CPF do titular diferente do cliente (`passos.py:222`), junto com o H15.
- Trocar os `#fff` por token e corrigir o texto do Fio B (rodada 14).
- H01 com teste automatizado que pede `/static/admin/css/base.css` com `DEBUG=0`.
- P2: filtro volta à página 1 e mantém os filtros na paginação.

---

## 3. Correções técnicas no H04 (financiamento)

- **IOF não é um percentual sobre o total.** Em CDC para pessoa física: 0,38% sobre o valor + 0,0082% ao dia (pessoa jurídica: 0,0041% ao dia), com teto de 365 dias, calculado **sobre cada parcela amortizada pelos dias até o vencimento dela**. Aplicar 0,0082% × 365 sobre o valor inteiro superestima. Para "parcela aproximada" dá para simplificar, mas a simplificação precisa estar escrita na decisão.
- **IOF e TAC financiados mudam o valor da parcela de forma circular** (o IOF incide sobre o valor que já inclui o IOF). Os bancos resolvem isso por iteração; para uso interno, uma fórmula fechada aproximada basta.
- **Pergunta que falta:** a taxa que o gestor cadastra é a taxa nominal do banco ou o **CET**? Se for o CET, TAC e IOF já estão dentro e somar de novo conta duas vezes.
- **"Melhor banco"** (`calculo.py:396-399`) hoje compara parcelas sem custos. Com TAC por banco, a escolha precisa ser feita depois de somar TAC e IOF.
- O caso Alesio não testa parcela (`tests/test_caso_referencia.py`), então essa mudança não mexe no teste de referência. O `registro` da emissão (D36) precisa gravar TAC e IOF usados.

---

## 4. Perguntas pendentes, com recomendação

| Item | Pergunta | Recomendo |
|---|---|---|
| H13 | Onde o CPF passa a ser exigido | **(a)** só na emissão da confirmada, com aviso no passo 4 |
| H14 | — | sem pergunta |
| H04 | TAC fixa ou %, por banco; IOF padrão ou do banco; taxa nominal ou CET; separado ou embutido no PDF | TAC por banco (R$ ou %); IOF padrão PF/PJ calculado; PDF mostra só a parcela "aproximada, com IOF e TAC" |
| H09 | Inteiro ou por item; quantidade e subtotais | orçamento inteiro; quantidade e subtotais por grupo continuam |
| H10 | Cartão ou boleto; juros por prazo; quais sem juros; prazos fixos; vendedor esconde | taxas por prazo em Configurações; prazos editáveis pelo gestor; vendedor pode esconder |
| H12b | Pesquisar CPF pago | não pesquisar; só CNPJ |
| H15 | Conferência, como achar o cliente, conflito, qual endereço | sempre conferir antes de gravar; achar pela UC; conflito pergunta; endereço da fatura vai para a UC, e para o cliente só se ele estiver vazio |
| H16 | Indicadores da v1; painel único ou por perfil | protótipo com os indicadores do A19; vendedor vê os dele, gestor vê todos |
| H17 | Entra ou não | entra na rodada 6 |
| H05 | Estado inteiro ou região; tipos de tarifa | só os municípios atendidos; B1, B2 e B3 |
