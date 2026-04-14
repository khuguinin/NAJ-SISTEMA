# Guia de implantação — NAJ Sistema Online
## Streamlit Cloud + Supabase (PostgreSQL gratuito)

---

## PASSO 1 — Criar o banco de dados no Supabase (gratuito)

1. Acesse **supabase.com** e crie uma conta gratuita
2. Clique em **"New Project"**
   - Nome: `naj-iuna`
   - Senha do banco: crie uma senha forte e **anote ela**
   - Região: **South America (São Paulo)**
3. Aguarde o projeto ser criado (~2 minutos)
4. Vá em **Project Settings → Database → Connection string**
   - Marque **"Use connection pooling"** e **Mode = Session**
   - Copie a URI completa (começa com `postgresql://...`)
   - Substitua `[YOUR-PASSWORD]` pela senha que você criou

> Guarde essa URI — você vai usar no Passo 3 e no Passo 4.

---

## PASSO 2 — Colocar o código no GitHub (gratuito)

1. Acesse **github.com** e crie uma conta gratuita
2. Clique em **"New repository"**
   - Nome: `naj-sistema`
   - Visibilidade: **Private** (importante!)
   - Clique em **Create repository**
3. Faça upload dos arquivos abaixo clicando em **"uploading an existing file"**:
   - `app_cloud.py` → **renomeie para `app.py`** ao fazer upload
   - `logo_naj.jpg`
   - `requirements.txt`
   - `.gitignore`
   - A pasta `.streamlit/` com o `config.toml` (sem o `secrets.toml`)

> ⚠️ NUNCA faça upload do `secrets.toml` — ele fica só na sua máquina.

---

## PASSO 3 — Configurar o secrets.toml localmente

Edite o arquivo `.streamlit/secrets.toml` (que NÃO vai ao GitHub):

```toml
DATABASE_URL = "postgresql://postgres.XXXX:SUA_SENHA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
```

Substitua pela URI real que você copiou no Passo 1.

---

## PASSO 4 — Publicar no Streamlit Cloud (gratuito)

1. Acesse **share.streamlit.io** e entre com sua conta GitHub
2. Clique em **"New app"**
3. Preencha:
   - Repository: `seu-usuario/naj-sistema`
   - Branch: `main`
   - Main file path: `app.py`
4. Clique em **"Advanced settings"** e em **Secrets** cole:
   ```
   DATABASE_URL = "postgresql://postgres.XXXX:SUA_SENHA@..."
   ```
5. Clique em **"Deploy!"**
6. Aguarde ~2 minutos. O sistema ficará acessível em:
   ```
   https://naj-sistema.streamlit.app
   ```
   (ou similar — o Streamlit gera o endereço automaticamente)

---

## PASSO 5 — Primeira execução (cria as tabelas)

Na primeira vez que acessar o sistema, ele cria as tabelas automaticamente no Supabase. Basta fazer login com qualquer usuário e navegar pelas telas.

Você pode verificar que as tabelas foram criadas no Supabase em:
**Table Editor** → deve aparecer `processos`, `demandas`, `atendimentos`

---

## Como os outros computadores acessam

Simplesmente abrem o navegador e acessam o endereço gerado pelo Streamlit Cloud, por exemplo:
```
https://naj-sistema.streamlit.app
```

Funciona em qualquer computador, celular ou tablet, de qualquer lugar com internet.

---

## Estrutura de arquivos no GitHub

```
📂 naj-sistema/  (repositório privado)
├── app.py              ← app_cloud.py renomeado
├── logo_naj.jpg
├── requirements.txt
├── .gitignore
└── .streamlit/
    └── config.toml     ← SEM o secrets.toml
```

---

## Usuários e senhas (não mudam)

| Usuário   | Senha       | Perfil   |
|-----------|-------------|----------|
| portaria  | portaria123 | Portaria |
| kleber    | kleber123   | Assessor |
| gustavo   | gustavo123  | Assessor |
| erikson   | erikson123  | Assessor |

---

## Limites do plano gratuito

| Serviço         | Limite gratuito                          |
|-----------------|------------------------------------------|
| Streamlit Cloud | Apps ilimitados, 1 GB de RAM             |
| Supabase        | 500 MB de banco, 5 GB de transferência   |

Para o uso do NAJ (escritório pequeno), esses limites são mais do que suficientes.
