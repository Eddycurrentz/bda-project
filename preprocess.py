"""
preprocess.py
=============
Text preprocessing utilities for raw tweet text.

Pipeline applied to every tweet:
    1. Remove URLs
    2. Remove @mentions
    3. Remove #hashtags (symbol only, keeps the word)
    4. Remove emojis / non-ASCII symbols
    5. Remove punctuation and special characters
    6. Collapse extra whitespace
    7. Lowercase
    8. Tokenize
    9. Remove stopwords

This module is used both by the Spark structured-streaming job
(as a pandas_udf / UDF) and standalone for quick testing.
"""

from __future__ import annotations

import logging
import re
import string
from functools import lru_cache
from typing import List

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from config import LOGGING, NLP

logging.basicConfig(level=LOGGING.log_level, format=LOGGING.log_format, datefmt=LOGGING.date_format)
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# NLTK bootstrap
# --------------------------------------------------------------------------- #
def ensure_nltk_resources() -> None:
    """Download required NLTK corpora if not already present (idempotent)."""
    required = [
        ("tokenizers/punkt", "punkt"),
        ("tokenizers/punkt_tab", "punkt_tab"),
        ("corpora/stopwords", "stopwords"),
    ]
    for path, package in required:
        try:
            nltk.data.find(path)
        except LookupError:
            logger.info("Downloading missing NLTK resource: %s", package)
            try:
                nltk.download(package, quiet=True)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning("Could not download NLTK resource '%s': %s", package, exc)


ensure_nltk_resources()


@lru_cache(maxsize=1)
def get_stopword_set() -> set:
    """Cached set of English stopwords."""
    try:
        return set(stopwords.words(NLP.language))
    except LookupError:
        ensure_nltk_resources()
        return set(stopwords.words(NLP.language))


# --------------------------------------------------------------------------- #
# Regex patterns (compiled once for performance)
# --------------------------------------------------------------------------- #
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
MENTION_PATTERN = re.compile(r"@\w+")
HASHTAG_SYMBOL_PATTERN = re.compile(r"#")
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002700-\U000027BF"  # dingbats
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U00002600-\U000026FF"  # misc symbols
    "]+",
    flags=re.UNICODE,
)
NON_ASCII_PATTERN = re.compile(r"[^\x00-\x7F]+")
EXTRA_SPACE_PATTERN = re.compile(r"\s+")
PUNCTUATION_TABLE = str.maketrans("", "", string.punctuation)


def remove_urls(text: str) -> str:
    """Strip http(s):// and www. links from text."""
    return URL_PATTERN.sub(" ", text)


def remove_mentions(text: str) -> str:
    """Strip @username mentions."""
    return MENTION_PATTERN.sub(" ", text)


def remove_hashtag_symbols(text: str) -> str:
    """Strip the '#' symbol but keep the hashtag word itself."""
    return HASHTAG_SYMBOL_PATTERN.sub("", text)


def remove_emojis(text: str) -> str:
    """Strip emoji characters and other non-ASCII symbols."""
    text = EMOJI_PATTERN.sub(" ", text)
    text = NON_ASCII_PATTERN.sub(" ", text)
    return text


def remove_punctuation(text: str) -> str:
    """Strip standard punctuation characters."""
    return text.translate(PUNCTUATION_TABLE)


def collapse_whitespace(text: str) -> str:
    """Collapse multiple spaces/tabs/newlines into a single space and trim."""
    return EXTRA_SPACE_PATTERN.sub(" ", text).strip()


def tokenize(text: str) -> List[str]:
    """Tokenize text into a list of lowercase word tokens."""
    try:
        return word_tokenize(text)
    except LookupError:
        ensure_nltk_resources()
        return word_tokenize(text)


def remove_stopwords(tokens: List[str]) -> List[str]:
    """Filter out English stopwords from a token list."""
    stop_set = get_stopword_set()
    return [tok for tok in tokens if tok not in stop_set and len(tok) > 1]


def clean_tweet(raw_text: str) -> str:
    """
    Full cleaning pipeline applied to one raw tweet.

    Returns a cleaned, lowercase, stopword-free string ready for
    sentiment analysis and word-frequency visualization.
    """
    if not raw_text or not isinstance(raw_text, str):
        return ""

    text = raw_text.lower()
    text = remove_urls(text)
    text = remove_mentions(text)
    text = remove_hashtag_symbols(text)
    text = remove_emojis(text)
    text = remove_punctuation(text)
    text = collapse_whitespace(text)

    tokens = tokenize(text)
    tokens = remove_stopwords(tokens)

    return " ".join(tokens)


if __name__ == "__main__":
    samples = [
        "OMG!! I just LOVE the new #iPhone 😍😍 check it out https://apple.com @Apple",
        "This service is TERRIBLE... never buying again!! #fail @support",
        "Meh, it's okay I guess. Nothing special. #neutral",
    ]
    for s in samples:
        print(f"RAW   : {s}")
        print(f"CLEAN : {clean_tweet(s)}")
        print("-" * 60)
