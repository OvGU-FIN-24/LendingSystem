# DEPLOY-1 — Docker Compose production deployment: requirements baseline

Status: accepted requirements baseline; the decisions in §5 are resolved in [architecture.md](architecture.md) (H1–H4, §9). Base: `main@58b5701a23e52329e66d1344eb93b3229e4ce537`, branch `feat/docker-compose-deployment`.

Goal: add a production-ready Docker Compose deployment, including a TLS reverse proxy (Caddy with automatic Let's Encrypt for a configured domain). There is no CI. A separate security review follows.

## 1. Current state (evidence)

| # | Fact | Evidence |
|---|------|----------|
| E1 | `docker compose config -q` fails on a fresh checkout: `env file .../backend.env not found` (rc=1). | local run at base |
| E2 | Ports published to the host: DB `3310:3306`, backend `5000:5000`, frontend `80`, `443`. The DB service is attached to both `database` (internal) and `public`. | `docker-compose.yml:4-7,21-22,30-33,60-62` |
| E3 | The frontend container has nothing listening on 443 and no TLS setup. | `frontend/nginx.conf:9-11` (`listen 80` only) |
| E4 | `MYSQL_ROOT_PASSWORD_FILE` is the only DB credential, so the backend has to log in as `root`. The image is `mysql:9.0.1`, an Innovation release (not LTS). | `docker-compose.yml:3,10-12` |
| E5 | `backend.env` is required but not in the repo. Its keys are documented only in the README, which includes the default `root_user_password=Passw0rd!`. | `docker-compose.yml:38-39`, `README.md:3-61` |
| E6 | The volume `template-files` is mounted at `/backend/templates`, but the backend build context `./backend` contains no templates; they are in repo-root `templates/`. The named volume therefore starts empty. Result: imprint, privacy and contact queries and every mail (reset, reminders, status change) fail with `FileNotFoundError`. | `docker-compose.yml:37`, `git ls-files templates/`, `backend/schema_queries.py:479-495`, `backend/scheduler.py:31,54,73`, `backend/mutations/mutation_users.py:184` |
| E7 | Frontend URLs are baked in at build time from the committed `frontend/.env`, which points to `http://192.168.178.169/...`. `EditRequest.tsx:773` also hardcodes `http://192.168.178.169/pdfs/`, a path nginx does not serve (`/pdf` alias, so `/pdfs/x` resolves to `.../pdfss/x`). | `frontend/.env`, `frontend/src/components/requests/EditRequest.tsx:773`, `frontend/nginx.conf:29-32` |
| E8 | The frontend falls back to the placeholder `pictures/1741980710.2106326_platzhalter_bild.png`, which is in neither the repo nor the image. | `frontend/src/components/inventory/Inventory.tsx:299,320,388`, `cart/Cart.tsx:170` |
| E9 | Backend: `python:3.12` (full), runs as root, `gunicorn -w 1`, `app.debug = True`, `graphiql=True`, `testing_on = 0` hardcoded. | `backend/Dockerfile`, `backend/config.py:61,79`, `backend/app.py:69` |
| E10 | The APScheduler `BackgroundScheduler` starts at import in every worker process and uses a SQLAlchemy jobstore. With more than one gunicorn worker, duplicate jobs and mails are possible. | `backend/config.py:97-103` |
| E11 | Schema: `app.py` runs `Base.metadata.create_all` only if table `users` is missing, then creates `root_organization` and the root user (system_admin) if missing. Alembic is not usable in the container: `alembic/` is in `backend/.dockerignore`, `alembic.ini` is gitignored, and a DB built by `create_all` is never stamped. | `backend/app.py:15-58`, `backend/.dockerignore`, `.gitignore` |
| E12 | Sessions: Flask-Session `SESSION_TYPE='sqlalchemy'`, lifetime 2h. `SESSION_COOKIE_SECURE` is not set (only a comment). CORS uses `origins: "*"` with `supports_credentials=True`. | `backend/config.py:84-93` |
| E13 | `ProxyFix(x_for=1, x_proto=1)`. nginx overwrites `X-Forwarded-Proto` with `$scheme`, so behind Caddy the backend would see `http`. | `backend/config.py:81`, `frontend/nginx.conf:24-25` |
| E14 | Mail: both branches use `smtplib.SMTP_SSL`, so `use_ssl=0` still means implicit TLS and STARTTLS (587) is unsupported. `int(use_ssl)` raises on empty or missing values. Any failure schedules a retry every 5 minutes with no limit. Password reset mails the new plaintext password. | `backend/sendMail.py:9-40`, `backend/mutations/mutation_users.py:163-190` |
| E15 | The `timezone` env var is read but never used; `Europe/Berlin` is hardcoded. | `backend/config.py:58,101` |
| E16 | nginx: `autoindex on` for `/pdf` and `/pictures`; the alias has no trailing slash (`location /pdf` → `alias /var/www/html/pdfs`); there is no `client_max_body_size`, so nginx's default 1 MB applies while the backend allows 100 MB pictures. `location /api` + `proxy_pass http://backend:5000/` produces `//graphql`; whether this works is unverified. | `frontend/nginx.conf`, `backend/mutations/mutation_files.py:78-83` |
| E17 | Frontend Dockerfile: `node:18` (EOL), `npm install` (not `npm ci`), creates unused dirs `/usr/share/nginx/html/{pdf,images}`. The PDF worker loads from `https://unpkg.com` (external CDN). `public/pdf.worker.min.js` exists locally but is unused. | `frontend/Dockerfile`, `frontend/src/index.tsx:33`, `AGB/AGBPopUp.tsx:147` |
| E18 | No `restart:` policies and no frontend healthcheck. The MySQL healthcheck `mysqladmin ping -h localhost` can pass against the temporary init server, which gives a race on the first start. The backend touches the DB at import and exits on failure. | `docker-compose.yml` |
| E19 | `.gitignore` already ignores `*.env`, `.env` and `db-password.txt`. Note that `frontend/.env` is tracked despite this. | `git check-ignore -v` |
| E20 | `backend/requirements.txt` is UTF-16LE with BOM and CRLF line endings. pip auto-detects the BOM, so the build is not blocked, but the file is fragile. `redis` is imported but unused. | `file`, `backend/config.py:11` |
| E21 | `origin/docker` (b6ab51a, based on an old `2e5dc24`) uses config.ini, Redis sessions, a `flask run --debug` entrypoint, an `nginx:1.13` proxy and hardcoded `test123`/secret key. **Nothing reusable** beyond the idea of a separate proxy service; the config model is obsolete (the current code uses env vars). | `git diff 2e5dc24 origin/docker` |

## 2. Configuration inventory

### 2.1 Backend (env, read in `backend/config.py`; `.env` is loaded only if hostname ≠ `container`)

| Key | Required | Container value / note |
|-----|----------|------------------------|
| `database_host` | yes | `database` (compose service name) |
| `database_port` | yes | `3306` (string concatenated into the URL) |
| `database_name` | yes | must equal `MYSQL_DATABASE` |
| `database_user` | yes | currently forced to `root` (E4); recommend a dedicated app user |
| `database_password` | one of | leave empty in compose |
| `database_password_location` | one of | `/run/secrets/db-password` |
| `root_directory` | yes | `/backend/` |
| `picture_directory` / `pdf_directory` / `template_directory` | yes | `pictures` / `pdfs` / `templates` (relative to root) |
| `secret_key` | yes (functionally) | if unset, `app.secret_key=None` and sessions break; must be random and ≥32 bytes |
| `root_user_name` | yes | login e-mail of the initial system admin; used only when that user does not exist |
| `root_user_password` | yes | only applied on first creation; later changes are ignored |
| `mail_server_address`, `mail_server_port`, `use_ssl`, `sender_email_address`, `sender_email_password` | functionally yes | see E14; an empty `use_ssl` breaks sending |
| `timezone` | no | unused (E15) |
| hostname `container` | yes | `hostname: container` in compose disables `load_dotenv("../backend.env")` |

Code constants that are not configurable: `testing_on=0`, `app.debug=True`, `graphiql=True`, CORS `*`, session lifetime 2h, scheduler TZ `Europe/Berlin`.

### 2.2 Frontend (CRA `react-scripts` 5, **build time only**)

| Key | Current | Note |
|-----|---------|------|
| `REACT_APP_BACKEND_URL` | `http://192.168.178.169/api/graphql` | relative `/api/graphql` works (fetch) |
| `REACT_APP_PICTURES_BASE_URL` | `http://192.168.178.169/pictures/` | relative `/pictures/` |
| `REACT_APP_PDFS_BASE_URL` | `http://192.168.178.169/pdf/` | relative `/pdf/` |
| `PUBLIC_URL` | default | `MarkdownScreen` is effectively unused now (imprint and privacy come from the backend) |

Runtime config: none. A domain-independent image needs **relative URLs** (same origin). Otherwise every domain change requires a rebuild.

### 2.3 Compose / operator inputs (proposed)

`DOMAIN` (FQDN for Caddy/ACME), `ACME_EMAIL` (optional), DB root password and app password as secret files, `backend.env` (or `.env` + `environment:`), templates directory (imprint, privacy, mail texts).

## 3. Requirements

### Functional

- **F1** One `docker compose up -d` on a fresh Linux host with Docker Engine + Compose v2 starts DB, backend, frontend and Caddy, given only the documented operator inputs (§2.3) and secret files.
- **F2** Caddy is the only service publishing host ports: `80` and `443` (optionally `443/udp` for HTTP/3). It obtains and renews a Let's Encrypt certificate for `DOMAIN` automatically and redirects HTTP to HTTPS.
- **F3** Single origin `https://DOMAIN`: `/` SPA (deep links fall back to `index.html`), `/api/` → backend, `/pictures/`, `/pdf/` → uploaded files. The frontend build uses relative URLs and contains no IP or host literals.
- **F4** On first start the backend creates the schema, the root organization and the root admin from `root_user_name` / `root_user_password` (existing behavior). Restarts are idempotent.
- **F5** Persistent named volumes for DB data, pictures, PDFs and Caddy data (certs/ACME account; loss → rate-limit risk). Templates (imprint, privacy, mails) are available to the backend on first start and editable by the operator without a rebuild.
- **F6** Uploads are written by the backend and served by the web tier from the same volume. The upload size limit along the whole chain is ≥ the backend limit (100 MB pictures) or an explicitly chosen lower value.
- **F7** A documented example config (`*.example` files) plus deploy, update, backup and restore steps. Secrets are never committed (AGENTS.md; `.gitignore` covers `*.env`, `db-password.txt`).
- **F8** A local smoke variant works without a public domain, e.g. `DOMAIN=localhost` with a Caddy internal CA cert, as required by `quality-gate.md` "Build and smoke".

### Non-functional

- **N1** DB and backend are not reachable from the host or the internet. The DB sits on an internal network only.
- **N2** Every service has `restart: unless-stopped` and a healthcheck. Startup ordering via `depends_on: condition: service_healthy`. The DB healthcheck does not report healthy during init (E18).
- **N3** Secrets come through compose `secrets:` files or an untracked env file. No secret in images, build args or the repo.
- **N4** Images are pinned to explicit versions. Base images are supported (not EOL): Node LTS ≥ 20, MySQL LTS line (see D3), maintained Caddy 2.x.
- **N5** Containers run as non-root where the image allows (backend at least). No debug server in production.
- **N6** Exactly one backend process runs the scheduler, i.e. one gunicorn worker (threads allowed) or a separate scheduler (E10). Default: keep `-w 1`, add threads if needed.
- **N7** Logs go to stdout/stderr with a bounded log driver (`max-size`/`max-file`).
- **N8** The backend sees the correct client scheme and IP through the proxy chain (E13). `SESSION_COOKIE_SECURE=True` when served over HTTPS.

## 4. Measurable acceptance

| ID | Check | Pass |
|----|-------|------|
| A1 | `docker compose config -q` with the example config copied | rc 0 |
| A2 | `docker compose build` | rc 0; ESLint warnings in touched files reported |
| A3 | `docker compose up -d` on an empty host/volumes, `docker compose ps` within ≤ 3 min | all services `healthy` (Caddy: running/healthy) |
| A4 | `curl -sI http://DOMAIN/` | 301/308 → `https://DOMAIN/` |
| A5 | `curl -s https://DOMAIN/` (prod: no `-k`; local: CA trusted or `-k` with internal CA) | 200, SPA HTML; prod certificate issuer is Let's Encrypt and the SAN equals `DOMAIN` |
| A6 | `curl -s -X POST https://DOMAIN/api/graphql -H 'content-type: application/json' -d '{"query":"{ getImprint }"}'` | 200, JSON containing the template content (shows templates are mounted) |
| A7 | Login mutation as root admin with the configured credentials | `ok: true`; the `Set-Cookie` session cookie has `Secure; HttpOnly` |
| A8 | Upload a 5 MB picture via the UI/API, then `GET https://DOMAIN/pictures/<name>` | 200; no 413 |
| A9 | `ss -tlnp` / `docker compose ps` on the host | only 80/443 (and 443/udp) published; nothing on 3306/3310/5000 |
| A10 | `docker compose down && docker compose up -d` | data, uploads and certificates persist; no new ACME order |
| A11 | Backup + restore procedure run on a test instance | restored DB + files are visible in the UI |
| A12 | `grep -r 192.168 frontend/build` (in image) | no hits |
| A13 | `docker compose exec backend id -u` | ≠ 0 (if N5 is accepted for the backend) |
| A14 | `docker compose down -v` | clean teardown (gate requirement) |

## 5. Decisions (resolved, see architecture.md)

| ID | Question | Options | Recommendation | Blocking |
|----|----------|---------|----------------|----------|
| D1 | Is there an existing deployment with data (MySQL 9.0 volume, uploads) to migrate? | a) greenfield; b) migrate existing volumes | needs an answer: decides D3, volume names, migration docs | **blocking** |
| D2 | Scope of code changes outside compose/Docker/proxy files | a) deploy files only; b) + minimal app config fixes: relative frontend URLs incl. `EditRequest.tsx:773`, `app.debug`/graphiql off, `SESSION_COOKIE_SECURE`, CORS restricted to same origin, `use_ssl`/STARTTLS | b): without the frontend URL fix the deployment cannot work on an arbitrary domain; the backend items are production hardening (security review follows) | **blocking** |
| D3 | MySQL version | a) keep `9.0.1`; b) `8.4` LTS; c) latest 9.x | b) if greenfield; if a 9.0 data volume exists, downgrade is impossible → c) | blocking via D1 |
| D4 | Topology | a) Caddy in front of the existing frontend nginx (internal only); b) Caddy replaces nginx (serves static + files + proxy) | a): minimal change, nginx config stays; fix the X-Forwarded-Proto pass-through | nonblocking (default a) |
| D5 | Single domain vs. subpaths/subdomains | a) one `DOMAIN`, all paths same origin; b) separate API domain | a): avoids CORS/cookie issues | nonblocking (default a) |
| D6 | Backup scope | a) documented manual `mysqldump` + volume tar + restore steps; b) + backup sidecar/cron with retention; c) none (operator's job) | a) | nonblocking (default a) |
| D7 | Local-dev override | a) none, only smoke via `DOMAIN=localhost`; b) `compose.override.yml` for dev (ports, hot reload) | a): b) is outside the deployment goal | nonblocking |
| D8 | Mail | a) required config; b) optional, documented as "without mail no password reset/reminders" | b), but document that a failed reset locks the user out (E14) | nonblocking |
| D9 | Templates (imprint/privacy are legally required in DE) | a) bind-mount `./templates` (operator edits); b) bake into the image + override volume | a) | nonblocking (default a) |
| D10 | Schema migration on start | a) keep `create_all` (existing); b) make Alembic runnable in the image + `upgrade head` on start | a) now; b) as a follow-up (alembic is not shipped and the DB is not stamped) | nonblocking |
| D11 | Placeholder image (E8) | a) ship it in the repo/volume seed; b) ignore | a) or a frontend fallback, small | nonblocking |
| D12 | External PDF worker from unpkg.com (privacy/CSP) | a) leave; b) use the local `public/pdf.worker.min.js` | b) if D2=b; otherwise document | nonblocking |

