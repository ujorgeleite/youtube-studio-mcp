# Guia de configuração — credenciais e integrações

Passo a passo para deixar o `youtube-studio-mcp` funcionando com o **seu** canal do
YouTube e conectado ao Claude Code. Tempo estimado: ~10 minutos.

## Visão geral

| O quê | Onde fica | Obrigatório |
|---|---|---|
| Projeto no Google Cloud com a **YouTube Data API v3** ativada | Google Cloud Console | sim |
| **OAuth Client ID** do tipo *Desktop app* (`client_secret.json`) | `~/.youtube-studio-mcp/client_secret.json` | sim |
| Token de acesso do usuário (`token.json`) | `~/.youtube-studio-mcp/token.json` (gerado pelo `make auth`) | sim |
| Registro do servidor no Claude Code | `claude mcp add` | para usar via Claude |

> **Não é usada API key.** Uma API key do Google só acessa dados públicos. Os dados do
> *seu* canal (`channels.list?mine=true`) exigem **OAuth**, que é o que este projeto usa.
> Se você já criou uma API key, ela não é necessária aqui.

---

## 0. Pré-requisitos

- Conta Google que é **dona (ou gerente) do canal** do YouTube.
- Python 3.11+ e `make`.
- Projeto instalado:

```bash
make install
```

---

## 1. Criar um projeto no Google Cloud

1. Acesse <https://console.cloud.google.com/>.
2. No seletor de projetos (topo da página) → **New project**.
3. Nome: `youtube-studio-mcp` (qualquer nome serve) → **Create**.
4. Confirme que o novo projeto está **selecionado** no topo antes de seguir.

## 2. Ativar a YouTube Data API v3

1. Acesse <https://console.cloud.google.com/apis/library/youtube.googleapis.com>
   (ou **APIs & Services → Library** e busque "YouTube Data API v3").
2. Clique em **Enable**.

## 3. Configurar a tela de consentimento OAuth

No menu: **APIs & Services → OAuth consent screen** (em consoles mais novos aparece como
**Google Auth Platform**). Clique em **Get started** se for a primeira vez.

1. **App information / Branding**
   - App name: `youtube-studio-mcp`
   - User support email: seu e-mail
2. **Audience**: selecione **External**.
3. **Contact information**: seu e-mail → aceite os termos → **Create**.
4. **Audience → Test users → Add users**: adicione o **e-mail da conta Google que você
   usa para entrar no YouTube**. ⚠️ Sem isso o login falha com `access_denied`.
5. (Recomendado) **Data Access → Add or remove scopes**: adicione
   `https://www.googleapis.com/auth/youtube.readonly` → **Save**.

> O app fica em modo **Testing**, o que é o correto para uso pessoal. Não é preciso
> enviar para verificação do Google.

## 4. Criar o OAuth Client ID

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   (ou **Google Auth Platform → Clients → Create client**).
2. Application type: **Desktop app**. ⚠️ Não use "Web application" — o fluxo local
   (`localhost` com porta aleatória) só funciona com Desktop app.
3. Name: `youtube-studio-mcp-cli` → **Create**.
4. Clique em **Download JSON**.

## 5. Salvar o `client_secret.json`

```bash
mkdir -p ~/.youtube-studio-mcp
mv ~/Downloads/client_secret_*.json ~/.youtube-studio-mcp/client_secret.json
chmod 600 ~/.youtube-studio-mcp/client_secret.json
```

Para usar outro caminho, defina `YTS_CLIENT_SECRET=/caminho/para/client_secret.json`.

## 6. Autenticar (gera o `token.json`)

```bash
make auth
```

1. O navegador abre na tela de login do Google.
2. Escolha a **conta** e, se aparecer, o **canal** (contas com Brand Account pedem para
   escolher o canal — escolha o que você quer consultar).
3. Aviso **"Google hasn't verified this app"** → **Continue** (é esperado em modo Testing).
4. Autorize o acesso de leitura ao YouTube → **Continue**.
5. No terminal: `Authenticated. Token saved to ~/.youtube-studio-mcp/token.json`.

## 7. Validar pelo terminal

```bash
make overview      # ou: make shell  →  yt> overview
```

Saída esperada:

```json
{
  "channel_id": "UC...",
  "title": "Seu Canal",
  "subscriber_count": 1234,
  "view_count": 56789,
  "video_count": 42,
  "uploads_playlist_id": "UU..."
}
```

## 8. Conectar ao Claude Code

```bash
make mcp-add       # = claude mcp add youtube-studio -- "<projeto>/.venv/bin/youtube-studio-mcp" serve
claude mcp list    # deve listar youtube-studio como conectado
```

Dentro do Claude Code, rode `/mcp` para ver o status e peça, por exemplo:
*"me mostra o overview do meu canal do YouTube"*.

> Faça o passo 6 **antes**: o servidor MCP nunca abre o navegador (isso quebraria o
> stdio). Sem token, a tool responde pedindo `youtube-studio-mcp auth`.

---

## Variáveis de ambiente

| Variável | Padrão | Uso |
|---|---|---|
| `YTS_DATA_DIR` | `~/.youtube-studio-mcp` | pasta de `token.json` e `cache.db` |
| `YTS_CLIENT_SECRET` | `$YTS_DATA_DIR/client_secret.json` | caminho do OAuth client |
| `YTS_CACHE_TTL` | `3600` | validade do cache, em segundos |

Para passar variáveis ao servidor no Claude Code:

```bash
claude mcp add youtube-studio -e YTS_CACHE_TTL=600 -- "$(pwd)/.venv/bin/youtube-studio-mcp" serve
```

---

## Solução de problemas

| Sintoma | Causa | Solução |
|---|---|---|
| `OAuth client secret not found` | `client_secret.json` fora do lugar | refaça o passo 5 ou defina `YTS_CLIENT_SECRET` |
| `Error 403: access_denied` / "has not completed the Google verification process" | sua conta não está em **Test users** | passo 3.4 |
| `redirect_uri_mismatch` | client criado como *Web application* | crie um client **Desktop app** (passo 4) |
| `accessNotConfigured` / "YouTube Data API v3 has not been used in project" | API não ativada ou recém-ativada | passo 2; aguarde alguns minutos |
| `No YouTube channel found for the authenticated account` | conta/canal errado no login | `rm ~/.youtube-studio-mcp/token.json && make auth` e escolha o canal certo |
| `Not authenticated` ou `invalid_grant` depois de alguns dias | em modo **Testing**, o Google expira o refresh token em **7 dias** | `make auth` de novo (ou publique o app em *Audience → Publish app*) |
| `quotaExceeded` | cota diária de 10.000 unidades | aguarde o reset diário; `overview` custa 1 unidade e usa cache |
| Dados desatualizados | cache local (1h por padrão) | `make refresh` ou `make clean-cache` |

## Segurança

- `client_secret.json` e `token.json` **nunca** devem ser commitados — já estão no `.gitignore`
  e ficam fora do repositório (`~/.youtube-studio-mcp`).
- O escopo pedido é só leitura: `youtube.readonly`.
- Para revogar o acesso: <https://myaccount.google.com/permissions> → `youtube-studio-mcp`
  → **Remove access**, e apague `~/.youtube-studio-mcp/token.json`.
