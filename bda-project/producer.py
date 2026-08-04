"""
producer.py
===========
Kafka producer that streams tweets from a CSV dataset into the
`twitter-stream` Kafka topic, one message per second, simulating a
live social-media feed.

Usage
-----
    python producer.py
    python producer.py --csv data/twitter_training.csv --rate 1.0
    python producer.py --limit 500

Press Ctrl+C at any time for a graceful shutdown.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Iterator, Optional

import pandas as pd
from kafka import KafkaProducer
from kafka.errors import KafkaError
from kafka.errors import NoBrokersAvailable


from config import DATASET, KAFKA, LOGGING

# --------------------------------------------------------------------------- #
# Logging setup
# --------------------------------------------------------------------------- #
LOGGING.producer_log_file.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=LOGGING.log_level,
    format=LOGGING.log_format,
    datefmt=LOGGING.date_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGGING.producer_log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("producer")


class GracefulShutdown:
    """Tracks SIGINT/SIGTERM so the send loop can exit cleanly."""

    def __init__(self) -> None:
        self.should_stop = False
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, frame: Optional[FrameType]) -> None:
        logger.warning("Shutdown signal received (%s). Finishing current message...", signum)
        self.should_stop = True


class TweetProducer:
    """Reads tweets from CSV and publishes them to a Kafka topic at a fixed rate."""

    def __init__(
        self,
        csv_path: Path,
        bootstrap_servers: str = KAFKA.bootstrap_servers,
        topic: str = KAFKA.topic_name,
        send_interval: float = KAFKA.send_interval_seconds,
        limit: Optional[int] = None,
    ) -> None:
        self.csv_path = csv_path
        self.topic = topic
        self.send_interval = send_interval
        self.limit = limit
        self.producer: Optional[KafkaProducer] = None
        self.bootstrap_servers = bootstrap_servers
        self.shutdown = GracefulShutdown()

        self._sent_count = 0
        self._error_count = 0

    # ----------------------------------------------------------------- #
    # Connection handling
    # ----------------------------------------------------------------- #
    def connect(self, max_retries: int = 5, retry_delay: float = 3.0) -> None:
        """Connect to the Kafka broker with retry logic."""
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Connecting to Kafka broker at %s (attempt %d/%d)...",
                    self.bootstrap_servers,
                    attempt,
                    max_retries,
                )
                self.producer = KafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    client_id=KAFKA.client_id,
                    acks=KAFKA.producer_acks,
                    retries=KAFKA.producer_retries,
                    linger_ms=KAFKA.linger_ms,
                )
                logger.info("Successfully connected to Kafka broker.")
                return
            except NoBrokersAvailable:
                logger.error(
                    "No Kafka brokers available at %s. Is the broker running "
                    "in KRaft mode on port 9092?",
                    self.bootstrap_servers,
                )
                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    raise

    # ----------------------------------------------------------------- #
    # Data loading
    # ----------------------------------------------------------------- #
    def load_tweets(self) -> Iterator[str]:
        """
        Load the dataset and yield tweet text one row at a time.

        Supports both the raw 4-column Kaggle format
        (tweet_id, entity, sentiment, tweet_text) and any CSV that
        contains a `tweet_text` or `text` column.
        """
        if not self.csv_path.exists():
            raise FileNotFoundError(
                f"Dataset not found at {self.csv_path}. "
                f"Place the Twitter Entity Sentiment Analysis CSV there "
                f"(see README.md for download instructions)."
            )

        logger.info("Loading dataset from %s", self.csv_path)

        try:
            df = pd.read_csv(self.csv_path, header=None, encoding="utf-8", on_bad_lines="skip")
        except UnicodeDecodeError:
            df = pd.read_csv(self.csv_path, header=None, encoding="latin-1", on_bad_lines="skip")

        # Case 1: raw Kaggle format with no header, 4 columns
        if df.shape[1] >= 4 and df.iloc[0].astype(str).str.match(r"^\d+$").any() is False:
            df.columns = list(DATASET.raw_columns) + [
                f"extra_{i}" for i in range(df.shape[1] - len(DATASET.raw_columns))
            ]
            text_series = df[DATASET.text_column]
        else:
            # Case 2: has a header row; try to detect the text column
            df = pd.read_csv(self.csv_path, encoding="utf-8", on_bad_lines="skip")
            candidate_cols = [c for c in df.columns if c.lower() in ("tweet_text", "text", "tweet")]
            if not candidate_cols:
                raise ValueError(
                    f"Could not find a tweet-text column in {self.csv_path}. "
                    f"Available columns: {list(df.columns)}"
                )
            text_series = df[candidate_cols[0]]

        if self.limit:
            text_series = text_series.head(self.limit)

        for tweet_text in text_series.dropna():
            cleaned = str(tweet_text).strip()
            if cleaned:
                yield cleaned

    # ----------------------------------------------------------------- #
    # Sending
    # ----------------------------------------------------------------- #
    def build_message(self, tweet_text: str, tweet_id: int) -> dict:
        """Build the JSON payload sent to Kafka."""
        return {
            "tweet_id": tweet_id,
            "tweet_text": tweet_text,
            "produced_at": datetime.now(timezone.utc).isoformat(),
        }

    def send_message(self, message: dict) -> bool:
        """Send a single message to Kafka; returns True on success."""
        try:
            future = self.producer.send(self.topic, key=str(message["tweet_id"]), value=message)
            record_metadata = future.get(timeout=10)
            logger.info(
                "Sent tweet_id=%s -> topic=%s partition=%s offset=%s",
                message["tweet_id"],
                record_metadata.topic,
                record_metadata.partition,
                record_metadata.offset,
            )
            self._sent_count += 1
            return True
        except KafkaError as exc:
            logger.error("Failed to send tweet_id=%s: %s", message["tweet_id"], exc)
            self._error_count += 1
            return False

    def run(self) -> None:
        """Main producer loop: read CSV -> send one tweet per second -> repeat."""
        self.connect()
        logger.info(
            "Starting tweet stream to topic '%s' (interval=%.1fs, limit=%s)",
            self.topic,
            self.send_interval,
            self.limit or "None",
        )

        try:
            for tweet_id, tweet_text in enumerate(self.load_tweets(), start=1):
                if self.shutdown.should_stop:
                    break

                message = self.build_message(tweet_text, tweet_id)
                self.send_message(message)
                time.sleep(self.send_interval)

        except FileNotFoundError as exc:
            logger.error(str(exc))
        except Exception as exc:  # pragma: no cover - defensive catch-all
            logger.exception("Unexpected error in producer loop: %s", exc)
        finally:
            self.shutdown_producer()

    def shutdown_producer(self) -> None:
        """Flush and close the Kafka producer cleanly."""
        if self.producer is not None:
            logger.info("Flushing and closing Kafka producer...")
            self.producer.flush(timeout=10)
            self.producer.close(timeout=10)
        logger.info(
            "Producer stopped. Messages sent=%d, errors=%d", self._sent_count, self._error_count
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream tweets from CSV into Kafka.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DATASET.raw_csv_path,
        help="Path to the tweet CSV dataset.",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=KAFKA.send_interval_seconds,
        help="Seconds to wait between messages (default: 1.0).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of tweets to send.",
    )
    parser.add_argument(
        "--bootstrap-servers",
        type=str,
        default=KAFKA.bootstrap_servers,
        help="Kafka bootstrap server address.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    producer = TweetProducer(
        csv_path=args.csv,
        bootstrap_servers=args.bootstrap_servers,
        send_interval=args.rate,
        limit=args.limit,
    )
    producer.run()


if __name__ == "__main__":
    main()
