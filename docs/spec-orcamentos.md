# Especificação: Orçamentos da revenda Intelbras

**Objetivo:** montar, no ERP, o orçamento de um projeto de segurança, redes ou energia com produtos Intelbras, materiais e serviços, e emitir o PDF no padrão visual da Optimus. Decisões: D12 a D15 em `docs/decisoes.md`.

**Fora do escopo:** Solar ON GRID (Plataforma Solar Intelbras), locação mensal, impostos sobre a venda, kits/modelos reutilizáveis, integração com o Registro de Projeto do Portal Sou Parceiro.

---

## 1. Models (`orcamentos/models.py`)

| Model | Campos principais | Observação |
|---|---|---|
| `ParametrosOrcamento` (registro único) | `uf_destino`, `markup_padrao`, `validade_padrao_dias`, `forma_pagamento_padrao`, `prazo_padrao`, `garantia_padrao`, `observacoes_padrao` | editado pelo admin |
| `MarkupSegmento` | `segmento` (único), `markup` (%) | sobrepõe o padrão |
| `TabelaPreco` | `referencia`, `arquivo`, `uf_destino`, `importada_em`, `resumo` (JSON) | um registro por importação |
| `Produto` | `codigo` (único), `descricao`, `resumo`, `bu`, `segmento`, `familia`, `uf_origem`, `ipi`, `icms`, `psd`, `pscf`, `qtd_multipla`, `preco_referencia`, `observacoes`, `ncm`, `ativo`, `substituto`, `tabela` | **custo = PSD** |
| `ItemProprio` | `tipo` (material/serviço), `descricao`, `unidade`, `custo`, `preco`, `ativo` | catálogo próprio |
| `Orcamento` | `numero` (`ORC-2026-0001`), `versao`, `origem`, `cliente`, `titulo`, `local_instalacao`, `status`, `emissao`, `validade_dias`, `forma_pagamento`, `prazo_execucao`, `garantia`, `observacoes`, `desconto_pct`, `projeto_registrado`, `numero_registro`, `tabela_referencia`, `total`, `pdf` | só `rascunho` é editável |
| `ItemOrcamento` | `orcamento`, `tipo` (intelbras/material/serviço), `produto` (opcional), `codigo`, `descricao`, `unidade`, `quantidade`, `custo_unitario`, `preco_unitario`, `pscf_unitario`, `qtd_multipla`, `ativo_na_tabela`, `substituto`, `ordem` | snapshot no momento da inclusão |

## 2. Serviços (funções puras, sem Django)

- `services/tabela_intelbras.py` → `ler_tabela(caminho, uf_destino) -> LeituraTabela`. Lê as abas `Tabela`, `Encerramentos` e `Orientacoes` e localiza as colunas pelo **nome do cabeçalho**, não pela posição.
- `services/calculo.py`
  - `ler_decimal("1.234,56")`
  - `preco_por_markup(custo, markup)` / `markup_por_preco(custo, preco)`
  - `markup_para(segmento, markups, padrao)`
  - `resumir(linhas, desconto_pct) -> Resumo` com os totais por tipo, desconto, custo, margem bruta e os alertas

**Alertas:**
- Item sem custo (PSD zerado).
- Preço abaixo do custo.
- Preço acima do PSCF (informativo).
- Quantidade que não é múltipla da embalagem de venda do distribuidor.
- Produto encerrado ou fora da tabela atual (com o substituto, se houver).
- Desconto que deixa o total abaixo do custo.

## 3. Telas

| Tela | Conteúdo |
|---|---|
| Lista | número/versão, cliente, título, total, status, emissão; filtros |
| Novo | cliente (selecionar ou cadastrar) + título → abre o editor |
| Editor | dados gerais · busca Intelbras (código/descrição, HTMX) · busca de itens próprios · item avulso · tabela de itens com qtd/markup/preço editáveis ao vivo · painel de totais e alertas |
| Preview | HTML do PDF |
| Emitir | gera o PDF, congela e muda o status para `emitido` |
| Revisar | copia o orçamento para uma nova versão em rascunho |
| Catálogo | busca e filtros por segmento, última importação |
| Importar tabela | upload do .xlsb e resumo (novos, preços alterados, encerrados) |

## 4. PDF

A4, no padrão da proposta Alesio: faixa navy no topo, logo e "ORÇAMENTO Nº X · CLIENTE"; bloco de título; cartão navy com o cliente, o número, a emissão e a validade. Os itens vêm agrupados em Equipamentos Intelbras, Materiais e Serviços. Depois vêm o cartão "Investimento total", a tabela de condições, o aceite e o rodapé com os dados da empresa e `n/total`.
