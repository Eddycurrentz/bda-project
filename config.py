"""
config.py
=========
Centralized configuration module for the Real-Time Social Media Sentiment
Analysis pipeline.

All Kafka, Spark, dataset, and output settings are defined here so that
every other module (producer.py, spark_stream.py, sentiment.py,
preprocess.py) can import a single, consistent source of truth.

Author  : Big Data Analytics Project Team
Course  : B.Tech AI & Data Science - Big Data Analytics
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# Base Paths
# --------------------------------------------------------------------------- #
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
OUTPUT_DIR: Path = BASE_DIR / "output"
LOG_DIR: Path = BASE_DIR / "logs"
CHECKPOINT_DIR: Path = OUTPUT_DIR / "checkpoints"

# Ensure required directories exist at import time.
for _directory in (DATA_DIR, OUTPUT_DIR, LOG_DIR, CHECKPOINT_DIR):
    _directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class KafkaConfig:
    """Kafka broker and topic configuration (KRaft mode, no ZooKeeper)."""

    bootstrap_servers: str = "localhost:9092"
    topic_name: str = "twitter-stream"
    client_id: str = "sentiment-producer"
    group_id: str = "sentiment-consumer-group"

    # Producer tuning
    producer_acks: str = "all"
    producer_retries: int = 5
    linger_ms: int = 10
    send_interval_seconds: float = 1.0  # one tweet per second

    # Consumer / Spark readStream starting offset
    starting_offsets: str = "latest"


@dataclass(frozen=True)
class SparkConfig:
    """Apache Spark / Spark Structured Streaming configuration."""

    app_name: str = "RealTimeSocialMediaSentimentAnalysis"
    master: str = "local[*]"
    shuffle_partitions: str = "4"
    max_offsets_per_trigger: str = "200"
    trigger_processing_time: str = "5 seconds"
    kafka_package: str = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1"
    log_level: str = "WARN"


@dataclass(frozen=True)
class DatasetConfig:
    """Dataset file locations and schema-related settings."""

    raw_csv_path: Path = DATA_DIR / "twitter_training.csv"
    sample_csv_path: Path = DATA_DIR / "sample_tweets.csv"

    # Raw Kaggle "Twitter Entity Sentiment Analysis" columns
    raw_columns: tuple = ("tweet_id", "entity", "sentiment_label", "tweet_text")

    # Column we actually stream (text only, per project spec)
    text_column: str = "tweet_text"


@dataclass(frozen=True)
class OutputConfig:
    """Output file configuration for streamed sentiment results."""

    sentiment_csv_path: Path = OUTPUT_DIR / "sentiment_results.csv"
    sentiment_csv_dir: Path = OUTPUT_DIR / "sentiment_stream"
    visualization_dir: Path = OUTPUT_DIR / "visualizations"
    output_columns: tuple = (
        "timestamp",
        "tweet",
        "clean_tweet",
        "polarity",
        "subjectivity",
        "sentiment",
    )


@dataclass(frozen=True)
class NLPConfig:
    """Thresholds used to convert TextBlob polarity into sentiment labels."""

    positive_threshold: float = 0.05
    negative_threshold: float = -0.05
    language: str = "english"


@dataclass(frozen=True)
class LoggingConfig:
    """Application-wide logging configuration."""

    log_format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    log_level: str = os.getenv("SENTIMENT_LOG_LEVEL", "INFO")
    producer_log_file: Path = LOG_DIR / "producer.log"
    spark_log_file: Path = LOG_DIR / "spark_stream.log"


# --------------------------------------------------------------------------- #
# Singleton-style config instances (import these in other modules)
# --------------------------------------------------------------------------- #
KAFKA: KafkaConfig = KafkaConfig()
SPARK: SparkConfig = SparkConfig()
DATASET: DatasetConfig = DatasetConfig()
OUTPUT: OutputConfig = OutputConfig()
NLP: NLPConfig = NLPConfig()
LOGGING: LoggingConfig = LoggingConfig()


def as_dict() -> dict:
    """Return the full configuration as a nested dictionary (useful for logging/debug)."""
    return {
        "kafka": KAFKA.__dict__,
        "spark": SPARK.__dict__,
        "dataset": {k: str(v) for k, v in DATASET.__dict__.items()},
        "output": {k: str(v) for k, v in OUTPUT.__dict__.items()},
        "nlp": NLP.__dict__,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(as_dict(), indent=2, default=str))
