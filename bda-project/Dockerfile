FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
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
CMD ["uvicorn", "webapp:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
