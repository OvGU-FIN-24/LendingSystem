"""Sign-up and credential validation."""
import re

from authz import Forbidden, InvalidInput
from config import allowed_email_domains

LOCAL_RE = re.compile(r'^[A-Za-z0-9._%+-]+$')
MIN_PASSWORD_LENGTH = 10

EMAIL_NOT_ALLOWED = (
    "Nur E-Mail Adressen der Universität (ovgu.de) sind erlaubt."
)
PASSWORD_TOO_SHORT = "Das Passwort muss mindestens 10 Zeichen lang sein"


def validate_email(raw):
    """Returns the lower-cased address if its domain is allowed, else Forbidden
    (403)."""
    email = (raw or "").strip()
    if email.count('@') != 1:
        raise Forbidden(EMAIL_NOT_ALLOWED)
    local, domain = email.split('@')
    domain = domain.lower()
    if not local or not LOCAL_RE.match(local):
        raise Forbidden(EMAIL_NOT_ALLOWED)
    if not any(
        domain == d or domain.endswith('.' + d) for d in allowed_email_domains
    ):
        raise Forbidden(EMAIL_NOT_ALLOWED)
    return email.lower()


def validate_password(pw):
    if pw is None or len(pw) < MIN_PASSWORD_LENGTH:
        raise InvalidInput(PASSWORD_TOO_SHORT)
