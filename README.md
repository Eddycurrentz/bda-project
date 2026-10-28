# Real-Time Social Media Sentiment Analysis

**Apache Kafka · Apache Spark Structured Streaming · Python · TextBlob · Power BI**

A Big Data Analytics project (B.Tech AI & Data Science) that streams tweets in
real time, cleans and analyzes their sentiment with NLP, and visualizes the
results on a live Power BI dashboard.

---

## 1. Architecture

```
 CSV Dataset (Kaggle Twitter Entity Sentiment)
        │
        ▼
 Python Kafka Producer  (producer.py)
        │  one tweet / second, JSON payload
        ▼
 Kafka Topic: twitter-stream   (KRaft mode, localhost:9092)
        │
        ▼
 Spark Structured Streaming    (spark_stream.py)
   ├─ Parse JSON (DataFrame API only, no RDD)
   ├─ Clean text (preprocess.py)
   ├─ Score sentiment (sentiment.py — TextBlob)
        │
        ▼
 CSV Output (output/sentiment_stream/*.csv)
        │
        ▼
 Power BI Dashboard  (dashboard/POWER_BI_GUIDE.md)
```

---

## 2. Folder Structure

```
SocialMediaSentiment/
├── data/                       # Dataset + sample data
│   ├── sample_tweets.csv
│   └── DATASET_INSTRUCTIONS.md
├── output/                     # Generated at runtime
│   ├── sentiment_stream/       # Streaming CSV part-files
│   ├── sentiment_results.csv   # Consolidated CSV for Power BI
│   └── visualizations/         # matplotlib PNG charts
├── producer.py                 # Kafka producer (CSV -> Kafka)
├── spark_stream.py             # Spark Structured Streaming job
├── sentiment.py                # TextBlob sentiment scoring
├── preprocess.py                # Text cleaning / tokenization
├── visualize.py                 # matplotlib charts
├── config.py                    # Central configuration
├── requirements.txt
├── README.md
├── dashboard/                    # Power BI setup guide
├── report/                       # IEEE-format project report
├── presentation/                 # 15-slide PPT
└── screenshots/                  # Execution screenshots
```

---

## 3. Prerequisites

| Component | Version |
|---|---|
| OS | Windows 11 |
| Python | 3.14 |
| Java (JDK) | 17 |
| Apache Kafka | 3.9.1 (KRaft mode) |
| Apache Spark | bundled via PySpark 3.5.1 |
| Power BI Desktop | latest |

Kafka must already be running in **KRaft mode** with the topic `twitter-stream`
created, and `SparkSession` must already work on your machine (per the project
brief, this is assumed to be verified).

---

## 4. Installation

```powershell
# 1. Clone / copy the project folder, then create a virtual environment
cd SocialMediaSentiment
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download NLTK corpora (one-time)
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords')"

# 4. Place the dataset
#    See data/DATASET_INSTRUCTIONS.md
#    (a ready-to-use data/sample_tweets.csv is already included)
```

---

## 5. Execution

Open **three terminals**.

### Terminal 1 — Start Kafka (KRaft mode, if not already running)

```powershell
# from your Kafka installation directory
.\bin\windows\kafka-server-start.bat .\config\kraft\server.properties
```

Create the topic if it does not already exist:

```powershell
.\bin\windows\kafka-topics.bat --create --topic twitter-stream --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
```

### Terminal 2 — Start the Spark Structured Streaming consumer

```powershell
cd SocialMediaSentiment
venv\Scripts\activate
python spark_stream.py
```

### Terminal 3 — Start the Kafka producer

```powershell
cd SocialMediaSentiment
venv\Scripts\activate
python producer.py --csv data/sample_tweets.csv
```

You will see:
- **Terminal 3** logging every tweet sent to Kafka.
- **Terminal 2** printing parsed + scored micro-batches to the console every 5 seconds,
  and continuously appending CSV files to `output/sentiment_stream/`.

Stop either process at any time with `Ctrl+C` — both shut down gracefully.

### Generate offline visualizations

```powershell
python visualize.py
```

This produces `sentiment_distribution.png`, `word_frequency.png`, and
`time_series.png` inside `output/visualizations/`.

### Load into Power BI

Follow `dashboard/POWER_BI_GUIDE.md` to connect Power BI Desktop to
`output/sentiment_results.csv` (or the `output/sentiment_stream/` folder for
a folder-based combined query) and build the dashboard.

---

## 6. Output Schema

Each row written to `output/sentiment_stream/*.csv`:

| Column | Type | Description |
|---|---|---|
| timestamp | datetime | Time the record was processed by Spark |
| tweet | string | Original raw tweet text |
| clean_tweet | string | Cleaned, lowercase, stopword-free text |
| polarity | float | TextBlob polarity, -1.0 to 1.0 |
| subjectivity | float | TextBlob subjectivity, 0.0 to 1.0 |
| sentiment | string | Positive / Neutral / Negative |
| confidence | float | Derived confidence score, 0.0 to 1.0 |

---

## 7. Screenshots

Placeholders are provided in `screenshots/`:

- `01_kafka_topic_created.png`
- `02_producer_running.png`
- `03_spark_streaming_console.png`
- `04_output_csv.png`
- `05_powerbi_dashboard.png`

Replace these with your own captures when running the project end-to-end.

---

## 8. Future Improvements

- Replace TextBlob with a fine-tuned transformer model (e.g., DistilBERT) for
  higher sentiment accuracy on informal, sarcastic text.
- Add entity-level sentiment aggregation (per brand/topic) using the `entity`
  column already present in the Kaggle dataset.
- Move from local `local[*]` Spark master to a multi-node Spark cluster for
  true distributed processing at scale.
- Push results to a proper OLAP store (e.g., PostgreSQL, Delta Lake) instead
  of flat CSV files, with Power BI connecting via DirectQuery for true
  real-time refresh.
- Add a REST/WebSocket dashboard as an alternative to Power BI for live
  demos without needing Power BI Desktop installed.
- Containerize the full stack with Docker Compose for one-command startup
  (explicitly out of scope for this iteration per project constraints).

---

## 9. Author

Big Data Analytics Project — B.Tech Artificial Intelligence & Data Science
