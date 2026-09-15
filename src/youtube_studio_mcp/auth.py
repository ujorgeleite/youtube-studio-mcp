"""OAuth: interactive login (CLI only) and silent credential loading (server)."""

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import SCOPES, Settings


class NotAuthenticatedError(RuntimeError):
    pass


RECONSENT_MESSAGE = (
    "Saved token is missing required scopes (YouTube Analytics). Phase 1 needs a "
    "new consent for the added scope — run: youtube-studio-mcp auth"
)


def login(settings: Settings) -> Credentials:
    """Run the browser OAuth flow and persist a fresh token for the full SCOPES set.
    Never call this from the stdio server: the flow prints to stdout and would
    corrupt the MCP protocol. Adding a scope cannot widen an existing token, so
    re-running this is how the Analytics scope gets granted."""
    if not settings.client_secret_file.exists():
        raise FileNotFoundError(f"OAuth client secret not found: {settings.client_secret_file}")
    flow = InstalledAppFlow.from_client_secrets_file(str(settings.client_secret_file), SCOPES)
    creds = flow.run_local_server(port=0)
    _save(settings, creds)
    return creds


def load_credentials(settings: Settings) -> Credentials:
    """Load the saved token, refreshing it if expired. Never opens a browser. Loads
    without a forced scope list so `creds.scopes` reflects what was actually granted;
    a token missing the Analytics scope fails the check and must be re-consented."""
    if not settings.token_file.exists():
        raise NotAuthenticatedError("Not authenticated. Run: youtube-studio-mcp auth")
    creds = Credentials.from_authorized_user_file(str(settings.token_file))
    if not creds.has_scopes(SCOPES):
        raise NotAuthenticatedError(RECONSENT_MESSAGE)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save(settings, creds)
        return creds
    raise NotAuthenticatedError("Saved token is invalid. Run: youtube-studio-mcp auth")


def _save(settings: Settings, creds: Credentials) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.token_file.write_text(creds.to_json())
    settings.token_file.chmod(0o600)
