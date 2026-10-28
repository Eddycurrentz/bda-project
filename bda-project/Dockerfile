FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 SENTINEL_ENV=production
WORKDIR /app
COPY requirements-web.txt ./requirements-web.txt
RUN pip install --no-cache-dir -r requirements-web.txt
COPY config.py security_store.py auth_service.py anomaly.py webapp.py ./
COPY web ./web
COPY data/sample_tweets.csv ./data/sample_tweets.csv
COPY output/sentiment_results.csv output/sentiment_results_enriched.csv ./output/
RUN useradd --create-home --uid 10001 sentinel && chown -R sentinel:sentinel /app
USER sentinel
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT','8000') + '/ready', timeout=3)"]
CMD ["sh", "-c", "exec uvicorn webapp:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
