"""
visualize.py
============
Generates static matplotlib visualizations from the streamed sentiment
output (output/sentiment_stream/*.csv), for quick offline analysis and
for embedding into the IEEE report:

    1. Sentiment Distribution   -> bar + pie chart
    2. Word Frequency           -> top-20 horizontal bar chart
    3. Time Series              -> tweet volume & average polarity over time

Usage
-----
    python visualize.py
"""

from __future__ import annotations

import glob
import logging
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe backend (no GUI required on Windows CI)
import matplotlib.pyplot as plt
import pandas as pd

from config import LOGGING, OUTPUT

logging.basicConfig(level=LOGGING.log_level, format=LOGGING.log_format, datefmt=LOGGING.date_format)
logger = logging.getLogger("visualize")

SENTIMENT_COLORS = {"Positive": "#2ecc71", "Neutral": "#95a5a6", "Negative": "#e74c3c"}


def load_results() -> pd.DataFrame:
    """Load and concatenate all streamed CSV part-files into one DataFrame."""
    csv_files = glob.glob(str(OUTPUT.sentiment_csv_dir / "*.csv"))
    if not csv_files:
        # Fall back to the single consolidated CSV if streaming output isn't present yet
        if OUTPUT.sentiment_csv_path.exists():
            csv_files = [str(OUTPUT.sentiment_csv_path)]
        else:
            raise FileNotFoundError(
                "No sentiment output CSV files found. Run producer.py and "
                "spark_stream.py first to generate data."
            )

    frames = [pd.read_csv(f) for f in csv_files]
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    logger.info("Loaded %d sentiment records from %d file(s).", len(df), len(csv_files))
    return df


def plot_sentiment_distribution(df: pd.DataFrame, out_dir: Path) -> None:
    """Bar + pie chart of Positive / Neutral / Negative counts."""
    counts = df["sentiment"].value_counts().reindex(["Positive", "Neutral", "Negative"]).fillna(0)
    colors = [SENTIMENT_COLORS[label] for label in counts.index]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].bar(counts.index, counts.values, color=colors)
    axes[0].set_title("Sentiment Distribution (Count)")
    axes[0].set_xlabel("Sentiment")
    axes[0].set_ylabel("Number of Tweets")
    for i, v in enumerate(counts.values):
        axes[0].text(i, v, str(int(v)), ha="center", va="bottom")

    axes[1].pie(
        counts.values,
        labels=counts.index,
        autopct="%1.1f%%",
        colors=colors,
        startangle=90,
    )
    axes[1].set_title("Sentiment Distribution (%)")

    fig.tight_layout()
    out_path = out_dir / "sentiment_distribution.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Saved %s", out_path)


def plot_word_frequency(df: pd.DataFrame, out_dir: Path, top_n: int = 20) -> None:
    """Horizontal bar chart of the most frequent words in clean_tweet."""
    all_words: list[str] = []
    for text in df["clean_tweet"].dropna():
        all_words.extend(str(text).split())

    freq = Counter(all_words).most_common(top_n)
    if not freq:
        logger.warning("No words available for word-frequency chart.")
        return

    words, counts = zip(*freq[::-1])  # reverse so most frequent is on top

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(words, counts, color="#3498db")
    ax.set_title(f"Top {top_n} Word Frequency")
    ax.set_xlabel("Frequency")
    fig.tight_layout()

    out_path = out_dir / "word_frequency.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Saved %s", out_path)


def plot_time_series(df: pd.DataFrame, out_dir: Path) -> None:
    """Line chart of tweet volume and average polarity over time (per minute)."""
    ts = df.set_index("timestamp").sort_index()
    volume = ts["sentiment"].resample("1min").count()
    avg_polarity = ts["polarity"].resample("1min").mean()

    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.plot(volume.index, volume.values, color="#3498db", label="Tweet Volume")
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Tweet Volume", color="#3498db")
    ax1.tick_params(axis="y", labelcolor="#3498db")

    ax2 = ax1.twinx()
    ax2.plot(avg_polarity.index, avg_polarity.values, color="#e67e22", label="Avg Polarity")
    ax2.set_ylabel("Average Polarity", color="#e67e22")
    ax2.tick_params(axis="y", labelcolor="#e67e22")
    ax2.axhline(0, color="grey", linewidth=0.8, linestyle="--")

    fig.suptitle("Tweet Volume & Average Polarity Over Time")
    fig.autofmt_xdate()
    fig.tight_layout()

    out_path = out_dir / "time_series.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Saved %s", out_path)


def main() -> None:
    OUTPUT.visualization_dir.mkdir(parents=True, exist_ok=True)
    df = load_results()

    plot_sentiment_distribution(df, OUTPUT.visualization_dir)
    plot_word_frequency(df, OUTPUT.visualization_dir)
    plot_time_series(df, OUTPUT.visualization_dir)

    logger.info("All visualizations saved to %s", OUTPUT.visualization_dir)


if __name__ == "__main__":
    main()
