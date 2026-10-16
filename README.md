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

# 5. Rodar o servidor de desenvolvimento, acessível pela rede local
python manage.py runserver 0.0.0.0:8000
```

Depois de rodar o passo 5, abra no navegador:
- Neste PC: http://localhost:8000/
- De outro PC na mesma rede: `http://<IP-deste-PC>:8000/` (ver o IP com `ipconfig`, procurar "Endereço IPv4").

## Produção (PC dedicado na rede local)

```powershell
pip install waitress
waitress-serve --port=8000 config.wsgi:application
```

## Estrutura

Ver a seção "Estrutura" em `CLAUDE.md`.
