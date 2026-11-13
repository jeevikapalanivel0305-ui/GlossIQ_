"""
Saved Purview connections, per signed-in GlossIQ user, each protected by a PIN.

Stored in backend/saved_connections.json (git-ignored). The client secret is
encrypted with a Fernet key taken from the `CREDENTIALS_KEY` secret / environment
variable, or else from backend/.credentials.key, which is created on first use
(also git-ignored). Keep that key file with the JSON: without it saved secrets
can't be read back.

The PIN itself is never stored, only a salted PBKDF2 hash. After MAX_ATTEMPTS
wrong PINs a connection is locked for LOCK_MINUTES.
"""
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken

_DIR = os.path.dirname(os.path.abspath(__file__))
STORE_PATH = os.path.join(_DIR, "saved_connections.json")
KEY_PATH = os.path.join(_DIR, ".credentials.key")
FIELDS = ("account_name", "tenant_id", "client_id")
PIN_RULE = "4 to 8 digits"
MAX_ATTEMPTS = 5
LOCK_MINUTES = 5


class PinError(Exception):
    """Wrong, missing or locked PIN."""


def valid_pin(pin):
    return bool(re.fullmatch(r"\d{4,8}", pin or ""))


def _hash_pin(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()


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


def _decrypt(rec, key):
    try:
        secret = _fernet(key).decrypt(rec["client_secret"].encode()).decode()
    except (InvalidToken, KeyError, ValueError):
        secret = ""   # key changed or missing: the user re-enters the secret
    return {**{f: rec.get(f, "") for f in FIELDS}, "client_secret": secret}


def list_titles(user):
    """Titles of the user's saved Purview connections, newest first."""
    saved = _load().get((user or "").lower(), {})
    return sorted(saved, key=lambda t: saved[t].get("saved_at", ""), reverse=True)


def has_pin(user, title):
    return bool(_load().get((user or "").lower(), {}).get(title, {}).get("pin_hash"))


def _check_pin(data, user, title, pin):
    """Verify the PIN for a record in `data` (updates attempt counters in `data`)."""
    rec = data.get((user or "").lower(), {}).get(title)
    if not rec:
        raise PinError("This saved connection no longer exists.")
    if not rec.get("pin_hash"):
        return rec   # saved before PINs existed
    locked_until = rec.get("locked_until")
    if locked_until and datetime.now() < datetime.fromisoformat(locked_until):
        mins = max(1, int((datetime.fromisoformat(locked_until) - datetime.now()).total_seconds() // 60) + 1)
        raise PinError(f"Too many wrong PINs. Try again in {mins} minute(s).")
    if hmac.compare_digest(_hash_pin(pin or "", rec["pin_salt"]), rec["pin_hash"]):
        rec.pop("failed_attempts", None)
        rec.pop("locked_until", None)
        return rec
    rec["failed_attempts"] = rec.get("failed_attempts", 0) + 1
    left = MAX_ATTEMPTS - rec["failed_attempts"]
    if left <= 0:
        rec["failed_attempts"] = 0
        rec["locked_until"] = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
        raise PinError(f"Wrong PIN. This connection is locked for {LOCK_MINUTES} minutes.")
    raise PinError(f"Wrong PIN. {left} attempt(s) left.")


def unlock(user, title, pin, key=None):
    """{account_name, tenant_id, client_id, client_secret} if the PIN is right; raises PinError otherwise."""
    data = _load()
    try:
        rec = _check_pin(data, user, title, pin)
    finally:
        _write(data)   # keep attempt counters
    return _decrypt(rec, key)


def save(user, title, creds, pin, key=None):
    """Save (or replace) a titled, PIN-protected connection for this user."""
    title = (title or "").strip()
    if not title:
        raise ValueError("A title is required")
    if not valid_pin(pin):
        raise ValueError(f"The PIN must be {PIN_RULE}")
    salt = os.urandom(16).hex()
    data = _load()
    data.setdefault((user or "").lower(), {})[title] = {
        **{f: (creds.get(f) or "").strip() for f in FIELDS},
        "client_secret": _fernet(key).encrypt((creds.get("client_secret") or "").encode()).decode(),
        "pin_salt": salt,
        "pin_hash": _hash_pin(pin, salt),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write(data)


def delete(user, title, pin):
    """Delete a saved connection; needs its PIN (raises PinError)."""
    data = _load()
    try:
        _check_pin(data, user, title, pin)
    except PinError:
        _write(data)
        raise
    data[(user or "").lower()].pop(title, None)
    _write(data)


def seal(obj, key=None):
    """Encrypt a JSON-able object into a cookie-safe token."""
    return _fernet(key).encrypt(json.dumps(obj, separators=(",", ":")).encode()).decode()


def unseal(token, key=None, max_age=None):
    """Object from seal(), or None if it is missing, tampered with, from another key or older than max_age seconds."""
    if not token:
        return None
    try:
        return json.loads(_fernet(key).decrypt(token.encode(), ttl=max_age))
    except (InvalidToken, ValueError, TypeError):
        return None


_RECORD_KEYS = (*FIELDS, "client_secret", "pin_salt", "pin_hash", "saved_at")


def export_records(user):
    """The user's saved connections as stored (secrets stay encrypted, PINs stay hashed)."""
    saved = _load().get((user or "").lower(), {})
    return {t: {k: r[k] for k in _RECORD_KEYS if k in r} for t, r in saved.items()}


def import_records(user, records):
    """Add saved connections kept in the browser that this server doesn't have (e.g. after a redeploy
    wiped the server's disk). A newer copy replaces an older one. → number added or updated."""
    if not user or not isinstance(records, dict):
        return 0
    data = _load()
    mine = data.setdefault(user.lower(), {})
    changed = 0
    for title, rec in records.items():
        if not (isinstance(rec, dict) and rec.get("client_secret")):
            continue
        if title not in mine or rec.get("saved_at", "") > mine[title].get("saved_at", ""):
            mine[title] = {k: rec[k] for k in _RECORD_KEYS if k in rec}
            changed += 1
    if changed:
        _write(data)
    return changed


def find_title(user, creds, key=None):
    """Title of an identical saved connection (all four fields), or None."""
    want = {f: creds.get(f, "") for f in (*FIELDS, "client_secret")}
    saved = _load().get((user or "").lower(), {})
    for title in list_titles(user):
        if _decrypt(saved[title], key) == want:
            return title
    return None
