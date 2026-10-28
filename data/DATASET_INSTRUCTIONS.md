# Dataset Instructions

This project uses the **Twitter Entity Sentiment Analysis** dataset from Kaggle:

https://www.kaggle.com/datasets/jp797498e/twitter-entity-sentiment-analysis

## Steps

1. Download `twitter_training.csv` from the Kaggle link above (requires a free Kaggle account).
2. Place the file in this `data/` folder so the final path is:

   ```
   SocialMediaSentiment/data/twitter_training.csv
   ```

3. The raw file has **no header row** and 4 columns in this order:

   ```
   tweet_id, entity, sentiment_label, tweet_text
   ```

   `config.py` already expects this exact layout (`DatasetConfig.raw_columns`).

4. Only the `tweet_text` column is used by the pipeline (`producer.py`), as required
   by the project specification — entity and the original label are ignored, since
   sentiment is computed live using TextBlob.

## Sample Data (already included)

A small `sample_tweets.csv` (30 rows, WITH a header row) ships with this project
so you can run the entire pipeline end-to-end immediately, without downloading
anything. To use it, either:

- Run the producer with `python producer.py --csv data/sample_tweets.csv`, or
- Rename/copy it to `twitter_training.csv` before running with default settings.
