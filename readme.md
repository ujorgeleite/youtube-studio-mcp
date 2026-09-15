# youtube-studio-mcp

Local MCP server (stdio) exposing data from **your own** YouTube channel to Claude Code.
OAuth → YouTube Data API v3 + YouTube Analytics API v2 → SQLite cache → MCP tools → stdio.

Tools:

| Tool | What it returns |
|------|-----------------|
| `get_channel_overview` | subscribers, total views, video count, uploads playlist id |
| `get_channel_metrics` | views, minutes watched, avg view duration, subscribers gained/lost/net for a date range |
| `list_videos` | every uploaded video (id, title, publish date, ISO-8601 duration) |
| `get_retention_curve` | audience retention curve for one video |
| `analyze_pillar_performance` | watch time and retention grouped and ranked by content pillar |

> ⚠️ **Phase 1 requires re-consenting once.** The Analytics tools need the added
> `yt-analytics.readonly` scope, and adding a scope does not widen an existing token.
> A token minted before Phase 1 is detected as insufficient and the tools ask you to
> run `make auth` (or `youtube-studio-mcp auth`) again to grant the new scope.

List the registered tools without authenticating:

```bash
.venv/bin/python -m youtube_studio_mcp.server --self-check
```

## Layout

```
src/youtube_studio_mcp/
  config.py    paths/settings (env vars), scopes, cache TTLs
  auth.py      OAuth: `login` (CLI, opens browser) / `load_credentials` (server, silent refresh + scope check)
  youtube.py   thin Data API v3 client + response parsing
  analytics.py thin Analytics API v2 client + response parsing
  pillars.py   loads config/pilares.json (videoId -> pillar map)
  cache.py     sqlite3 key/value cache with TTL
  service.py   use cases (clients + cache), no MCP/Google imports
  server.py    MCP tool registration (MCPServer) + --self-check
  __main__.py  entry point: `serve` (default), `auth`, and the CLI commands
config/
  pilares.json hand-maintained videoId -> pillar map
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

1. In Google Cloud Console: enable **YouTube Data API v3** and **YouTube Analytics API**.
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
.venv/bin/youtube-studio-mcp metrics --start 2026-08-01 --end 2026-08-28
.venv/bin/youtube-studio-mcp videos
.venv/bin/youtube-studio-mcp retention <VIDEO_ID>
.venv/bin/youtube-studio-mcp pillars
```

To add a command for a new tool: add a subparser in `cli.build_parser`, handle it in
`cli.run_command`, and list it in `shell.COMMANDS`.

## Content pillars (`config/pilares.json`)

`analyze_pillar_performance` groups your videos by content pillar. You maintain the
map **by hand** — it is the source of truth for `videoId -> pillar`:

```json
{
  "VIDEO_ID": { "pilar": "imigracao|pedro|holanda|pratico|doceria", "formato": "vlog", "seo": true }
}
```

Videos not listed here are still counted, under a `não classificado` bucket, so nothing
is silently dropped. Point `YTS_PILLARS_FILE` elsewhere to use a different file.

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
| `YTS_PILLARS_FILE`  | `config/pilares.json`                       |
