"""
sentiment.py
============
NLP sentiment scoring module built on TextBlob.

For every (raw, cleaned) tweet pair this module computes:
    - polarity      : float in [-1.0, 1.0]   (negative -> positive)
    - subjectivity  : float in [0.0, 1.0]    (objective -> subjective)
    - sentiment     : "Positive" | "Neutral" | "Negative"
    - confidence    : float in [0.0, 1.0]    (derived confidence score)

The SentimentAnalyzer class is designed to be picklable so it can be
used inside a Spark pandas_udf / UDF without re-importing TextBlob
per row.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from textblob import TextBlob

from config import LOGGING, NLP

logging.basicConfig(level=LOGGING.log_level, format=LOGGING.log_format, datefmt=LOGGING.date_format)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SentimentResult:
    """Immutable container for one sentiment scoring result."""

    polarity: float
    subjectivity: float
    sentiment: str
    confidence: float

    def as_tuple(self) -> tuple:
        return (self.polarity, self.subjectivity, self.sentiment, self.confidence)


class SentimentAnalyzer:
    """
    Wraps TextBlob to provide consistent polarity/subjectivity scoring
    and label assignment using configurable thresholds.
    """

    def __init__(
        self,
        positive_threshold: float = NLP.positive_threshold,
        negative_threshold: float = NLP.negative_threshold,
    ) -> None:
        self.positive_threshold = positive_threshold
        self.negative_threshold = negative_threshold

    def _label_from_polarity(self, polarity: float) -> str:
        """Map a polarity score to a Positive/Neutral/Negative label."""
        if polarity >= self.positive_threshold:
            return "Positive"
        if polarity <= self.negative_threshold:
            return "Negative"
        return "Neutral"

    @staticmethod
    def _confidence_from_scores(polarity: float, subjectivity: float) -> float:
        """
        Derive a simple confidence score in [0, 1].

        Confidence increases with |polarity| (stronger sentiment signal)
        and is slightly boosted by subjectivity (opinionated text carries
        more identifiable sentiment than purely factual text).
        """
        base_confidence = abs(polarity)
        subjectivity_boost = 0.15 * subjectivity
        confidence = min(1.0, round(base_confidence + subjectivity_boost, 4))
        return confidence

    def analyze(self, text: str) -> SentimentResult:
        """Score a single piece of text and return a SentimentResult."""
        if not text or not isinstance(text, str) or not text.strip():
            return SentimentResult(0.0, 0.0, "Neutral", 0.0)

        try:
            blob = TextBlob(text)
            polarity = round(float(blob.sentiment.polarity), 4)
            subjectivity = round(float(blob.sentiment.subjectivity), 4)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("TextBlob failed to analyze text: %s | error=%s", text[:50], exc)
            return SentimentResult(0.0, 0.0, "Neutral", 0.0)

        label = self._label_from_polarity(polarity)
        confidence = self._confidence_from_scores(polarity, subjectivity)

        return SentimentResult(polarity, subjectivity, label, confidence)


# Module-level singleton for convenient reuse (and for Spark UDF closures)
default_analyzer = SentimentAnalyzer()


def analyze_text(text: str) -> tuple:
    """
    Functional convenience wrapper, useful for Spark UDF registration:

        from pyspark.sql.functions import udf
        from pyspark.sql.types import StructType, StructField, FloatType, StringType

        sentiment_udf = udf(analyze_text, sentiment_schema)
    """
    return default_analyzer.analyze(text).as_tuple()


if __name__ == "__main__":
    analyzer = SentimentAnalyzer()
    samples = [
        "I absolutely love this product, it's amazing and works perfectly!",
        "This is the worst experience I have ever had, totally disappointed.",
        "The package arrived today, it is a box.",
    ]
    for s in samples:
        result = analyzer.analyze(s)
        print(f"TEXT       : {s}")
        print(f"POLARITY   : {result.polarity}")
        print(f"SUBJECTIVE : {result.subjectivity}")
        print(f"SENTIMENT  : {result.sentiment}")
        print(f"CONFIDENCE : {result.confidence}")
        print("-" * 60)
