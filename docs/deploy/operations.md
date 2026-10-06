# Operating the LendingSystem with Docker Compose

This guide covers the production deployment in `docker-compose.yml`: first deployment, upgrading an existing deployment, updates, backup and restore, optional HTTPS with Let's Encrypt, template editing and troubleshooting.

> **Before going live:** rotate all credentials taken over from an earlier setup ([upgrade step 13](#upgrading-from-the-previous-compose-file), [Rotating the database passwords](#rotating-the-database-passwords)), run the stack only behind a TLS-terminating reverse proxy such as Traefik ([Behind Traefik](#behind-traefik-recommended-for-production)), and keep the images up to date ([Updating](#updating)).

## Overview

The stack has three services:

| Service | Image | Role |
|---------|-------|------|
| `frontend` | `nginxinc/nginx-unprivileged` (built from `frontend/`) | Serves the web app, `/pictures/` and `/pdf/`; forwards `/api/` to the backend. Listens on 8080 inside the container. |
| `backend` | `python:3.12.15-slim` (built from `backend/`) | GraphQL API (gunicorn, one worker with four threads), runs as uid 10001. |
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
| `TRUSTED_PROXY_CIDR` | `127.0.0.1/32` | IP or CIDR of the reverse proxy, as nginx sees it. Only from this address does nginx accept `X-Forwarded-For` (client IP for the access log and the rate limit) and `X-Forwarded-Proto`. A proxy on the same host reaches nginx through Docker's port forwarding, so nginx sees the gateway of the `<project>_public` network, not `127.0.0.1`; see [Trusted proxy address](#trusted-proxy-address). |
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

On the first start MySQL creates the database `LendingSystem` and the user `DB_APP_USER`. The backend creates the tables and the initial administrator. The volumes `template-files` and `image-files` are seeded with the default templates and the placeholder picture. Docker seeds a volume only if it is empty when first mounted; existing content is never overwritten. See [Placeholder picture](#placeholder-picture).

Then point the reverse proxy at `http://<host>:HTTP_PORT`. It must set `X-Forwarded-Proto: https` and `X-Forwarded-For`, and allow request bodies of at least 100 MB (file uploads). Set `TRUSTED_PROXY_CIDR` to its address ([Trusted proxy address](#trusted-proxy-address)). It should also send `Strict-Transport-Security` (see [Security settings](#security-settings)).

The initial administrator password from `backend.env` stays valid until it is changed. After the first login, change it in the web app (profile page) or as described in [Changing the administrator password](#changing-the-administrator-password).

Check:

```sh
curl -s -X POST -H 'Content-Type: application/json' -d '{"query":"{ getImprint }"}' http://127.0.0.1:${HTTP_PORT:-80}/api/graphql
```

## Upgrading from the previous compose file

This applies to deployments started from the old `docker-compose.yml` (MySQL 9.0.1, backend connecting as `root`, `db-password.txt`, ports 80/443/3310/5000). The upgrade keeps all volumes and upgrades MySQL in place to 9.7.2. **A MySQL 9.7 data directory cannot be used with 9.0 again; the backup in step 1 is the only way back.**

0. **Find the project name.** Run `docker volume ls | grep database-data`. The part before `_database-data` is the project name. If it is not `lendingsystem`, you will set `COMPOSE_PROJECT_NAME` to it in step 4.

1. **Back up**, with the old stack still running. `umask 077` makes the files readable only by you; they contain personal data and password hashes:

   ```sh
   umask 077
   docker compose exec -T database sh -c 'MYSQL_PWD="$(cat /run/secrets/db-password)" mysqldump -uroot --single-transaction --routines --set-gtid-purged=OFF --databases LendingSystem' > backup-$(date +%F).sql
   P=<project name from step 0>
   for v in image-files pdf-files template-files; do
     docker run --rm -v ${P}_$v:/v:ro alpine:3.22 tar czf - -C /v . > $v.tgz
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

   **Mail on port 465:** the old version always used implicit TLS, whatever `use_ssl` said. The new version uses implicit TLS only with `use_ssl=1` and STARTTLS otherwise. If `mail_server_port` is `465`, set `use_ssl=1`; otherwise mail sending times out.

7. **Start and upgrade the database:**

   ```sh
   docker compose up -d database
   docker compose ps database        # wait for "healthy"
   docker compose logs database | grep -i upgrade
   ```

   The log shows `Server upgrade from '90001' to '90702' completed`.

8. **Create the backend's DB user.** The image creates it only on an empty data directory, so it must be added once here:

   ```sh
   docker compose exec -T database sh -c 'MYSQL_PWD="$(cat /run/secrets/db-root-password)" mysql -uroot' <<SQL
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
    - The old `image-files` volume is not empty, so the placeholder picture was **not** seeded. Add it if it is missing (an existing file is never overwritten):

      ```sh
      docker compose exec backend test -e /backend/pictures/1741980710.2106326_platzhalter_bild.png \
        || docker compose cp backend/static-seed/platzhalter_bild.png backend:/backend/pictures/1741980710.2106326_platzhalter_bild.png
      ```

      Check: `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:${HTTP_PORT:-80}/pictures/1741980710.2106326_platzhalter_bild.png` returns `200`.

13. **Rotate all credentials (mandatory).** Treat the passwords and keys of the old installation as known to others (for example, the old README suggested a default administrator password) and change all of them now:

    - **Administrator (root) password.** The backend never changes an existing administrator from `backend.env`; editing `root_user_password` has no effect on an existing installation. Change the password as described in [Changing the administrator password](#changing-the-administrator-password), then check that the old password no longer works. Do the same for every other account that may still use an old or shared password.
    - **`secret_key`** in `backend.env`: generate a new one (`python3 -c "import secrets;print(secrets.token_hex(32))"`).
    - **SMTP password** (`sender_email_password`): change it at the mail provider, then in `backend.env`.
    - **Database passwords:** rotate the MySQL root password that was taken over from `db-password.txt` (see [Rotating the database passwords](#rotating-the-database-passwords)). Do not reuse old database passwords anywhere.

    Then apply the changes and log out all users. Sessions are stored in the database, so a new `secret_key` alone does not end them; delete them:

    ```sh
    docker compose up -d --force-recreate backend
    docker compose exec -T database sh -c 'MYSQL_PWD="$(cat /run/secrets/db-root-password)" mysql -uroot LendingSystem -e "DELETE FROM sessions"'
    ```

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

Backups contain all personal data and the password hashes. Keep them in a directory only you can read (`install -d -m 700 backups`), create them with `umask 077` as below, and encrypt every copy that leaves the host, e.g. with [age](https://age-encryption.org) (`age -r <recipient> -o backup.sql.age backup-YYYY-MM-DD.sql`) or `gpg --symmetric`.

### Backup

```sh
P=lendingsystem
umask 077
docker compose exec -T database sh -c 'MYSQL_PWD="$(cat /run/secrets/db-root-password)" mysqldump -uroot --single-transaction --routines --set-gtid-purged=OFF --databases LendingSystem' > backup-$(date +%F).sql
for v in image-files pdf-files template-files; do
  # the archive goes to stdout, so your shell creates the file (owned by you, umask 077)
  docker run --rm -v ${P}_$v:/v:ro alpine:3.22 tar czf - -C /v . > $v-$(date +%F).tgz
done
```

With the Let's Encrypt overlay, also back up `caddy-data` the same way (it holds the certificates).

### Restore

```sh
P=lendingsystem
docker compose stop backend frontend
docker compose up -d database          # wait for "healthy"
docker compose exec -T database sh -c 'MYSQL_PWD="$(cat /run/secrets/db-root-password)" mysql -uroot' < backup-YYYY-MM-DD.sql
for v in image-files pdf-files template-files; do
  docker run --rm -v ${P}_$v:/v -v "$PWD":/b alpine:3.22 sh -c "find /v -mindepth 1 -delete && tar xzf /b/$v-YYYY-MM-DD.tgz -C /v"
done
docker compose run --rm --no-deps --user root --entrypoint chown backend -R 10001:10001 /backend/pictures /backend/pdfs /backend/templates
docker compose up -d
```

The dump contains `CREATE DATABASE`/`USE`, so it restores into the same schema. Restoring into a fresh installation also works: deploy first (which creates the DB user), then restore.

## Behind Traefik (recommended for production)

Traefik terminates TLS and manages the certificates; the stack serves plain HTTP behind it. Use one of two variants. In both, keep `session_cookie_secure=1` in `backend.env`, and add an HSTS headers middleware to the router (nginx does not send HSTS). Traefik replaces any `X-Forwarded-For`/`X-Forwarded-Proto` sent by clients (unless its entrypoint has `forwardedHeaders.insecure`), so nginx can trust what Traefik sends.

Large uploads: Traefik v3 aborts requests whose body takes longer than 60 seconds to arrive (`respondingTimeouts.readTimeout`). If uploads of big files fail, raise it in Traefik's static configuration, e.g. `entryPoints.websecure.transport.respondingTimeouts.readTimeout: 600s`.

### Variant A: Traefik with the file provider

Traefik runs elsewhere (another host, or on this host outside Docker) and reaches the published port. In `.env`, publish the port only where Traefik can reach it, and trust only Traefik:

```sh
HTTP_PORT=10.0.0.10:8080          # internal IP of this host; 127.0.0.1:8080 if Traefik runs on this host
TRUSTED_PROXY_CIDR=10.0.0.5/32    # IP of the Traefik host, as nginx sees it (see Trusted proxy address)
```

Dynamic configuration for Traefik's file provider (adjust host name, entrypoint and resolver names to your Traefik setup):

```yaml
http:
  routers:
    lendingsystem:
      rule: Host(`lend.example.org`)
      entryPoints: [websecure]
      service: lendingsystem
      middlewares: [lendingsystem-hsts]
      tls:
        certResolver: letsencrypt
  middlewares:
    lendingsystem-hsts:
      headers:
        stsSeconds: 31536000
  services:
    lendingsystem:
      loadBalancer:
        servers:
          - url: http://10.0.0.10:8080   # same address as HTTP_PORT
```

If Traefik runs on this host with `HTTP_PORT=127.0.0.1:8080`, nginx sees the gateway of the compose network, not `127.0.0.1`; set `TRUSTED_PROXY_CIDR` as described in [Trusted proxy address](#trusted-proxy-address).

### Variant B: Traefik in Docker on the same host

Traefik uses its Docker provider and reaches the frontend over a shared Docker network (here `traefik`, created with `docker network create traefik` and attached to the Traefik container). The frontend port is not published. Create `compose.override.yml` next to `docker-compose.yml` (it is git-ignored and loaded automatically):

```yaml
services:
  frontend:
    ports: !reset []
    networks: [public, traefik]
    labels:
      traefik.enable: "true"
      traefik.docker.network: traefik
      traefik.http.routers.lendingsystem.rule: Host(`lend.example.org`)
      traefik.http.routers.lendingsystem.entrypoints: websecure
      traefik.http.routers.lendingsystem.tls.certresolver: letsencrypt
      traefik.http.routers.lendingsystem.middlewares: lendingsystem-hsts
      traefik.http.middlewares.lendingsystem-hsts.headers.stsSeconds: "31536000"
      traefik.http.services.lendingsystem.loadbalancer.server.port: "8080"

networks:
  traefik:
    external: true
```

Set `TRUSTED_PROXY_CIDR` in `.env` to the subnet of the `traefik` network (only proxies and the services they route to should be attached to it):

```sh
docker network inspect traefik --format '{{(index .IPAM.Config 0).Subnet}}'
```

Then run `docker compose up -d`. If you set `COMPOSE_FILE` in `.env`, add `compose.override.yml` to it (`COMPOSE_FILE=docker-compose.yml:compose.override.yml`), because Compose then no longer loads it automatically.

Check (from any client): `curl -sI https://lend.example.org/` shows `strict-transport-security` and `content-security-policy`.

## HTTPS with Let's Encrypt

Alternative to Traefik: use this when there is no reverse proxy in front of the stack. The overlay `compose.tls.yml` adds Caddy on ports 80 and 443, obtains and renews a Let's Encrypt certificate automatically and redirects HTTP to HTTPS. The frontend port is then no longer published.

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

Caddy sends `Strict-Transport-Security: max-age=31536000`, so browsers use only HTTPS for this domain for one year after the first visit.

Certificates are stored in the `caddy-data` volume. Back it up; losing it forces a new issuance, and Let's Encrypt rate-limits repeated issuance.

Local test: with `DOMAIN=localhost`, Caddy uses its own internal CA instead of Let's Encrypt (`curl -k https://localhost/`).

## Placeholder picture

Items without pictures show `/pictures/1741980710.2106326_platzhalter_bild.png`. The backend image contains a neutral default (`backend/static-seed/platzhalter_bild.png`), which Docker copies into the `image-files` volume only when the volume is empty at first start. It never overwrites an existing file.

- **Missing after an upgrade:** run the command from upgrade step 12.
- **Use your own picture:** copy it over the default (PNG recommended; the file name must stay the same):

  ```sh
  docker compose cp my-placeholder.png backend:/backend/pictures/1741980710.2106326_platzhalter_bild.png
  ```

  It is kept across updates, because the volume is not re-seeded.

## Trusted proxy address

nginx accepts `X-Forwarded-For` and `X-Forwarded-Proto` only from `TRUSTED_PROXY_CIDR`. The client IP is used for the access log and the rate limit: if the value is wrong, all users share the rate limit of the proxy's address and get `429` errors sooner. It must match the address nginx sees for the reverse proxy:

- **Proxy on another host:** that host's IP, e.g. `10.0.0.5/32`.
- **Proxy on the same host** (e.g. `HTTP_PORT=127.0.0.1:8080`): connections arrive from the gateway of the compose network. Look it up after the first start and put it (or the whole subnet) into `.env`, then run `docker compose up -d` again:

  ```sh
  docker network inspect lendingsystem_public --format '{{(index .IPAM.Config 0).Gateway}} {{(index .IPAM.Config 0).Subnet}}'
  ```

  Replace `lendingsystem` if you set `COMPOSE_PROJECT_NAME`. Only trust addresses that clients cannot reach directly.

## Security settings

The stack applies these limits and headers. Change them in `frontend/nginx/default.conf.template`, `backend/Dockerfile` or `docker-compose.yml` and rebuild.

- **Rate limit:** `/api/` accepts 10 requests per second per client IP on average, with bursts of up to 200 requests (the web app sends one request per item when it checks availability); requests beyond that get `429 Too Many Requests`. The client IP comes from the reverse proxy ([Trusted proxy address](#trusted-proxy-address)), so a wrong `TRUSTED_PROXY_CIDR` makes all users share one limit.
- **Request types:** `POST /api/…` accepts only `application/json` and `multipart/form-data` (file uploads); other content types get `415`.
- **Sizes and timeouts:** request bodies up to 100 MB on `/api/` and 1 MB elsewhere. nginx waits at most 30 seconds for a backend response (`proxy_read_timeout 30s`) and then returns `504` to the client; the backend may still finish the request in the background. gunicorn's `--timeout 30` only restarts the worker if it stops responding entirely; it does not limit single requests.
- **Login backoff:** after 5 failed logins for the same email address within 15 minutes, further logins for that address are refused for 15 minutes, even with the correct password. The answer is the same as for a wrong password. Unknown addresses are counted the same way. A successful login resets the count. Change the limits with `login_max_failures` and `login_lockout_minutes` in `backend.env`. To unlock an account early, set a new password with `docker compose exec backend python manage.py set-password <email>`; a completed password reset also unlocks it.
- **GraphQL:** schema introspection is off unless `graphiql=1`. Queries nested deeper than `graphql_max_depth` (default 11) and query documents longer than 20 000 characters are rejected.
- **Backend workers:** one gunicorn worker with four threads. Do not add workers: the job scheduler (reminder mails) runs in every worker, so more workers would send duplicate mails.
- **Headers:** `Content-Security-Policy` (scripts, styles, pictures and fonts only from this site, no framing; templates such as the imprint therefore cannot load external pictures, fonts or scripts), `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` and `X-Content-Type-Options: nosniff`.
- **Uploaded files** (`/pictures/`, `/pdf/`) are served with `Content-Security-Policy: sandbox`, so scripts inside a file do not run on this site when the file is opened directly. SVG pictures open as a download.
- **HSTS** is not set by nginx, because nginx only speaks plain HTTP. The TLS terminator sets it: the Caddy overlay does this automatically; an upstream reverse proxy should send `Strict-Transport-Security: max-age=31536000` on HTTPS responses.
- **Containers:** all Linux capabilities are dropped (the database keeps the few its entrypoint needs to switch to the `mysql` user), `no-new-privileges` is set, the root filesystems are read-only (temporary and upload files go to anonymous volumes, the nginx configuration to `tmpfs`), and memory and process limits apply (database 1 GB, backend 512 MB, frontend 256 MB). Raise `mem_limit` in `docker-compose.yml` if the database is killed for lack of memory (`docker compose ps` shows restarts, `docker inspect --format '{{.State.OOMKilled}}' <container>`).

## Changing the administrator password

The backend creates the administrator from `root_user_name`/`root_user_password` only if that user does not exist. Later changes to these values are ignored, so a password set during an earlier installation stays valid until it is changed.

- **In the web app:** log in as the administrator, open the profile page and change the password.
- **Without a working login** (forgotten password, or the account was locked by a password reset): set a new password directly in the database. The commands ask for the new password without echoing it:

  ```sh
  read -rs NEW_PW
  HASH=$(printf '%s' "$NEW_PW" | docker compose exec -T backend python -c 'import sys; from argon2 import PasswordHasher; print(PasswordHasher().hash(sys.stdin.read()))')
  unset NEW_PW
  docker compose exec -T database sh -c 'MYSQL_PWD="$(cat /run/secrets/db-root-password)" mysql -uroot LendingSystem' <<SQL
  UPDATE \`user\` SET password_hash='$HASH' WHERE email='<root_user_name>';
  SQL
  ```

  Replace `<root_user_name>` with the login of the account. The same works for any user.

Check that the old password is rejected and the new one works.

## Rotating the database passwords

- **MySQL root password:**

  ```sh
  NEW=$(openssl rand -base64 32 | tr -d '/+=')
  docker compose exec -T database sh -c 'MYSQL_PWD="$(cat /run/secrets/db-root-password)" mysql -uroot' <<SQL
  ALTER USER IF EXISTS 'root'@'localhost' IDENTIFIED BY '$NEW';
  ALTER USER IF EXISTS 'root'@'%' IDENTIFIED BY '$NEW';
  SQL
  (umask 077; printf '%s\n' "$NEW" > secrets/db-root-password.txt)
  ```

- **Backend DB user** (`DB_APP_USER`, default `lending`):

  ```sh
  NEW=$(openssl rand -base64 32 | tr -d '/+=')
  docker compose exec -T database sh -c 'MYSQL_PWD="$(cat /run/secrets/db-root-password)" mysql -uroot' <<SQL
  ALTER USER 'lending'@'%' IDENTIFIED BY '$NEW';
  SQL
  printf '%s\n' "$NEW" > secrets/db-app-password.txt && chmod 644 secrets/db-app-password.txt
  docker compose restart backend
  ```

The secret files are mounted, so the containers see the new content immediately; MySQL itself keeps the password stored in its data directory.

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
| Requests fail with 429 | Rate limit ([Security settings](#security-settings)). If all users are affected, check `TRUSTED_PROXY_CIDR`: nginx may see every request as coming from the proxy. |
| API requests fail with 415 | The client sends a `Content-Type` other than `application/json` or `multipart/form-data`. |
| Requests fail with 504 | The backend did not answer within 30 seconds (`proxy_read_timeout`). Check `docker compose logs backend`. |
| Service health | `docker compose ps`, `docker compose logs <service>`. Logs rotate at 3 × 10 MB per container. |