## 6. Non-goals

CI/CD and registry publishing (cicd.md: manual deploy); Kubernetes/Swarm; HA/multi-node; monitoring stack; automated tests; Redis sessions (`origin/docker`); application feature or behavior changes beyond D2.

## 7. Security-relevant findings for the follow-up review (not resolved here)

1. DB (`3310`) and backend (`5000`) published to the host; DB on the `public` network (E2).
2. The backend uses MySQL `root` (E4).
3. `app.debug = True` and GraphiQL are enabled in production (E9).
4. CORS `*` + `supports_credentials=True` → flask-cors reflects any origin with credentials (E12). No CSRF protection is visible.
5. The session cookie has no `Secure` flag; `secret_key` may be unset (E12, §2.1).
6. The default `root_user_password=Passw0rd!` is in the README (E5).
7. nginx `autoindex on` lists every upload; prefix locations without a trailing slash (`/pdfX` → `/var/www/html/pdfsX`); no classic off-by-slash traversal because the alias also has no slash, but the new config must keep `location` and `alias` slashes consistent (E16).
8. Uploads: no `secure_filename`, the filename comes from the client (`mutation_files.py:70-73`); SVG is allowed (stored XSS when served same-origin); no size limit for PDFs.
9. Password reset sends the plaintext password by mail and allows reset by e-mail only (E14).
10. Imprint and privacy HTML is rendered via `dangerouslySetInnerHTML` from templates (trusted operator content, note only).
11. Containers run as root; base images are full/EOL (`node:18`) (E9, E17).
12. External script from unpkg.com without SRI (E17).
13. The mail retry loop is unbounded (DoS/spam on bad config) (E14).
14. `frontend/.env` is tracked despite the `*.env` ignore rule; future real values would leak (E19).

## 8. Open questions

- D1, D2: resolved (architecture.md H1, H2).
- Does `location /api` → `//graphql` work today (Werkzeug `merge_slashes` redirect vs. 404)? Verify in the smoke run; it is fixed by `location /api/` either way.
- Target host: public IP with DNS A/AAAA for `DOMAIN`, ports 80/443 open? (ACME HTTP-01/TLS-ALPN prerequisite.)
