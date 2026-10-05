import pytz

from config import use_ssl, mail_server_address, mail_server_port, sender_email_address, sender_email_password, scheduler, timezone
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

def sendMail(receiver, subject, body):
    if not mail_server_address:
        print("Mail disabled (mail_server_address not set): not sending '" + subject + "' to " + receiver)
        return

    try:
        # create Mail Server: use_ssl=1 -> implicit TLS (465), otherwise STARTTLS (587)
        context = ssl.create_default_context()
        if use_ssl == '1':
            mail_server = smtplib.SMTP_SSL(mail_server_address, mail_server_port, context=context)
        else:
            mail_server = smtplib.SMTP(mail_server_address, mail_server_port)
            mail_server.starttls(context=context)

        mail_server.login(sender_email_address, sender_email_password)

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = sender_email_address
        message["To"] = receiver

        # HTML hier möglich
        body_text = MIMEText(body, "HTML")
        message.attach(body_text)

        mail_server.sendmail(sender_email_address, receiver, message.as_string())
        mail_server.quit()
    except Exception as e:
        print("Was not able to send mail: " + str(e))

        # Resend the mail again in 5 Minutes
        # Attention: this schedule will not be cancelled using the CancelJob function from the scheduler file
        scheduler.add_job(
            name="sendMail retry",
            func=sendMail,
            args=(receiver, subject + " RETRY", body),
            trigger='date',
            run_date=datetime.now(timezone) + timedelta(minutes=5)
        )
