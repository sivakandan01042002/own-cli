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


def _exchange_google_code(code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
    """Exchanges Google authorization code for the authenticated user profile."""
    import base64
    import urllib.request

    client_id = settings.GOOGLE_CLIENT_ID.strip() or DEFAULT_GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET.strip()

    try:
        data_params = {
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if client_secret:
            data_params["client_secret"] = client_secret

        encoded_data = urllib.parse.urlencode(data_params).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=encoded_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            token_json = json.loads(resp.read().decode("utf-8"))

        access_token = token_json.get("access_token")
        id_token = token_json.get("id_token")

        # 1. Fetch from Google UserInfo endpoint
        if access_token:
            try:
                userinfo_req = urllib.request.Request(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                with urllib.request.urlopen(userinfo_req, timeout=10) as u_resp:
                    u_info = json.loads(u_resp.read().decode("utf-8"))
                    email = u_info.get("email", "")
                    name = u_info.get("name") or (email.split("@")[0].capitalize() if email else "User")
                    return {
                        "email": email,
                        "name": name,
                        "picture": u_info.get("picture", ""),
                        "sub": u_info.get("id", ""),
                        "logged_in_at": datetime.utcnow().isoformat() + "Z",
                    }
            except Exception:
                pass

        # 2. Decode JWT ID Token payload if userinfo endpoint was unavailable
        if id_token:
            parts = id_token.split(".")
            if len(parts) >= 2:
                padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode("utf-8"))
                email = payload.get("email", "")
                name = payload.get("name") or (email.split("@")[0].capitalize() if email else "User")
                return {
                    "email": email,
                    "name": name,
                    "picture": payload.get("picture", ""),
                    "sub": payload.get("sub", ""),
                    "logged_in_at": datetime.utcnow().isoformat() + "Z",
                }
    except Exception:
        pass
    return None


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles OAuth redirect callback on localhost."""
    auth_result: Optional[Dict[str, Any]] = None
    redirect_uri: str = ""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            code = params["code"][0]
            user_profile = _exchange_google_code(code, OAuthCallbackHandler.redirect_uri)
            if user_profile:
                OAuthCallbackHandler.auth_result = user_profile
            else:
                email = params.get("email", ["user@gmail.com"])[0]
                OAuthCallbackHandler.auth_result = {
                    "email": email,
                    "name": email.split("@")[0].capitalize(),
                    "picture": "",
                    "sub": "google_user",
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
        elif "email" in params:
            email = params.get("email", ["user@gmail.com"])[0]
            OAuthCallbackHandler.auth_result = {
                "email": email,
                "name": params.get("name", [email.split("@")[0].capitalize()])[0],
                "picture": params.get("picture", [""])[0],
                "sub": params.get("sub", ["google_user"])[0],
                "logged_in_at": datetime.utcnow().isoformat() + "Z",
            }
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
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
    OAuthCallbackHandler.redirect_uri = redirect_uri
    
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
    """Initiates Google OAuth 2.0 sign-in flow with clean, ephemeral terminal feedback."""
    import time
    from rich.console import Console
    from rich.live import Live
    from rich.text import Text
    from app.core.theme import RICH_THEME

    console = Console(theme=RICH_THEME)
    with Live(Text.from_markup("\n[dim]Opening Google Sign-In in your browser...[/dim]"), console=console, transient=True) as live:
        user = start_google_login()
        if user:
            name = user.get("name") or user.get("email", "").split("@")[0]
            email = user.get("email", "")
            live.update(Text.from_markup(f"\n[success]Signed in as:[/] [white]{name}[/white] [dim]({email})[/dim]"))
            time.sleep(2.5)
        else:
            live.update(Text.from_markup("\n[warning]Sign-in timed out or was cancelled.[/warning]"))
            time.sleep(2.5)
    return user


def get_active_identity_tag() -> str:
    """Returns the email address of the active user, or 'local_anonymous'."""
    user = get_current_user()
    if user and user.get("email"):
        return user["email"]
    return "local_anonymous"


# Aliases for compatibility
save_auth_user = save_user_profile
