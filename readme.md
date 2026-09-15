# youtube-studio-mcp

Local MCP server (stdio) exposing data from **your own** YouTube channel to Claude Code.
Walking skeleton: one tool, `get_channel_overview`, wired end to end —
OAuth → YouTube Data API v3 → SQLite cache → MCP tool → stdio.

## Layout

```
src/youtube_studio_mcp/
  config.py    paths/settings (env vars)
  auth.py      OAuth: `login` (CLI, opens browser) / `load_credentials` (server, silent refresh)
  youtube.py   thin Data API v3 client + response parsing
  cache.py     sqlite3 key/value cache with TTL
  service.py   use cases (client + cache), no MCP/Google imports
  server.py    MCP tool registration (MCPServer)
  __main__.py  entry point: `serve` (default) or `auth`
tests/         pytest, no network
```

To add a tool: API call in `youtube.py` → use case in `service.py` → `@server.tool()` in `server.py`.

> Note: `mcp` 2.x renamed `FastMCP` to `MCPServer` (`from mcp.server.mcpserver import MCPServer`).

## Setup

```bash
make install   # venv + project + dev deps
make test
make           # list all commands (install, test, shell, auth, overview, mcp-add, clean...)
```

### Google OAuth (one time)

> 📘 **Step-by-step guide (credentials, OAuth, Claude Code, troubleshooting):
> [docs/SETUP.md](docs/SETUP.md)**

Summary:

1. In Google Cloud Console: enable **YouTube Data API v3**.
2. Configure the OAuth consent screen (add yourself as a test user).
3. Create an OAuth client ID of type **Desktop app** and download the JSON to
   `~/.youtube-studio-mcp/client_secret.json`.
4. Log in (opens the browser): `make auth`

No API key is used — your own channel's data requires OAuth.
The token is stored at `~/.youtube-studio-mcp/token.json` and refreshed automatically.
The server never opens the browser itself (it would corrupt stdio).

## CLI

The same features are available from the terminal (same service and cache as the MCP tools).

Interactive menu with Tab completion — just run it in a terminal:

```
$ .venv/bin/youtube-studio-mcp
YouTube Studio — 'help' lists commands, Tab completes, 'exit' quits.
yt> help
yt> overview --help
yt> overview --refresh
yt> exit
```

One-shot commands:

```bash
.venv/bin/youtube-studio-mcp --help
.venv/bin/youtube-studio-mcp overview            # JSON, served from cache when fresh
.venv/bin/youtube-studio-mcp overview --refresh  # bypass the cache
```

To add a command for a new tool: add a subparser in `cli.build_parser`, handle it in
`cli.run_command`, and list it in `shell.COMMANDS`.

## Connect to Claude Code

```bash
claude mcp add youtube-studio -- "$(pwd)/.venv/bin/youtube-studio-mcp" serve
```

## Configuration

| Env var             | Default                                     |
|---------------------|---------------------------------------------|
| `YTS_DATA_DIR`      | `~/.youtube-studio-mcp`                     |
| `YTS_CLIENT_SECRET` | `$YTS_DATA_DIR/client_secret.json`          |
| `YTS_CACHE_TTL`     | `3600` (seconds)                            |
