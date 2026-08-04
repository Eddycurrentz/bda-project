# Screenshots

Place execution screenshots here with these exact filenames so they line up
with the references in `README.md` and `report/`:

| Filename | What to capture |
|---|---|
| `01_kafka_topic_created.png` | Terminal output of `kafka-topics.bat --create ...` and `--list` confirming `twitter-stream` exists |
| `02_producer_running.png` | `producer.py` terminal log showing tweets being sent with partition/offset |
| `03_spark_streaming_console.png` | `spark_stream.py` console output showing a parsed + scored micro-batch |
| `04_output_csv.png` | `output/sentiment_stream/*.csv` opened in Excel/VS Code showing populated rows |
| `05_powerbi_dashboard.png` | The completed Power BI dashboard with KPI cards, charts, and slicers |
| `06_word_frequency_chart.png` | `output/visualizations/word_frequency.png` |
| `07_sentiment_distribution_chart.png` | `output/visualizations/sentiment_distribution.png` |
| `08_time_series_chart.png` | `output/visualizations/time_series.png` |

These are referenced as figures in `report/Project_Report.docx` and slide 13
("Results") of `presentation/Project_Presentation.pptx`. Replace this file's
listed placeholders with actual PNG/JPG captures before final submission.
