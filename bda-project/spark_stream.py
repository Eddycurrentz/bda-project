"""
spark_stream.py
================
Apache Spark Structured Streaming job that:

    1. Reads raw JSON tweet messages continuously from the Kafka topic
       `twitter-stream` (localhost:9092).
    2. Parses the JSON payload into a structured DataFrame.
    3. Cleans tweet text (via preprocess.clean_tweet, wrapped as a UDF).
    4. Scores sentiment (via sentiment.analyze_text, wrapped as a UDF).
    5. Continuously appends results to CSV under output/sentiment_stream/.

Uses DataFrames exclusively (no RDD API), per project requirements.

Run
---
    python spark_stream.py

Requires the Spark-Kafka connector package; if you run via
`spark-submit` instead of `python`, add:

    spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 spark_stream.py
"""

from __future__ import annotations

import logging
import os
import sys

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, current_timestamp, from_json, udf
from pyspark.sql.types import (
    FloatType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from config import KAFKA, LOGGING, OUTPUT, SPARK
from preprocess import clean_tweet
from sentiment import analyze_text

# --------------------------------------------------------------------------- #
# Logging setup
# --------------------------------------------------------------------------- #
LOGGING.spark_log_file.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=LOGGING.log_level,
    format=LOGGING.log_format,
    datefmt=LOGGING.date_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGGING.spark_log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("spark_stream")

# Make the Spark-Kafka connector available even when launched with `python`
# rather than `spark-submit` (PySpark will fetch it via Maven on first run).
os.environ.setdefault(
    "PYSPARK_SUBMIT_ARGS", f"--packages {SPARK.kafka_package} pyspark-shell"
)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
# Schema of the JSON payload produced by producer.py
TWEET_SCHEMA = StructType(
    [
        StructField("tweet_id", IntegerType(), True),
        StructField("tweet_text", StringType(), True),
        StructField("produced_at", StringType(), True),
    ]
)

# Schema returned by the sentiment analysis UDF
SENTIMENT_SCHEMA = StructType(
    [
        StructField("polarity", FloatType(), False),
        StructField("subjectivity", FloatType(), False),
        StructField("sentiment", StringType(), False),
        StructField("confidence", FloatType(), False),
    ]
)


def build_spark_session() -> SparkSession:
    """Create (or fetch) the SparkSession configured for structured streaming."""
    spark = (
        SparkSession.builder.appName(SPARK.app_name)
        .master(SPARK.master)
        .config("spark.sql.shuffle.partitions", SPARK.shuffle_partitions)
        .config("spark.jars.packages", SPARK.kafka_package)
        .config("spark.sql.streaming.schemaInference", "true")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(SPARK.log_level)
    logger.info("SparkSession created: %s (master=%s)", SPARK.app_name, SPARK.master)
    return spark


def read_kafka_stream(spark: SparkSession) -> DataFrame:
    """Read the raw Kafka stream as a DataFrame of (key, value, timestamp, ...)."""
    logger.info(
        "Subscribing to Kafka topic '%s' on %s", KAFKA.topic_name, KAFKA.bootstrap_servers
    )
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA.bootstrap_servers)
        .option("subscribe", KAFKA.topic_name)
        .option("startingOffsets", KAFKA.starting_offsets)
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", SPARK.max_offsets_per_trigger)
        .load()
    )


def parse_json_payload(raw_df: DataFrame) -> DataFrame:
    """Decode the Kafka `value` column (bytes) into structured columns via TWEET_SCHEMA."""
    return (
        raw_df.selectExpr("CAST(value AS STRING) AS json_value", "timestamp AS kafka_timestamp")
        .withColumn("data", from_json(col("json_value"), TWEET_SCHEMA))
        .select(
            col("data.tweet_id").alias("tweet_id"),
            col("data.tweet_text").alias("tweet"),
            col("data.produced_at").alias("produced_at"),
            col("kafka_timestamp"),
        )
        .filter(col("tweet").isNotNull())
    )


def apply_cleaning_and_sentiment(parsed_df: DataFrame) -> DataFrame:
    """Attach clean_tweet and sentiment columns using registered Spark UDFs."""
    clean_udf = udf(clean_tweet, StringType())
    sentiment_udf = udf(analyze_text, SENTIMENT_SCHEMA)

    with_clean = parsed_df.withColumn("clean_tweet", clean_udf(col("tweet")))
    with_sentiment = with_clean.withColumn("sentiment_struct", sentiment_udf(col("clean_tweet")))

    result_df = with_sentiment.select(
        current_timestamp().alias("timestamp"),
        col("tweet"),
        col("clean_tweet"),
        col("sentiment_struct.polarity").alias("polarity"),
        col("sentiment_struct.subjectivity").alias("subjectivity"),
        col("sentiment_struct.sentiment").alias("sentiment"),
        col("sentiment_struct.confidence").alias("confidence"),
    )
    return result_df


def write_to_csv(result_df: DataFrame):
    """Start a streaming query that continuously appends results as CSV files."""
    OUTPUT.sentiment_csv_dir.mkdir(parents=True, exist_ok=True)

    query = (
        result_df.writeStream.format("csv")
        .option("path", str(OUTPUT.sentiment_csv_dir))
        .option("checkpointLocation", str(OUTPUT.sentiment_csv_dir / "_checkpoint"))
        .option("header", "true")
        .outputMode("append")
        .trigger(processingTime=SPARK.trigger_processing_time)
        .start()
    )
    logger.info(
        "Streaming query started. Writing CSV output to %s (trigger every %s)",
        OUTPUT.sentiment_csv_dir,
        SPARK.trigger_processing_time,
    )
    return query


def write_to_console(result_df: DataFrame):
    """Optional: also mirror results to the console for live debugging/demo."""
    return (
        result_df.writeStream.format("console")
        .outputMode("append")
        .option("truncate", "false")
        .trigger(processingTime=SPARK.trigger_processing_time)
        .start()
    )


def main() -> None:
    spark = build_spark_session()

    try:
        raw_stream_df = read_kafka_stream(spark)
        parsed_df = parse_json_payload(raw_stream_df)
        result_df = apply_cleaning_and_sentiment(parsed_df)

        csv_query = write_to_csv(result_df)
        console_query = write_to_console(result_df)

        logger.info("Spark Structured Streaming job is running. Press Ctrl+C to stop.")
        csv_query.awaitTermination()
        console_query.awaitTermination()

    except KeyboardInterrupt:
        logger.warning("Interrupted by user. Stopping streaming queries...")
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("Fatal error in Spark streaming job: %s", exc)
    finally:
        logger.info("Stopping SparkSession.")
        spark.stop()


if __name__ == "__main__":
    main()
