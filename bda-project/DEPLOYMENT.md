# Hosting SentinelPulse

SentinelPulse can run on any host that builds Docker images and provides a persistent PostgreSQL database. This guide uses a provider-neutral setup; the exact dashboard names differ by host.

## 1. Push the repository

Push the project to a GitHub repository and connect that repository to a Docker web service. Select the repository root as the build context and `Dockerfile` as the build file. The GitHub Actions workflow runs on pushes to `main` and pull requests targeting `main`.

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
