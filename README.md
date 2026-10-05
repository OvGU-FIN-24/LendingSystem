# LendingSystem
## Deployment
Production deployment with Docker Compose (configuration, first deployment, upgrade, backup and restore, optional HTTPS): see [docs/deploy/operations.md](docs/deploy/operations.md).

## Config file for local development
- copy `backend.env.example` to `backend.env` in the LendingSystem directory and fill it in
- for running the backend outside Docker, additionally set the database and path keys:
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
## For Backend
### Install requirements
```shell
pip install -r requirements.txt
```
### For local developing
- With connected VPN you can connect your current session to the server DB:

#### Database evolution
- Database migration with Alembic
  - Initialize Alembic; folder already in git, but ini file is not
    ```shell
    python - m alembic.config init alembic
    ```
  - Edit the alembic.ini file in the alembic directory to point to the database
    ```ini
    sqlalchemy.url = mysql+pymysql://administrator:<DB Password>@hades.fritz.box:3306/LendingSystem
    ```
  - Create a migration
    ```shell
    python - m alembic.config revision --autogenerate -m "Comment for the migration"
    ```
  - Run the migration
    ```shell
    python - m alembic.config upgrade head
    ```
  - Downgrade the migration
    ```shell
    python - m alembic.config downgrade <relative position / version code (first four characters)>
    ```

## For Frontend
### Successfully query request with apollo client
App.tsx
```typescript
import './App.css';
import React from 'react';
import { ApolloClient, InMemoryCache, ApolloProvider, useQuery, gql } from '@apollo/client';

const client = new ApolloClient({
  uri: 'http://hades.fritz.box/api/graphql',
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
