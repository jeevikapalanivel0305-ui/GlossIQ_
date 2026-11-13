"""
Saved Purview connections, per signed-in GlossIQ user, each protected by a PIN.

Each connection's four fields are encrypted with a key derived from its own PIN (PBKDF2 +
random salt), so a saved connection never depends on a server key: it stays readable across
redeploys, server restarts and secret rotations, and only its PIN opens it. The PIN itself is
never stored, only a salted PBKDF2 hash (with a different derivation from the encryption key).
After MAX_ATTEMPTS wrong PINs a connection is locked for LOCK_MINUTES on this server.

Stored in backend/saved_connections.json (git-ignored). The app also keeps a copy in the browser
(export_records / import_records), because Streamlit Cloud wipes the server's disk on redeploy.

Connections saved by older versions (secret encrypted with a server key) are still read and are
upgraded to PIN encryption the first time they are unlocked.

seal()/unseal() encrypt other app data (the sign-in cookie) with the server key: the
`CREDENTIALS_KEY` passed in / environment variable, or else backend/.credentials.key.
"""
import base64
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
ALL_FIELDS = (*FIELDS, "client_secret")
PIN_RULE = "4 to 8 digits"
MAX_ATTEMPTS = 5
LOCK_MINUTES = 5
_ITERATIONS = 200_000


class PinError(Exception):
    """Wrong, missing or locked PIN."""


def valid_pin(pin):
    return bool(re.fullmatch(r"\d{4,8}", pin or ""))


def _hash_pin(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), _ITERATIONS).hex()


def _pin_fernet(pin, salt):
    """Encryption key for one connection, from its PIN (separate derivation from the PIN hash)."""
    raw = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt) + b"glossiq-enc", _ITERATIONS)
    return Fernet(base64.urlsafe_b64encode(raw))


def _fingerprint(creds, salt):
    """Salted hash of all four fields: tells whether a connection is already saved without the PIN."""
    msg = "\x1f".join((creds.get(f) or "").strip() for f in ALL_FIELDS).encode()
    return hmac.new(bytes.fromhex(salt), msg, hashlib.sha256).hexdigest()


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


def _legacy_decrypt(rec, key):
    """Fields of a connection saved before PIN encryption (secret encrypted with the server key)."""
    try:
        secret = _fernet(key).decrypt(rec["client_secret"].encode()).decode()
    except (InvalidToken, KeyError, ValueError):
        secret = ""   # server key changed: the secret can't be recovered
    return {**{f: rec.get(f, "") for f in FIELDS}, "client_secret": secret}


def _build_record(creds, pin):
    salt = os.urandom(16).hex()
    creds = {f: (creds.get(f) or "").strip() for f in ALL_FIELDS}
    return {
        "sealed": _pin_fernet(pin, salt).encrypt(json.dumps(creds).encode()).decode(),
        "pin_salt": salt,
        "pin_hash": _hash_pin(pin, salt),
        "fingerprint": _fingerprint(creds, salt),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }


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
    """{account_name, tenant_id, client_id, client_secret} if the PIN is right; raises PinError otherwise.
    An older connection is upgraded to PIN encryption here (when its PIN is known)."""
    data = _load()
    try:
        rec = _check_pin(data, user, title, pin)
        if rec.get("sealed"):
            try:
                creds = json.loads(_pin_fernet(pin, rec["pin_salt"]).decrypt(rec["sealed"].encode()))
            except (InvalidToken, ValueError):
                raise PinError("This saved connection is damaged. Delete it and save it again.")
        else:
            creds = _legacy_decrypt(rec, key)
            if valid_pin(pin) and creds["client_secret"]:
                upgraded = _build_record(creds, pin)
                upgraded["saved_at"] = rec.get("saved_at", upgraded["saved_at"])
                data[(user or "").lower()][title] = upgraded
    finally:
        _write(data)   # keep attempt counters / the upgrade
    return {f: creds.get(f, "") for f in ALL_FIELDS}


def save(user, title, creds, pin, key=None):
    """Save (or replace) a titled, PIN-protected connection for this user."""
    title = (title or "").strip()
    if not title:
        raise ValueError("A title is required")
    if not valid_pin(pin):
        raise ValueError(f"The PIN must be {PIN_RULE}")
    data = _load()
    data.setdefault((user or "").lower(), {})[title] = _build_record(creds, pin)
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
    data.setdefault("_deleted", {}).setdefault((user or "").lower(), {})[title] = \
        datetime.now().isoformat(timespec="seconds")
    _write(data)


def find_title(user, creds, key=None):
    """Title of an identical saved connection (all four fields), or None. Needs no PIN."""
    want = {f: (creds.get(f) or "").strip() for f in ALL_FIELDS}
    saved = _load().get((user or "").lower(), {})
    for title in list_titles(user):
        rec = saved[title]
        if rec.get("fingerprint"):
            if hmac.compare_digest(_fingerprint(want, rec["pin_salt"]), rec["fingerprint"]):
                return title
        elif _legacy_decrypt(rec, key) == want:
            return title
    return None


# ── Browser copy ────────────────────────────────────────────────────────────────────────────────
_RECORD_KEYS = ("sealed", "pin_salt", "pin_hash", "fingerprint", "saved_at",
                *FIELDS, "client_secret")   # the last four only on older records


def export_records(user):
    """The user's saved connections as stored (PIN-encrypted, PINs hashed) and recent deletions."""
    data = _load()
    u = (user or "").lower()
    recs = {t: {k: r[k] for k in _RECORD_KEYS if k in r} for t, r in data.get(u, {}).items()}
    return {"saved": recs, "deleted": data.get("_deleted", {}).get(u, {})}


def import_records(user, exported):
    """Merge a browser copy from export_records() into this server's store (e.g. after a redeploy
    wiped the disk): the newer of saved / deleted wins per title. → number of changes."""
    if not user or not isinstance(exported, dict):
        return 0
    if "saved" not in exported:   # copy written by the previous version: {title: record}
        exported = {"saved": exported, "deleted": {}}
    u = user.lower()
    data = _load()
    mine = data.setdefault(u, {})
    deleted = data.setdefault("_deleted", {}).setdefault(u, {})
    changed = 0
    for title, when in (exported.get("deleted") or {}).items():
        if when > deleted.get(title, ""):
            deleted[title] = when
            changed += 1
        if title in mine and when >= mine[title].get("saved_at", ""):
            mine.pop(title)
            changed += 1
    for title, rec in (exported.get("saved") or {}).items():
        if not (isinstance(rec, dict) and (rec.get("sealed") or rec.get("client_secret"))):
            continue
        when = rec.get("saved_at", "")
        if when <= deleted.get(title, "") or (title in mine and when <= mine[title].get("saved_at", "")):
            continue
        mine[title] = {k: rec[k] for k in _RECORD_KEYS if k in rec}
        changed += 1
    if changed:
        _write(data)
    return changed


# ── Other app data (sign-in cookie) ─────────────────────────────────────────────────────────────
def seal(obj, key=None):
    """Encrypt a JSON-able object into a cookie-safe token with the server key."""
    return _fernet(key).encrypt(json.dumps(obj, separators=(",", ":")).encode()).decode()


def unseal(token, key=None, max_age=None):
    """Object from seal(), or None if it is missing, tampered with, from another key or older than max_age seconds."""
    if not token:
        return None
    try:
        return json.loads(_fernet(key).decrypt(token.encode(), ttl=max_age))
    except (InvalidToken, ValueError, TypeError):
        return None
