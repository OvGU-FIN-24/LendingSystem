# Operating the LendingSystem with Docker Compose

This guide covers the production deployment in `docker-compose.yml`: first deployment, upgrading an existing deployment, updates, backup and restore, optional HTTPS with Let's Encrypt, template editing and troubleshooting.

## Overview

The stack has three services:

| Service | Image | Role |
|---------|-------|------|
| `frontend` | `nginxinc/nginx-unprivileged` (built from `frontend/`) | Serves the web app, `/pictures/` and `/pdf/`; forwards `/api/` to the backend. Listens on 8080 inside the container. |
| `backend` | `python:3.12-slim` (built from `backend/`) | GraphQL API (gunicorn, one worker), runs as uid 10001. |
| `database` | `mysql:9.7.2` (LTS) | Data. Reachable only from the backend. |

Only the frontend publishes a port: `HTTP_PORT` (default `80`). It serves **plain HTTP**. TLS is expected to be terminated in front of the stack by a reverse proxy or load balancer, which must send `X-Forwarded-Proto` and `X-Forwarded-For`. If there is no such proxy, use the Let's Encrypt overlay ([HTTPS with Let's Encrypt](#https-with-lets-encrypt)).

Data lives in four named volumes: `database-data`, `image-files`, `pdf-files` and `template-files`. With the default project name they are called `lendingsystem_<name>`.

Requirements: Docker Engine with Docker Compose v2.23.1 or newer (`docker compose version`).

## Configuration files

| File | Purpose | In git |
|------|---------|--------|
| `.env` | Compose settings: port, trusted proxy, DB user, secret paths, optional overlay. Template: `.env.example`. | no |
| `backend.env` | Application settings: secret key, initial admin, mail, cookie and CORS options. Template: `backend.env.example`. | no |
| `secrets/db-root-password.txt` | MySQL root password (database only). | no |
| `secrets/db-app-password.txt` | Password of the backend's DB user (database and backend). | no |

### `.env`

| Key | Default | Meaning |
|-----|---------|---------|
| `COMPOSE_PROJECT_NAME` | `lendingsystem` | Only set this when upgrading an old deployment whose volumes have a different prefix. |
| `HTTP_PORT` | `80` | Published port, `[ip:]port`. Use e.g. `127.0.0.1:8080` when the reverse proxy runs on the same host. |
| `TRUSTED_PROXY_CIDR` | `127.0.0.1/32` | IP or CIDR of the reverse proxy. Its `X-Forwarded-For` header is used as the client IP in the access log. |
| `DB_APP_USER` | `lending` | DB user of the backend. |
| `DB_ROOT_PASSWORD_FILE`, `DB_APP_PASSWORD_FILE` | `./secrets/…` | Secret file paths. |
| `COMPOSE_FILE`, `DOMAIN`, `ACME_EMAIL` | unset | Only for the Let's Encrypt overlay. |

### `backend.env`

| Key | Required | Meaning |
|-----|----------|---------|
| `secret_key` | yes | Session signing key. The backend refuses to start without it. |
| `root_user_name`, `root_user_password` | yes | Initial system administrator. Created only if this user does not exist yet; changing the values later does not change an existing user. |
| `session_cookie_secure` | default `1` | Session cookie only over HTTPS. Set `0` only for local tests over plain HTTP. |
| `mail_server_address`, `mail_server_port`, `use_ssl`, `sender_email_address`, `sender_email_password` | optional | SMTP. `use_ssl=1` uses implicit TLS (usually port 465); any other value uses STARTTLS (usually port 587). |
| `graphiql` | default `0` | `1` enables the GraphiQL UI at `/api/graphql`. |
| `cors_origins` | default empty | Comma-separated list of allowed foreign origins. Empty means same origin only, which is all the bundled frontend needs. |

The database host, user, password file and storage paths are set in `docker-compose.yml` and override any values in `backend.env`.

**Mail is optional, with one caveat.** If `mail_server_address` is empty, no mails are sent (password reset, pickup/return reminders, order status) and the backend logs `Mail disabled`. A password reset still sets a new random password, but the user never receives it and is locked out until an administrator sets a new password.

## First deployment

```sh
git clone https://github.com/OvGU-FIN-24/LendingSystem.git && cd LendingSystem

cp .env.example .env              # set HTTP_PORT and TRUSTED_PROXY_CIDR
cp backend.env.example backend.env
chmod 600 backend.env             # set secret_key, root_user_name, root_user_password, mail

# secret key for backend.env
python3 -c "import secrets;print(secrets.token_hex(32))"

# database passwords
install -d -m 700 secrets
openssl rand -base64 32 | tr -d '/+=' > secrets/db-root-password.txt
openssl rand -base64 32 | tr -d '/+=' > secrets/db-app-password.txt
chmod 600 secrets/db-root-password.txt
chmod 644 secrets/db-app-password.txt   # must be readable by the backend user (uid 10001); the directory stays 0700

docker compose up -d --build
docker compose ps                 # wait until all services are "healthy" (first start: about 1–2 minutes)
```

On the first start MySQL creates the database `LendingSystem` and the user `DB_APP_USER`. The backend creates the tables and the initial administrator. The volumes `template-files` and `image-files` are seeded with the default templates and the placeholder picture.

Then point the reverse proxy at `http://<host>:HTTP_PORT`. It must set `X-Forwarded-Proto: https` and `X-Forwarded-For`, and allow request bodies of at least 100 MB (file uploads).

Check:

```sh
curl -s -X POST -H 'Content-Type: application/json' -d '{"query":"{ getImprint }"}' http://127.0.0.1:${HTTP_PORT:-80}/api/graphql
```

## Upgrading from the previous compose file

This applies to deployments started from the old `docker-compose.yml` (MySQL 9.0.1, backend connecting as `root`, `db-password.txt`, ports 80/443/3310/5000). The upgrade keeps all volumes and upgrades MySQL in place to 9.7.2. **A MySQL 9.7 data directory cannot be used with 9.0 again; the backup in step 1 is the only way back.**

0. **Find the project name.** Run `docker volume ls | grep database-data`. The part before `_database-data` is the project name. If it is not `lendingsystem`, you will set `COMPOSE_PROJECT_NAME` to it in step 4.

1. **Back up**, with the old stack still running:

   ```sh
   docker compose exec database sh -c 'mysqldump -uroot -p"$(cat /run/secrets/db-password)" --single-transaction --routines --set-gtid-purged=OFF --databases LendingSystem' > backup-$(date +%F).sql
   P=<project name from step 0>
   for v in image-files pdf-files template-files; do
     docker run --rm -v ${P}_$v:/v:ro -v "$PWD":/b alpine:3.22 tar czf /b/$v.tgz -C /v .
   done
   ```

   Check that `backup-*.sql` is not empty and ends with `-- Dump completed`.

2. **Stop the old stack:** `docker compose down`. Do **not** use `-v`; it deletes the volumes.

3. **Check out the new version:** `git pull` (or check out the release).

4. **Create `.env`:** `cp .env.example .env`. Set `HTTP_PORT`, `TRUSTED_PROXY_CIDR` and, if needed, `COMPOSE_PROJECT_NAME` from step 0.

5. **Move and create the secrets:**

   ```sh
   install -d -m 700 secrets
   mv db-password.txt secrets/db-root-password.txt
   chmod 600 secrets/db-root-password.txt
   openssl rand -base64 32 | tr -d '/+=' > secrets/db-app-password.txt
   chmod 644 secrets/db-app-password.txt
   ```

6. **Update `backend.env`:** make sure `secret_key` is set and add `session_cookie_secure=1`. The database and path keys can be removed; compose overrides them anyway.

7. **Start and upgrade the database:**

   ```sh
   docker compose up -d database
   docker compose ps database        # wait for "healthy"
   docker compose logs database | grep -i upgrade
   ```

   The log shows `Server upgrade from '90001' to '90702' completed`.

8. **Create the backend's DB user.** The image creates it only on an empty data directory, so it must be added once here:

   ```sh
   docker compose exec -T database sh -c 'mysql -uroot -p"$(cat /run/secrets/db-root-password)"' <<SQL
   CREATE USER IF NOT EXISTS 'lending'@'%' IDENTIFIED BY '$(cat secrets/db-app-password.txt)';
   GRANT ALL PRIVILEGES ON \`LendingSystem\`.* TO 'lending'@'%';
   SQL
   ```

   Replace `lending` if you changed `DB_APP_USER`.

9. **Fix file ownership.** The old backend wrote uploads as root; the new one runs as uid 10001:

   ```sh
   docker compose run --rm --no-deps --user root --entrypoint chown backend -R 10001:10001 /backend/pictures /backend/pdfs /backend/templates
   ```

10. **Start everything:** `docker compose up -d --build`, then `docker compose ps` until all services are healthy.

11. **Repoint the reverse proxy** from the old ports 80/443 to `HTTP_PORT` (plain HTTP), with `X-Forwarded-Proto: https` and `X-Forwarded-For`.

12. **Verify:** log in as an existing user, open an item with pictures, upload a picture, and open the imprint and privacy pages.

    - If the old `template-files` volume was empty, it has now been filled with the default templates.
    - If it contained your own templates, they are kept unchanged.

**Rollback:** `docker compose down`, remove the database volume (`docker volume rm ${P}_database-data`), check out the previous version, put `db-password.txt` back, start the old stack and restore the dump from step 1 ([Restore](#restore)), using secret name `db-password` instead of `db-root-password`.

## Updating

```sh
git pull
docker compose up -d --build
docker compose ps
```

Back up first (next section). Old images can be removed with `docker image prune`.

Templates are copied into the `template-files` volume only when it is empty. Template changes in a new release therefore do not reach an existing installation automatically; see [Editing templates](#editing-templates).

## Backup and restore

Backups are manual. Run them regularly (e.g. via cron) and keep copies off the host. `P` is the project name (`lendingsystem` unless `COMPOSE_PROJECT_NAME` is set).

### Backup

```sh
P=lendingsystem
docker compose exec -T database sh -c 'mysqldump -uroot -p"$(cat /run/secrets/db-root-password)" --single-transaction --routines --set-gtid-purged=OFF --databases LendingSystem' > backup-$(date +%F).sql
for v in image-files pdf-files template-files; do
  docker run --rm -v ${P}_$v:/v:ro -v "$PWD":/b alpine:3.22 tar czf /b/$v-$(date +%F).tgz -C /v .
done
```

With the Let's Encrypt overlay, also back up `caddy-data` the same way (it holds the certificates).

### Restore

```sh
P=lendingsystem
docker compose stop backend frontend
docker compose up -d database          # wait for "healthy"
docker compose exec -T database sh -c 'mysql -uroot -p"$(cat /run/secrets/db-root-password)"' < backup-YYYY-MM-DD.sql
for v in image-files pdf-files template-files; do
  docker run --rm -v ${P}_$v:/v -v "$PWD":/b alpine:3.22 sh -c "find /v -mindepth 1 -delete && tar xzf /b/$v-YYYY-MM-DD.tgz -C /v"
done
docker compose run --rm --no-deps --user root --entrypoint chown backend -R 10001:10001 /backend/pictures /backend/pdfs /backend/templates
docker compose up -d
```

The dump contains `CREATE DATABASE`/`USE`, so it restores into the same schema. Restoring into a fresh installation also works: deploy first (which creates the DB user), then restore.

## HTTPS with Let's Encrypt

Use this when there is no reverse proxy in front of the stack. The overlay `compose.tls.yml` adds Caddy on ports 80 and 443, obtains and renews a Let's Encrypt certificate automatically and redirects HTTP to HTTPS. The frontend port is then no longer published.

Prerequisites:

- A DNS `A` record (and `AAAA` for IPv6) for the domain pointing to the host.
- Ports 80/tcp and 443/tcp (and optionally 443/udp for HTTP/3) reachable from the internet and not used by anything else on the host.

Enable it in `.env`:

```sh
COMPOSE_FILE=docker-compose.yml:compose.tls.yml
DOMAIN=lend.example.org
ACME_EMAIL=ops@example.org
```

Then run `docker compose up -d` and check with `docker compose logs caddy` that the certificate was obtained. Keep `session_cookie_secure=1`.

Certificates are stored in the `caddy-data` volume. Back it up; losing it forces a new issuance, and Let's Encrypt rate-limits repeated issuance.

Local test: with `DOMAIN=localhost`, Caddy uses its own internal CA instead of Let's Encrypt (`curl -k https://localhost/`).

## Editing templates

Imprint, privacy policy, contact information and mail texts are HTML files in the `template-files` volume (defaults in `templates/`). To change one:

```sh
docker compose cp backend:/backend/templates/imprint.html .
# edit imprint.html
docker compose cp imprint.html backend:/backend/templates/imprint.html
```

The pages read the files on each request; no restart is needed. To take over the defaults of a new release, copy the file from `templates/` in the repository the same way.

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `docker compose up` fails with `env file … backend.env not found` | Create `backend.env` from `backend.env.example`. |
| Backend restarts, log `secret_key is not set` | Set `secret_key` in `backend.env`. |
| Backend log `Permission denied: '/run/secrets/db-app-password'` | `chmod 644 secrets/db-app-password.txt` (keep `secrets/` at 0700). |
| Backend log `Access denied for user 'lending'` after an upgrade | Step 8 of the upgrade was skipped, or the password in `secrets/db-app-password.txt` changed. Run step 8 again with `ALTER USER` instead of `CREATE USER IF NOT EXISTS`. |
| Login works but the session is lost immediately | The browser reached the site over plain HTTP while `session_cookie_secure=1`. Use HTTPS, or `0` for local tests only. |
| Upload fails with permission denied | Run the `chown` from upgrade step 9. |
| Upload fails with 413 | The reverse proxy in front limits body size; allow at least 100 MB. |
| Service health | `docker compose ps`, `docker compose logs <service>`. Logs rotate at 3 × 10 MB per container. |
