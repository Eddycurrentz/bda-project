# SentinelPulse

SentinelPulse is a local social sentiment analytics dashboard built around the project's existing Kafka and Spark Structured Streaming pipeline. The browser dashboard is designed for Power BI-style exploration: headline metrics, sentiment trends and share, brand comparison, alert review, and a searchable tweet table. It also keeps the Power BI guide and CSV output workflow available.

## Features

- FastAPI dashboard API with a responsive browser interface and live refresh.
- TextBlob sentiment data from Spark CSV output, with sample data fallback.
- Date, brand, sentiment, and text filters; sortable/paginated tweet explorer.
- CSV and PDF report export; CSV cells are protected from spreadsheet formula execution.
- Account registration/login, Argon2 password hashes, short lived access tokens, rotating refresh cookies, CSRF checks, optional TOTP, roles, audit events, and rate limiting.
- Anomaly scoring for mention volume and negative sentiment, with alert acknowledgement.
- Optional PostgreSQL and Redis persistence; local development defaults to SQLite and in-memory limits.
- Docker Compose files for PostgreSQL, Redis, Kafka, Spark streaming, a replay producer, and the dashboard.

## Run locally

Use Python 3.11 or newer. From this directory:

```powershell
python -m venv ..\venv
..\venv\Scripts\python.exe -m pip install -r requirements-web.txt
..\venv\Scripts\python.exe -m uvicorn webapp:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. On first local start, the demo admin is created automatically:

- Email: `admin@sentinelpulse.local`
- Password: `SentinelDemo!2026`

Change this password in Settings before using real data. Local state is stored in `sentinelpulse.db` and is ignored by Git. To reset the demo database, stop the server and remove that file.

The app loads the newest Spark part-file when available, then consolidated output CSVs, and finally `data/sample_tweets.csv`. Without Kafka/Spark running, the UI is still usable with the sample dataset. The dashboard's replay and injected anomaly controls are for demonstration.

## Run the full stream stack

Docker Desktop with Compose is required. Copy `.env.example` to `.env`, set a new demo password and a long random JWT secret, then start the stack:

```powershell
Copy-Item .env.example .env
# Edit .env values before starting
 docker compose up --build
```

The dashboard is published on `http://127.0.0.1:8000`; Kafka, PostgreSQL, and Redis remain on the internal Compose network. The producer replays `data/sample_tweets.csv` continuously. Spark persists processed rows to PostgreSQL/Redis and writes the existing CSV output. To stop, run `docker compose down`.

For an existing local Kafka/Spark installation, start the consumer with `python spark_stream.py`, then the producer with `python producer.py --csv data/sample_tweets.csv`. Use `python producer.py --help` for replay options. The original Power BI model instructions remain in `dashboard/POWER_BI_GUIDE.md`.

## Configuration

All settings are environment variables; `.env.example` documents the supported names. Key values include `DATABASE_URL`, `REDIS_URL`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_TOPIC`, `SPARK_MASTER`, `SENTINEL_JWT_SECRET`, and `SENTINEL_COOKIE_SECURE`. SQLite and in-memory rate limiting are the local defaults. For password reset email, configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, and `PUBLIC_BASE_URL`; without SMTP the API returns a generic response but cannot deliver reset links.

For production, use HTTPS, a strong secret, secure cookies, a non-demo admin password, managed secrets, backups, and a real SMTP service. Set `SENTINEL_ENV=production`; startup will reject missing production secrets. The Compose stack is intended for local demos and is not a hardened public deployment. No public website has been deployed from this workspace; the link above is local to the machine running the server.

## Development and verification

```powershell
..\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
..\venv\Scripts\python.exe -m pytest -q --basetemp=.pytest-tmp
```

The GitHub Actions workflow checks Python formatting/lint, tests, security scans, secret scanning, and builds both containers. The demo includes sample social posts; model sentiment is indicative and should not be treated as a verified measure of public opinion.

## Project layout

- `webapp.py`, `auth_service.py`, `security_store.py`, `anomaly.py`: dashboard API, identity, persistence, and anomaly logic.
- `web/`: frontend HTML, CSS, and JavaScript assets.
- `producer.py`, `spark_stream.py`, `sentiment.py`, `preprocess.py`: Kafka/Spark processing pipeline.
- `data/`, `output/`: input dataset and generated analytics artifacts.
- `dashboard/POWER_BI_GUIDE.md`: Power BI Desktop connection and report setup.
- `tests/`: API, auth, RBAC, export, and anomaly tests.
