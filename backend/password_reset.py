"""
Password reset with emailed single-use links.

Only the sha256 hash of a token is stored. Tokens expire after one hour, are
deleted on use and are never put into the scheduler job store: the reset mail
is sent synchronously without retry. Used by the GraphQL mutations and by the
operator CLI (manage.py).
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from string import Template

from argon2 import PasswordHasher
from sqlalchemy import func

import login_throttle
from authz import InvalidInput, bump_auth_epoch
from config import db, mail_server_address, public_base_url, template_directory
from models import PasswordResetToken, User
from sendMail import sendMail
from validation import validate_password

log = logging.getLogger("lending")

REQUEST_INFO = "Wenn ein Konto existiert, wurde eine E-Mail versendet."
INVALID_LINK = "Der Link ist ungültig oder abgelaufen."
MAIL_SUBJECT = "Passwort zurücksetzen"
TOKEN_LIFETIME = timedelta(hours=1)
TEMPLATE_FILE = "password_reset_template.html"

# Used when the operator template still uses the old $password placeholder.
FALLBACK_BODY = (
    "<p>Sie haben ein neues Passwort angefordert. Über den folgenden Link "
    "können Sie ein neues Passwort festlegen:</p>\n"
    "<p><a href=\"$link\">$link</a></p>\n"
    "<p>Der Link ist eine Stunde gültig und kann nur einmal verwendet werden. "
    "Wenn Sie kein neues Passwort angefordert haben, können Sie diese E-Mail "
    "ignorieren.</p>"
)


def _utcnow():
    # naive UTC, matching PasswordResetToken.expires_at
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def find_user(email):
    if not email:
        return None
    return db.query(User).filter(
        func.lower(User.email) == email.strip().lower()).first()


def _delete_tokens(user_id):
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id).delete(synchronize_session=False)


def _link(token):
    return f"{public_base_url.rstrip('/')}/reset-password?token={token}"


def issue_link(user):
    """Replaces the user's tokens with a new one and returns the reset link
    (commits)."""
    _delete_tokens(user.user_id)
    token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(token_hash=_hash(token), user_id=user.user_id,
                              expires_at=_utcnow() + TOKEN_LIFETIME))
    db.commit()
    return _link(token)


def render_mail(link):
    try:
        path = os.path.join(template_directory, TEMPLATE_FILE)
        with open(path, encoding="utf-8") as file:
            text = file.read()
    except OSError:
        log.warning("Password reset template %s not readable, "
                    "using the built-in text", TEMPLATE_FILE)
        text = FALLBACK_BODY
    template = Template(text)
    if "link" not in template.get_identifiers():
        log.warning("Password reset template has no $link placeholder "
                    "(outdated template?), using the built-in text. "
                    "Copy the new %s into the template volume.", TEMPLATE_FILE)
        template = Template(FALLBACK_BODY)
    return template.safe_substitute(link=link)


def request_reset(email):
    """Sends a reset link if possible. Callers always answer with
    REQUEST_INFO."""
    user = find_user(email)
    if user is None:
        log.warning("Password reset requested for an unknown account")
        return
    if not mail_server_address or not public_base_url:
        log.warning("Password reset requested but mail or public_base_url "
                    "is not configured; no link created "
                    "(use manage.py reset-link)")
        return

    link = issue_link(user)
    if not sendMail(user.email, MAIL_SUBJECT, render_mail(link), retry=False):
        log.warning("Password reset mail could not be sent; link discarded")
        _delete_tokens(user.user_id)
        db.commit()


def set_password(user, new_password):
    """Sets a new password, removes all reset tokens, lifts a login lock
    and ends the user's other sessions (commits)."""
    validate_password(new_password)
    user.password_hash = PasswordHasher().hash(new_password)
    _delete_tokens(user.user_id)
    login_throttle.clear(user.email)
    bump_auth_epoch(user.user_id)
    db.commit()


def confirm_reset(token, new_password):
    """Sets the password for a valid link. Raises InvalidInput for a bad
    password or link."""
    validate_password(new_password)
    row = db.get(PasswordResetToken, _hash(token)) if token else None
    if row is None or row.expires_at <= _utcnow():
        raise InvalidInput(INVALID_LINK)
    user_id = row.user_id
    # single use: only the request that deletes the row may continue
    consumed = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == row.token_hash,
        PasswordResetToken.expires_at > _utcnow(),
    ).delete(synchronize_session=False)
    user = db.get(User, user_id) if consumed == 1 else None
    if user is None:
        db.rollback()
        raise InvalidInput(INVALID_LINK)
    set_password(user, new_password)
