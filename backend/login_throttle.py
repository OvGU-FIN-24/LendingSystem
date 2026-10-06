"""
Per-account login backoff.

Failed logins are counted per submitted email (normalized, also for unknown
emails, stored as sha256 hash). After login_max_failures failures within
login_lockout_minutes, logins for that email are refused for
login_lockout_minutes. A successful login, set_password and a password reset
clear the entry. Attempts while locked are not counted, so they do not
extend the lock. _lock serializes the read-modify-write between the threads
of the single gunicorn worker.
"""
import hashlib
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from config import db, login_lockout_minutes, login_max_failures
from models import LoginThrottle

_lock = threading.Lock()


def _utcnow():
    # naive UTC, matching LoginThrottle's DateTime columns
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _key(email):
    normalized = (email or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _period():
    return timedelta(minutes=login_lockout_minutes)


def is_locked(email):
    row = db.get(LoginThrottle, _key(email))
    return bool(row and row.locked_until and row.locked_until > _utcnow())


def record_failure(email):
    """Counts a failed login; locks the email when the limit is reached
    (commits)."""
    now = _utcnow()
    with _lock:
        # forget entries whose window and lock are over
        db.query(LoginThrottle).filter(
            LoginThrottle.window_start <= now - _period(),
            or_(LoginThrottle.locked_until.is_(None),
                LoginThrottle.locked_until <= now),
        ).delete(synchronize_session=False)
        key = _key(email)
        # locking read with refresh: sees rows committed by other threads
        # since is_locked() started this transaction (MySQL REPEATABLE READ)
        row = db.query(LoginThrottle).filter(
            LoginThrottle.key_hash == key
        ).with_for_update().populate_existing().first()
        if row is None:
            row = LoginThrottle(key_hash=key, failures=0)
            db.add(row)
        if row.window_start is None or row.window_start <= now - _period():
            row.failures = 0
            row.window_start = now
        row.failures += 1
        if row.failures >= login_max_failures:
            # the next window starts with the lock, so the entry expires
            # together with it
            row.locked_until = now + _period()
            row.failures = 0
            row.window_start = now
        db.commit()


def clear(email):
    """Removes the entry for email (does not commit)."""
    db.query(LoginThrottle).filter(
        LoginThrottle.key_hash == _key(email)
    ).delete(synchronize_session=False)
