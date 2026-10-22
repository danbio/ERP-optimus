# meu_erp — Optimus Energia Solar

ERP interno da Optimus Energia Solar (Gurupi-TO). Ver `CLAUDE.md` para as regras do projeto e `docs/spec-fase1.md` para a especificação da fase atual.

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

**Backup:** com o servidor parado, copiar `db.sqlite3` e a pasta `media/`. Com o servidor ligado, copiar também `db.sqlite3-wal` e `db.sqlite3-shm`.

## Estrutura

Ver a seção "Estrutura" em `CLAUDE.md`.
