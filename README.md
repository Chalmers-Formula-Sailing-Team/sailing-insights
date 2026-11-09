# sailing_insights
This repo is about gathering insights from sailing sessions.

## Setup

### Requirements
- Docker installed [https://docs.docker.com/desktop/]
- Liquibase installed for database migrations [https://www.liquibase.com/download-community] or [https://formulae.brew.sh/formula/liquibase]
- make sure npm is installed `npm --version` or install [https://docs.npmjs.com/downloading-and-installing-node-js-and-npm]

### initial setup
1. Copy the example development environment and fill in local values:
```bash
cp .env.dev.exmpl .env.dev
```
2. Make sure the docker deamon runs (start Docker desktop)

3. Start the development Postgres database:
```bash
docker compose -f compose-dev.yaml up db-dev 
```
4. cd into db
```bash
cd db
```
5. copy the liquibase properties file
```bash
cp liquibase.properties.example liquibase.properties
```

6. Apply the migrations (create the tables)
```bash
liquibase --defaults-file=liquibase.properties update
```

7. Create virtual python environment for the backend
```bash
cd ../
python -m venv backend/.venv
```

8. Activate the environment and install the packages
```bash
source backend/.venv/bin/activate
pip install -e backend
```

7. Start the backend API against `.env.dev`:
```bash
SAILING_INSIGHTS_ENV_FILE=.env.dev uvicorn src.api:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

8. In a new terminal window we start the frontend:
```bash
cd frontend
npm i
npm run dev
```

## Run dev
Running the software after the initial setup is a bit easier:

1. Start the database 
```bash
docker compose -f compose-dev.yaml up db-dev 
```

2. start the backend (in a new terminal window)
```bash
source backend/.venv/bin/activate
pip install -e backend
SAILING_INSIGHTS_ENV_FILE=.env.dev uvicorn src.api:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

3. start the frontend (in a new terminal window)
```bash
cd frontend
npm i
npm run dev
```

Video overlay note:
- The session video trigger now renders an annotated copy with Python.
- If your environment was set up before this change, run `pip install -e backend` again.
- The key video library is `imageio-ffmpeg`, which provides the ffmpeg binary used to burn the SOG overlay into the video.



## Copyright
Copyright (C) 2026 Chalmers Formula Sailing Team

Sailing Insights is licensed under the GNU General Public License,
version 3 or any later version.
See [COPYING.txt](COPYING.txt) for the full license.