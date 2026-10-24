# meu_erp — Optimus Energia Solar

ERP interno da Optimus Energia Solar (Gurupi-TO): propostas de energia solar e orçamentos da revenda Intelbras. Ver `CLAUDE.md` para as regras do projeto, `docs/spec-proposta-v2.md` para a proposta solar (o motor de cálculo e o PDF seguem `docs/spec-fase1.md`), `docs/spec-orcamentos.md` para os orçamentos e `docs/decisoes.md` para o porquê de cada regra.

## Instalação (Windows / PowerShell)

Pré-requisito: Python 3.12 ou mais novo instalado.

```powershell
# 1. Criar o ambiente virtual do projeto (uma vez só)
python -m venv .venv

# 2. Ativar o ambiente virtual (todas as vezes, antes de usar o projeto)
.venv\Scripts\Activate.ps1

# 3. Instalar as dependências
pip install -r requirements.txt

# 4. Aplicar as migrações do banco (cria o db.sqlite3)
python manage.py migrate

# 5. Criar o primeiro usuário (o gestor). Os outros são criados no menu Usuários.
python manage.py createsuperuser

# 6. Rodar o servidor de desenvolvimento, acessível pela rede local
python manage.py runserver 0.0.0.0:8000
```

Para os PDFs (proposta e orçamento), instalar o Chromium do Playwright uma única vez:

```powershell
python -m playwright install chromium
```

Depois de rodar o passo 6, abra no navegador e entre com o usuário criado:
- Neste PC: http://localhost:8000/
- De outro PC na mesma rede: `http://<IP-deste-PC>:8000/` (ver o IP com `ipconfig`, procurar "Endereço IPv4").

## Atualizar o sistema (depois de cada `git pull`)

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # só muda quando entra dependência nova
python manage.py migrate          # aplica as mudanças do banco; não apaga dados
```

Depois, pare o servidor (Ctrl+C) e rode de novo.

## Dados oficiais (o gestor atualiza)

A proposta nunca consulta a internet na hora: usa o que está no banco, com a fonte e a data.

- **Tarifas e bandeiras (ANEEL):** Configurações → Tarifas e bandeiras → "Atualizar da ANEEL". Depois de cada reajuste, confira os tributos e o Fio B de cada tarifa. Pelo PowerShell: `python manage.py atualizar_tarifas`.
- **Irradiação (NASA POWER):** Configurações → Municípios → "Buscar na NASA POWER" (20 municípios por clique). Pelo PowerShell: `python manage.py atualizar_irradiacao --uf TO`.
- **Iluminação pública:** Configurações → Municípios → "Editar tabela" do município; atualize o valor da unidade fiscal todo ano.
- **Taxas de financiamento, TAC e IOF:** Configurações → Financiamento.
- **Parcelamento do orçamento Intelbras:** Configurações → Parcelamento (Intelbras).
- **Outro estado (ex.: Goiás):** cadastre a distribuidora no admin (Distribuidoras, com a sigla da ANEEL), importe os municípios com `python manage.py importar_municipios GO`, inclua "GO" em Configurações → Empresa → Estados atendidos e atualize tarifas e irradiação (D47).

## Leitura de fatura e cotação por IA

Opcional. Com a chave da API no `.env` (`GEMINI_API_KEY=...`), os botões "Ler a fatura com IA" e "Ler a cotação com IA" preenchem os campos; o vendedor confere e salva (D37). Sem a chave, os botões avisam e tudo continua sendo digitado. Antes de usar com faturas de clientes reais, ative o nível pago da chave (no gratuito o Google pode usar o conteúdo).

## Testes

```powershell
python -m pytest
```

## Orçamentos Intelbras — primeiro uso

1. **Catálogo Intelbras → Importar tabela**: enviar o `.xlsb` baixado do Portal Sou Parceiro (repetir a cada nova tabela, dias 1 e 15).
2. **Admin → Parâmetros de orçamento**: conferir o markup padrão, a validade, a garantia e as observações.
3. **Admin → Markups por segmento** (opcional): markup diferente por segmento (ex.: `CFTV IP` 40%).
4. **Admin → Itens próprios**: cadastrar os serviços (instalação por ponto, configuração…) e os materiais de outras marcas.
5. **Orçamentos → + novo orçamento**.

## Usuários

- Todo o sistema exige login. O usuário criado no passo 5 (superusuário) cria os demais em **Usuários** (admin do Django): botão "Adicionar usuário", depois nome e senha.
- Para dar acesso de gestor (Configurações, catálogo, importar tabela), marque o grupo **gestor** no usuário.

## Produção (PC dedicado na rede local)

```powershell
# 1. Uma vez: copiar .env.exemplo para .env e colar uma SECRET_KEY nova (instruções dentro do arquivo).
copy .env.exemplo .env
notepad .env

# 2. Rodar
waitress-serve --port=8000 config.wsgi:application
```

Acesso pelo celular fora da loja: por VPN (ex.: Tailscale), nunca abrindo a porta do PC no roteador (D36).

**Backup:** com o servidor parado, copiar `db.sqlite3` e a pasta `media/` (PDFs, faturas, fotos e datasheets) para outro disco ou para a nuvem. Com o servidor ligado, copiar também `db.sqlite3-wal` e `db.sqlite3-shm`. Faça antes de cada `git pull` com migração nova.

## Estrutura

Ver a seção "Estrutura" em `CLAUDE.md`.
