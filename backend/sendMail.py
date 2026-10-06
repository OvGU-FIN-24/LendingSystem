import logging
import smtplib
import socket
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from smtplib import (
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPException,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPServerDisconnected,
)

from config import use_ssl, mail_server_address, mail_server_port, sender_email_address, sender_email_password, scheduler, timezone

log = logging.getLogger("lending")

# Errors worth retrying later; everything else is permanent and dropped.
TRANSIENT = (
    SMTPServerDisconnected,
    SMTPConnectError,
    socket.timeout,
    TimeoutError,
    ConnectionError,
)
# Delay in minutes before retry 1, 2 and 3; no further retries after that.
BACKOFF_MIN = [5, 15, 60]


def _is_transient(error):
    if isinstance(error, (SMTPRecipientsRefused, SMTPAuthenticationError)):
        return False
    if isinstance(error, SMTPResponseException):
        return 400 <= error.smtp_code < 500
    return isinstance(error, TRANSIENT)


def _deliver(receiver, subject, body):
    # use_ssl=1 -> implicit TLS (465), otherwise STARTTLS (587)
    context = ssl.create_default_context()
    if use_ssl == '1':
        mail_server = smtplib.SMTP_SSL(
            mail_server_address, mail_server_port, context=context, timeout=30
        )
    else:
        mail_server = smtplib.SMTP(
            mail_server_address, mail_server_port, timeout=30
        )
        mail_server.starttls(context=context)
    try:
        mail_server.login(sender_email_address, sender_email_password)

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = sender_email_address
        message["To"] = receiver
        message.attach(MIMEText(body, "HTML"))

        mail_server.sendmail(sender_email_address, receiver, message.as_string())
    finally:
        try:
            mail_server.quit()
        except SMTPException:
            pass


def sendMail(receiver, subject, body, attempt=0, retry=True):
    """
    Sends an HTML mail. Returns True when the SMTP server accepted the mail.

    Transient errors are retried through the scheduler at most
    len(BACKOFF_MIN) times, keeping the original subject. retry=False never
    schedules a job: use it for mails whose body must not be stored in the job
    store (password reset links). The defaults keep retry jobs pickled with
    the old three-argument signature working.
    """
    if not mail_server_address:
        log.warning(
            "Mail disabled (mail_server_address not set): not sending %r",
            subject,
        )
        return False

    try:
        _deliver(receiver, subject, body)
        return True
    except Exception as e:
        transient = _is_transient(e)
        log.warning(
            "Sending mail %r failed (attempt %d, %s): %s",
            subject,
            attempt + 1,
            "transient" if transient else "permanent",
            type(e).__name__,
        )

        if not (retry and transient and attempt < len(BACKOFF_MIN)):
            return False

        scheduler.add_job(
            name="sendMail retry",
            func=sendMail,
            args=(receiver, subject, body, attempt + 1, True),
            trigger='date',
            run_date=datetime.now(timezone)
            + timedelta(minutes=BACKOFF_MIN[attempt]),
        )
        return False
