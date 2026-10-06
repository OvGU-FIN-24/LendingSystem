from dotenv import load_dotenv
from datetime import timedelta

from flask import Flask
from flask_cors import CORS
from flask_session import Session
import os
import socket
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
import pytz
from werkzeug.middleware.proxy_fix import ProxyFix

hostname = socket.gethostname()
print("Hostname: ", hostname)

# Read config file on host
if not (hostname == "container"):
    load_dotenv("../backend.env")

# Testing: testing_on=1 uses an in-memory sqlite database, temporary
# directories, no mail and no scheduler start (see app.py)
testing_on = int(os.getenv('testing_on', '0') or 0)

# Read env variables
# Database
db_host     = os.getenv("database_host")
db_database = os.getenv('database_name')
db_port     = os.getenv('database_port')
db_user     = os.getenv('database_user')

# Read database password from file or env variable
db_pw = os.getenv('database_password')
if not testing_on and (db_pw is None or db_pw == ""):
    with open(os.getenv('database_password_location'), 'r') as f:
        db_pw = f.read().strip()

# Paths
if testing_on:
    _tmp = tempfile.mkdtemp(prefix="lending-test-")
    root_directory          = os.getenv('root_directory') or _tmp
    tmp_picture_directory   = os.getenv('picture_directory') or 'pictures'
    tmp_pdf_directory       = os.getenv('pdf_directory') or 'pdfs'
    tmp_template_directory  = os.getenv('template_directory') or 'templates'
else:
    root_directory          = os.getenv('root_directory')
    tmp_picture_directory   = os.getenv('picture_directory')
    tmp_pdf_directory       = os.getenv('pdf_directory')
    tmp_template_directory  = os.getenv('template_directory')
picture_directory       = os.path.join(root_directory, tmp_picture_directory)
pdf_directory           = os.path.join(root_directory, tmp_pdf_directory)
template_directory      = os.path.join(root_directory, tmp_template_directory)
if testing_on:
    for _d in (picture_directory, pdf_directory, template_directory):
        os.makedirs(_d, exist_ok=True)

# Mail
mail_server_address     = None if testing_on else os.getenv('mail_server_address')
mail_server_port        = os.getenv('mail_server_port')
use_ssl                 = os.getenv('use_ssl')
sender_email_address    = os.getenv('sender_email_address')
sender_email_password   = os.getenv('sender_email_password')

# Public base URL of the frontend, used for links in mails (password reset)
public_base_url = os.getenv('public_base_url', '').strip()

# Allowed sign-up email domains (comma list); subdomains are allowed too
allowed_email_domains = [d.strip().lower() for d in
                         os.getenv('allowed_email_domains', 'ovgu.de').split(',')
                         if d.strip()]

# Secret key
secret_key = os.getenv("secret_key")
if not secret_key:
    raise SystemExit("secret_key is not set (backend.env): refusing to start")

# Timezone
timezone_string         = os.getenv('timezone')

# Root user
application_root_user_name      = os.getenv('root_user_name')
application_root_user_password  = os.getenv('root_user_password')

if not testing_on:
    database_connection_string = 'mysql://' + db_user + ':' + db_pw + '@' + db_host + ":" + db_port + '/' + db_database
    engine = create_engine(database_connection_string, convert_unicode=True)
else:
    database_connection_string = 'sqlite://'
    engine = create_engine(database_connection_string, poolclass=StaticPool,
                           connect_args={'check_same_thread': False})

db = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# Create Flask app
app = Flask(__name__)
app.debug = False

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

app.secret_key = secret_key
app.config['SESSION_TYPE'] = 'sqlalchemy'
# Secure cookie by default; session_cookie_secure=0 only for plain-HTTP tests
app.config['SESSION_COOKIE_SECURE'] = (
    os.getenv('session_cookie_secure', '1') == '1')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.permanent_session_lifetime = timedelta(hours=2)

app.config['SQLALCHEMY_DATABASE_URI'] = database_connection_string

# Same origin by default; cors_origins (comma list) enables cross-origin access
cors_origins = [o.strip() for o in os.getenv('cors_origins', '').split(',')
                if o.strip()]
if cors_origins:
    CORS(app, resources={r"/*": {"origins": cors_origins}},
         supports_credentials=True)
server_session = Session(app)

# Create scheduler for automated mail sending; started in app.py (not for
# tests or the operator CLI)
jobstores = {
    'default': SQLAlchemyJobStore(engine=engine)
}

timezone = pytz.timezone('Europe/Berlin')
scheduler = BackgroundScheduler(jobstores=jobstores, timezone=timezone)
