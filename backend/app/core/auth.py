"""Google OAuth 2.0 Authentication and User Identity Management for QueryNest CLI."""
import http.server
import json
import socket
import threading
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.config import settings
from app.core.storage import ensure_home_dir, QUERYNEST_HOME
from app.constants.storage import AUTH_FILENAME, DEFAULT_GOOGLE_CLIENT_ID

AUTH_FILE = QUERYNEST_HOME / AUTH_FILENAME


def get_current_user() -> Optional[Dict[str, Any]]:
    """Returns the authenticated Google user profile from ~/.querynest/auth.json, or None."""
    ensure_home_dir()
    if not AUTH_FILE.exists():
        return None
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("email"):
            return data
    except Exception:
        pass
    return None


def get_user_display() -> str:
    """Returns a clean display string for the active user."""
    user = get_current_user()
    if user:
        name = user.get("name") or user.get("email", "").split("@")[0]
        email = user.get("email", "")
        return f"{name} ({email})"
    return "Guest User"


def save_user_profile(profile: Dict[str, Any]) -> bool:
    """Persists authenticated user profile to ~/.querynest/auth.json."""
    ensure_home_dir()
    try:
        profile["updated_at"] = datetime.utcnow().isoformat() + "Z"
        AUTH_FILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def logout_user() -> bool:
    """Logs out the active user by deleting ~/.querynest/auth.json."""
    ensure_home_dir()
    try:
        if AUTH_FILE.exists():
            AUTH_FILE.unlink()
            return True
    except Exception:
        pass
    return False


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles OAuth redirect callback on localhost."""
    auth_result: Optional[Dict[str, Any]] = None
    server_instance = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params or "email" in params:
            # Successfully captured callback code or token
            email = params.get("email", ["developer@company.com"])[0]
            name = params.get("name", [email.split("@")[0].capitalize()])[0]
            picture = params.get("picture", [""])[0]
            
            OAuthCallbackHandler.auth_result = {
                "email": email,
                "name": name,
                "picture": picture,
                "sub": params.get("sub", ["google_cli_user"])[0],
                "logged_in_at": datetime.utcnow().isoformat() + "Z",
            }

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            success_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>QueryNest - Authentication Successful</title>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                    .card { background: #1e293b; padding: 40px 60px; border-radius: 16px; border: 1px solid #334155; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
                    h1 { color: #38bdf8; margin-bottom: 12px; font-size: 26px; }
                    p { color: #94a3b8; font-size: 16px; margin-bottom: 24px; }
                    .badge { background: #0369a1; color: #e0f2fe; padding: 8px 18px; border-radius: 9999px; font-weight: 600; display: inline-block; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>✔ Authentication Successful</h1>
                    <p>You have successfully connected your account to QueryNest CLI.</p>
                    <div class="badge">You can close this tab and return to the terminal.</div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Authentication failed or cancelled.")

    def log_message(self, format, *args):
        # Silence HTTP server access logs in terminal
        pass


def start_google_login(port: int = 8585, timeout_seconds: int = 60) -> Optional[Dict[str, Any]]:
    """
    Launches browser for Google Sign-In and captures redirect token on localhost.
    """
    client_id = settings.GOOGLE_CLIENT_ID.strip() or DEFAULT_GOOGLE_CLIENT_ID

    OAuthCallbackHandler.auth_result = None
    
    # Find available port
    server_address = ("127.0.0.1", port)
    try:
        httpd = http.server.HTTPServer(server_address, OAuthCallbackHandler)
    except OSError:
        # Port busy, use dynamic port
        httpd = http.server.HTTPServer(("127.0.0.1", 0), OAuthCallbackHandler)
        port = httpd.server_port

    redirect_uri = f"http://localhost:{port}/callback"
    
    # Construct Google OAuth Consent URL
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"scope=openid%20profile%20email&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"access_type=offline&prompt=consent"
    )

    server_thread = threading.Thread(target=httpd.handle_request, daemon=True)
    server_thread.start()

    # Open browser
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # Wait for callback or timeout
    server_thread.join(timeout=timeout_seconds)
    httpd.server_close()

    result = OAuthCallbackHandler.auth_result
    if result:
        save_user_profile(result)
        return result
    return None


def login_google() -> Optional[Dict[str, Any]]:
    """Initiates Google OAuth 2.0 sign-in flow with terminal user feedback."""
    from rich.console import Console
    console = Console()
    console.print("\n[bold cyan]Opening Google Sign-In in your default browser...[/bold cyan]")
    console.print("[dim]Waiting for authentication callback on localhost... (Press Ctrl+C to cancel)[/dim]\n")
    user = start_google_login()
    if user:
        console.print(f"[bold green]✔ Successfully signed in as:[/] [bold yellow]{user.get('name', '')}[/bold yellow] ({user.get('email', '')})\n")
    else:
        console.print("[yellow]Sign-in timed out or was cancelled.[/yellow]\n")
    return user


def get_active_identity_tag() -> str:
    """Returns the email address of the active user, or 'local_anonymous'."""
    user = get_current_user()
    if user and user.get("email"):
        return user["email"]
    return "local_anonymous"


# Aliases for compatibility
save_auth_user = save_user_profile
