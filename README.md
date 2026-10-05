# LendingSystem

An equipment lending system for organisations at Otto von Guericke University Magdeburg (OvGU). Organisations publish a catalogue of their equipment. Users browse it, collect items in a cart and send lending requests. Organisation staff manage the requests through pickup and return. The system consists of a React frontend, a Flask/GraphQL backend and a MySQL database.

## Features

- Equipment catalogue with pictures, manuals, tags and groups
- Cart and lending requests for a chosen lending period
- Order management with status changes, pickup and return reminders by e-mail
- Multiple organisations, each with its own terms of use, and role-based user rights
- Configurable imprint, privacy policy and mail templates
- Production-ready Docker Compose deployment, with optional automatic HTTPS (Let's Encrypt)

## Security notice

Run the LendingSystem only on an internal network or behind a VPN until the known application security issues are resolved. Do not expose it directly to the internet.

## Quick start (Docker Compose)

Requirements: Docker Engine with Docker Compose v2.23.1 or newer.

```sh
git clone https://github.com/OvGU-FIN-24/LendingSystem.git
cd LendingSystem

cp .env.example .env                # set HTTP_PORT (default 80)
cp backend.env.example backend.env
chmod 600 backend.env

# database passwords
install -d -m 700 secrets
openssl rand -base64 32 | tr -d '/+=' > secrets/db-root-password.txt
openssl rand -base64 32 | tr -d '/+=' > secrets/db-app-password.txt
chmod 644 secrets/db-app-password.txt

# session secret for backend.env
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Edit `backend.env`: set `secret_key` to the generated value and choose `root_user_name` and `root_user_password` for the initial administrator. Then start the stack:

```sh
docker compose up -d
docker compose ps                   # wait until all services are "healthy"
```

Open `http://localhost:${HTTP_PORT}` (e.g. `http://localhost` with the default port).

The stack serves plain HTTP and expects a TLS-terminating reverse proxy in front of it. Without HTTPS, browsers do not send the session cookie and login fails. For a local test over plain HTTP only, set `session_cookie_secure=0` in `backend.env`.

## Documentation

[docs/deploy/operations.md](docs/deploy/operations.md) covers:

- configuration reference (`.env`, `backend.env`, secrets)
- upgrading from the previous Docker setup
- updates, backup and restore
- HTTPS with Let's Encrypt
- editing templates and troubleshooting

## Development

### Configuration outside Docker

Copy `backend.env.example` to `backend.env` and fill it in. When the backend runs outside Docker, also set the database and path keys:

```env
database_host=
database_name=
database_port=
database_user=
# either a password file or the password itself
database_password_location=../db-password.txt
database_password=
root_directory=../
picture_directory=pictures
pdf_directory=pdfs
template_directory=templates
session_cookie_secure=0
```

CORS is off by default (same origin only). If the dev frontend (`npm start`, port 3000) talks to the backend on port 5000 directly, add `cors_origins=http://localhost:3000` to `backend.env`.

### Backend
#### Install requirements
```shell
pip install -r requirements.txt
```
#### Local development
- Point `backend.env` at a reachable MySQL database (see the keys above).

#### Database evolution
- Database migration with Alembic
  - Initialize Alembic; folder already in git, but ini file is not
    ```shell
    python -m alembic.config init alembic
    ```
  - Edit the alembic.ini file in the alembic directory to point to the database
    ```ini
    sqlalchemy.url = mysql+pymysql://<db user>:<db password>@<db host>:3306/LendingSystem
    ```
  - Create a migration
    ```shell
    python -m alembic.config revision --autogenerate -m "Comment for the migration"
    ```
  - Run the migration
    ```shell
    python -m alembic.config upgrade head
    ```
  - Downgrade the migration
    ```shell
    python -m alembic.config downgrade <relative position / version code (first four characters)>
    ```

### Frontend
#### Example: GraphQL query with Apollo Client
App.tsx
```typescript
import './App.css';
import React from 'react';
import { ApolloClient, InMemoryCache, ApolloProvider, useQuery, gql } from '@apollo/client';

const client = new ApolloClient({
  uri: 'http://localhost/api/graphql',
  cache: new InMemoryCache(),
});

const GET_LOCATIONS = gql`
  query {
    filterTags {
      tagId
      name
    }
  }
`;

function DisplayLocations() {
  const { loading, error, data } = useQuery(GET_LOCATIONS, { client });

  if (loading) return <p>Loading...</p>;
  if (error) return <p>Error : {error.message}</p>;

  return data.filterTags.map(({ tagId, name }: { tagId: number, name: string }) => (
    <div key={tagId}>
      <p>
        {tagId}: {name}
      </p>
    </div>
  ));
}

export default function App() {

  return (
    <div>
      <h2>My first Apollo app 🚀</h2>
      <br/>
      <DisplayLocations />
    </div>
  );
}
```

## License

MIT, see [LICENSE](LICENSE).
