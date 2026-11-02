# sailing_insights
This repo is about gathering insights from sailing sessions.

## Environments
- `.env` = prod/default
- `.env.dev` = development

The native backend uses `.env` automatically unless you explicitly set
`SAILING_INSIGHTS_ENV_FILE=.env.dev`.

## Run prod
Use this when you want the full app stack in Docker: Postgres, backend API, and frontend.

1. Copy the example environment and fill in local values:
```bash
cp .env.exmpl .env
```

2. Start the production stack:
```bash
docker compose up -d
```

3. Open the app:
```text
http://localhost:8080
```

Notes:
- `docker compose up -d` starts the prod/default DB, backend container, and frontend container.
- The backend container connects to the local Postgres container through the Compose network.
- `docker compose up -d` uses the current `APP_VERSION` from `.env`.

## Run dev
Use this when you want only the dev database in Docker and run backend/frontend natively.

1. Copy the example development environment and fill in local values:
```bash
cp .env.dev.exmpl .env.dev
```

2. Start only the dev Postgres database:
```bash
docker compose up -d db-dev
```

3. Start the backend API against `.env.dev`:
```bash
source backend/.venv/bin/activate
pip install -e backend
SAILING_INSIGHTS_ENV_FILE=.env.dev uvicorn src.api:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

Video overlay note:
- The session video trigger now renders an annotated copy with Python.
- If your environment was set up before this change, run `pip install -e backend` again.
- The key video library is `imageio-ffmpeg`, which provides the ffmpeg binary used to burn the SOG overlay into the video.

4. Start the frontend:
```bash
cd frontend
npm i
npm run dev
```

Notes:
- Dev uses the isolated database in `.env.dev` on port `5435`.


## Liquibase Migrations
DEV:
```bash
cd db
liquibase --defaults-file=liquibase.dev.properties update
```

PROD:
```bash
cd db
liquibase --defaults-file=liquibase.properties update
```

## Init DB
DEV:
```bash
cd db
psql -U sailing_app -h localhost -p 5435 -d sailing_dev -f init.sql
```

PROD:
```bash
cd db
psql -U sailing_app -h localhost -p 5434 -d sailing -f init.sql
```

## Copyright
Copyright (C) 2026 Chalmers Formula Sailing Team

Sailing Insights is licensed under the GNU General Public License,
version 3 or any later version.
See [COPYING.txt](COPYING.txt) for the full license.