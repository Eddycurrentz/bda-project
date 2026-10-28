# Hosting SentinelPulse

SentinelPulse can run on Vercel's FastAPI/Python runtime or a Docker host. Both production options need a persistent PostgreSQL database. This guide covers Vercel and a provider-neutral container setup.

## Vercel

1. Push this repository to GitHub and import it at [vercel.com/new](https://vercel.com/new). With the repository root selected, Vercel uses the root `index.py` entrypoint, which loads the app from `bda-project/`, and installs the lightweight root `requirements.txt`. You can alternatively set **Root Directory** to `bda-project` to deploy directly from that subfolder.
2. Provision managed PostgreSQL (for example, a provider with a pooled connection string) and add the environment variables in Vercel Project Settings. Use separate databases for Preview and Production.
3. Set `SENTINEL_ENV=production`, `DATABASE_URL`, `SENTINEL_JWT_SECRET` (random, at least 32 characters), `SENTINEL_COOKIE_SECURE=true`, `SENTINEL_DEMO_EMAIL`, `SENTINEL_DEMO_PASSWORD` (a unique password meeting the app policy), and `PUBLIC_BASE_URL` (the exact HTTPS deployment domain). Add `REDIS_URL` for cross-instance rate limits and shared live events. Configure `SMTP_*` if password reset email is needed.
4. Redeploy after setting the variables. The dashboard's static files and bundled 100-row demo fixture are included. Vercel's function filesystem is temporary, so keep identities, audit records, and tweet records in PostgreSQL. Do not rely on writing generated CSVs, checkpoints, or logs to the deployment directory. Run Kafka/Spark ingestion as a separate service and persist processed data in an external store before exposing it to the hosted dashboard.

Vercel supports FastAPI and WebSockets, but each function instance and live connection has a configured duration. The browser reconnects after a dropped socket; use Redis when multiple instances need to share live events. The current replay/injected demo controls use in-memory state and are intended for local demonstration, not durable hosted jobs.

See [Vercel's FastAPI deployment guide](https://vercel.com/docs/frameworks/backend/fastapi) for current runtime and function limits.

## Docker host

The container instructions below work on hosts that build Docker images and provide persistent PostgreSQL. The exact dashboard names differ by host.

## 1. Push the repository

Push the project to GitHub and connect the repository to a Docker web service. Set the build context to the `bda-project` directory and the build file to `Dockerfile`. The repository-level GitHub Actions workflow runs on pushes to `main` and pull requests targeting `main`.

Do not commit `.env` files, database files, or the downloaded Kaggle source CSVs. `.gitignore` and `.dockerignore` exclude them. `.env.example` contains placeholders for local Docker Compose only; do not use those placeholder values in a hosted service.

## 2. Provision persistent storage

Create a managed PostgreSQL database and set `DATABASE_URL` on the web service to its private connection string. Production startup refuses to use local SQLite because most container filesystems are temporary. Redis is optional; without it the dashboard uses process-local rate limits and does not receive cross-container live events.

The bundled 100-row sample data is copied into the image for a working first launch. To load live project output, use a persistent volume or an ingestion process that writes to the app's `output/` directory, or connect the existing Kafka/Spark services separately.

## 3. Set hosted environment variables

Set these variables in the hosting provider's secret/environment settings:

| Variable | Value |
|---|---|
| `PORT` | Use the port assigned by the host. The image defaults to `8000` for local use. |
| `SENTINEL_ENV` | `production` |
| `DATABASE_URL` | Private PostgreSQL connection string |
| `SENTINEL_JWT_SECRET` | A randomly generated secret of at least 32 characters |
| `SENTINEL_COOKIE_SECURE` | `true` |
| `SENTINEL_DEMO_EMAIL` | Email address for the initial administrator account |
| `SENTINEL_DEMO_PASSWORD` | Unique password with 12+ characters, upper/lower case, a number, and a symbol |
| `PUBLIC_BASE_URL` | The final public HTTPS URL, such as `https://sentiment.example.com` |

The initial admin account is created once when the database is empty. Keep the database persistent and protect the admin credentials. The sign-in page does not show local demo credentials in production. Set `REDIS_URL` and the `SMTP_*` variables if you want shared live events/rate limits and password reset email.

## 4. Health and public access

Configure the host's health check to use `/ready`. The Docker image listens on `0.0.0.0:$PORT` and includes a container health check. Terminate TLS at the host or its trusted proxy so secure cookies and reset links use HTTPS.

For a local image check, build from this directory and run the container with the same production variables. `docker-compose.yml` is for a local full-stack demo and deliberately binds its web port to loopback; use the `Dockerfile` for a public web service.

## 5. Dataset and pipeline notes

The image includes the 100-row synthetic demo fixture, not the full Kaggle dataset. The full training CSV must be downloaded separately and should not be committed. The web service can display processed Spark output CSVs placed under `output/`. Running Kafka and Spark on a hosted platform requires separate services and sufficient memory; it is not required to host the dashboard demo.
