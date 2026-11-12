"""
Saved Purview connections, per signed-in GlossIQ user.

Stored in backend/saved_connections.json (git-ignored). The client secret is
encrypted with a Fernet key taken from the `CREDENTIALS_KEY` secret / environment
variable, or else from backend/.credentials.key, which is created on first use
(also git-ignored). Keep that key file with the JSON: without it saved secrets
can't be read back.
"""
import json
import os
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken

_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(_DIR, "saved_connections.json")
KEY_PATH = os.path.join(_DIR, ".credentials.key")
FIELDS = ("account_name", "tenant_id", "client_id")


def _fernet(key=None):
    key = key or os.environ.get("CREDENTIALS_KEY")
    if not key:
        if not os.path.exists(KEY_PATH):
            with open(KEY_PATH, "wb") as f:
                f.write(Fernet.generate_key())
        with open(KEY_PATH, "rb") as f:
            key = f.read().strip()
    return Fernet(key if isinstance(key, bytes) else key.encode())


def _load():
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data):
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, STORE_PATH)


def list_titles(user):
    """Titles of the user's saved Purview connections, newest first."""
    saved = _load().get((user or "").lower(), {})
    return sorted(saved, key=lambda t: saved[t].get("saved_at", ""), reverse=True)


def get(user, title, key=None):
    """{account_name, tenant_id, client_id, client_secret} for a saved title, or None."""
    rec = _load().get((user or "").lower(), {}).get(title)
    if not rec:
        return None
    try:
        secret = _fernet(key).decrypt(rec["client_secret"].encode()).decode()
    except (InvalidToken, KeyError, ValueError):
        secret = ""   # key changed or missing: the user re-enters the secret
    return {**{f: rec.get(f, "") for f in FIELDS}, "client_secret": secret}


def save(user, title, creds, key=None):
    """Save (or replace) a titled connection for this user."""
    title = (title or "").strip()
    if not title:
        raise ValueError("A title is required")
    data = _load()
    data.setdefault((user or "").lower(), {})[title] = {
        **{f: (creds.get(f) or "").strip() for f in FIELDS},
        "client_secret": _fernet(key).encrypt((creds.get("client_secret") or "").encode()).decode(),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write(data)


def delete(user, title):
    data = _load()
    if data.get((user or "").lower(), {}).pop(title, None) is not None:
        _write(data)


def find_title(user, creds, key=None):
    """Title of an identical saved connection (all four fields), or None."""
    for title in list_titles(user):
        if get(user, title, key) == {f: creds.get(f, "") for f in (*FIELDS, "client_secret")}:
            return title
    return None
