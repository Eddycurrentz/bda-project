# Power BI Final Results Presentation
## Real-Time Social Media Sentiment Analysis Dashboard

**B.Tech AI & Data Science — Big Data Analytics Project**

---

## Overview

This guide walks you through building the **complete, presentation-ready Power BI dashboard** from your project's final output. All steps use the enriched CSV that now includes `brand` and `polarity_bucket` columns for richer visuals.

---

## Files You Need

| File | Location |
|---|---|
| **Enriched results** | `output/sentiment_results_enriched.csv` |
| **DAX Measures** | `dashboard/DAX_MEASURES.txt` |
| Sentiment distribution chart | `output/visualizations/sentiment_distribution.png` |
| Time series chart | `output/visualizations/time_series.png` |
| Word frequency chart | `output/visualizations/word_frequency.png` |

---

## Step 1 — Load the Data

1. Open **Power BI Desktop**
2. **Home → Get Data → Text/CSV**
3. Browse to: `output/sentiment_results_enriched.csv` → **Open**
4. In the preview dialog, click **Transform Data** (opens Power Query Editor)

### Step 1a — Set Column Types in Power Query

| Column | Type to Set |
|---|---|
| `timestamp` | **Date/Time** |
| `polarity` | **Decimal Number** |
| `subjectivity` | **Decimal Number** |
| `confidence` | **Decimal Number** |
| `sentiment` | **Text** |
| `brand` | **Text** |
| `polarity_bucket` | **Text** |
| `tweet`, `clean_tweet` | **Text** |

5. Click **Close & Apply**

---

## Step 2 — Add All DAX Measures

Open `dashboard/DAX_MEASURES.txt`. For **each measure block**:

1. **Modeling tab → New Measure**
2. Paste the DAX formula
3. Press **Enter**

Measures to create (in order):

| # | Measure Name | Used In |
|---|---|---|
| 1 | `Total Tweets` | KPI Card |
| 2 | `Positive Tweets` | KPI Card |
| 3 | `Negative Tweets` | KPI Card |
| 4 | `Neutral Tweets` | KPI Card |
| 5 | `Average Polarity` | KPI Card, Line Chart |
| 6 | `Average Subjectivity` | KPI Card |
| 7 | `Average Confidence` | KPI Card |
| 8 | `Positive %` | Donut Chart |
| 9 | `Negative %` | Donut Chart |
| 10 | `Neutral %` | Donut Chart |
| 11 | `Sentiment Score` | Gauge Visual |
| 12 | `Brand Positive %` | Brand Bar Chart |
| 13 | `Brand Net Sentiment` | Brand Heatmap |
| 14 | `Sentiment Color` | Conditional formatting |

---

## Step 3 — Build the Dashboard (Page by Page)

Set canvas size: **File → Page Setup → Page Size = Widescreen (16:9)**

---

### Page 1 — Executive Summary

Layout:
```
[Total] [Positive] [Negative] [Neutral] [Avg Polarity] [Avg Subj]
[   Donut Chart   ] [  Bar Chart  ] [  Gauge  ]
[         Line Chart — Polarity Over Time              ]
[  Slicer: Sentiment ] [ Slicer: Brand ] [ Slicer: Date ]
```

#### KPI Cards (top row — 6 cards)
- **Insert → Card** visual x6
- Assign measures: `Total Tweets`, `Positive Tweets`, `Negative Tweets`, `Neutral Tweets`, `Average Polarity`, `Average Subjectivity`
- Positive card callout color: `#27AE60` (green)
- Negative card callout color: `#E74C3C` (red)
- Neutral card callout color: `#95A5A6` (grey)

#### Donut Chart — Sentiment Share
- Visual: **Donut Chart**
- Legend: `sentiment` field
- Values: `Total Tweets` measure
- Colors: Positive=`#27AE60`, Negative=`#E74C3C`, Neutral=`#95A5A6`
- Enable Detail labels with percentage + count

#### Clustered Column Chart — Sentiment Count
- Visual: **Clustered Column Chart**
- X-axis: `sentiment`
- Y-axis: `Total Tweets` measure
- Data colors → match green/grey/red per bar
- Enable Data labels

#### Gauge Visual — Sentiment Health Score
- Visual: **Gauge**
- Value: `Sentiment Score` measure (0-100)
- Min: `0`, Max: `100`, Target: `50`
- Title: "Overall Sentiment Health"

#### Line Chart — Polarity Over Time
- Visual: **Line Chart**
- X-axis: `timestamp` → Continuous
- Y-axis: `Average Polarity` measure
- Add Constant Line at Y=0 (red dashed)
- Title: "Polarity Trend Over Time"

#### Slicers (bottom bar)
1. Sentiment slicer — field: `sentiment`, style: Dropdown
2. Brand slicer — field: `brand`, style: Dropdown
3. Date slicer — field: `timestamp`, style: Between

---

### Page 2 — Brand Analysis

Layout:
```
[ Horizontal Bar: Tweets per Brand ]  [ Stacked Bar: Sentiment Mix per Brand ]
[ Bar: Avg Polarity by Brand       ]  [ Bar: Net Sentiment by Brand          ]
```

#### Bar Chart — Tweets per Brand
- Visual: **Bar Chart (horizontal)**
- Y-axis: `brand`, X-axis: `Total Tweets`
- Sort descending by Total Tweets
- Title: "Tweet Volume by Brand"

#### Stacked Bar — Sentiment Mix per Brand
- Visual: **Stacked Bar Chart**
- Y-axis: `brand`, X-axis: `Total Tweets`, Legend: `sentiment`
- Colors: Positive=green, Neutral=grey, Negative=red
- Title: "Sentiment Breakdown by Brand"

#### Bar Chart — Average Polarity by Brand
- Visual: **Clustered Bar Chart**
- Y-axis: `brand`, X-axis: `Average Polarity`
- Conditional formatting: value < 0 → Red, value >= 0 → Green
- Add reference line at 0
- Title: "Average Polarity Score by Brand"

#### Bar Chart — Net Sentiment by Brand
- Visual: **Clustered Bar Chart**
- Y-axis: `brand`, X-axis: `Brand Net Sentiment`
- Conditional formatting: negative=red, positive=green
- Title: "Net Sentiment (Positive% - Negative%) by Brand"

---

### Page 3 — Tweet Detail / Live Feed

Layout:
```
[ Table — Full Tweet Feed with sentiment row coloring (full width) ]
[ Scatter: Polarity vs Subjectivity ]  [ Word Frequency Image      ]
```

#### Table — Live Tweet Feed
- Visual: **Table**
- Columns: `timestamp`, `brand`, `tweet`, `sentiment`, `polarity`, `confidence`
- Sort descending by `timestamp`
- Conditional formatting on `sentiment` column:
  - Background color → Field value → `Sentiment Color` measure
  - Font color → white (static)
- Conditional formatting on `polarity` column:
  - If value < 0 → background `#FADBD8` (light red)
  - If value >= 0 → background `#D5F5E3` (light green)
- Title: "Real-Time Tweet Sentiment Feed"

#### Scatter Plot — Polarity vs. Subjectivity
- Visual: **Scatter Chart**
- X-axis: `polarity`, Y-axis: `subjectivity`
- Size: `confidence`, Legend: `sentiment`
- Colors: Positive=green, Neutral=grey, Negative=red
- Title: "Polarity vs. Subjectivity (sized by Confidence)"

#### Word Frequency Image
- **Insert → Image** → `output/visualizations/word_frequency.png`
- Title: "Top Keywords in Tweets"

---

### Page 4 — Polarity Deep Dive

#### Column Chart — Polarity Distribution
- Visual: **Clustered Column Chart**
- X-axis: `polarity_bucket`
  - Sort order: Strongly Negative → Mildly Negative → Neutral → Mildly Positive → Strongly Positive
- Y-axis: `Total Tweets`
- Data colors: spectrum from red (negative) to grey to green (positive)
- Title: "Polarity Distribution by Bucket"

#### Area Chart — Subjectivity Over Time
- Visual: **Area Chart**
- X-axis: `timestamp`, Y-axis: `Average Subjectivity`
- Title: "Subjectivity Trend Over Time"

#### KPI Cards (page-level)
- `Average Confidence` — label: "Pipeline Confidence"
- `Sentiment Score` — label: "Overall Health Score"

---

## Step 4 — Apply Report Theming

**View → Themes → Executive** (built-in, clean and professional)

Or for a dark theme, save this JSON as `sentiment_theme.json` and load it via **View → Themes → Browse for themes**:

```json
{
  "name": "SentimentTheme",
  "dataColors": ["#27AE60", "#E74C3C", "#95A5A6", "#3498DB", "#F39C12", "#9B59B6"],
  "background": "#FFFFFF",
  "foreground": "#2C3E50",
  "tableAccent": "#3498DB"
}
```

---

## Step 5 — Report Polish

### Report Header (Text Box on each page)
- **Insert → Text Box**
- Line 1: `Real-Time Social Media Sentiment Analysis` — Bold, 18pt
- Line 2: `Apache Kafka · PySpark Streaming · TextBlob · Power BI` — Regular, 11pt

### Page Navigation Buttons
- **Insert → Buttons → Navigator → Page Navigator**
- Place at top or bottom of each page

---

## Step 6 — Enable Auto-Refresh (for Live Demo)

**File → Options & Settings → Options → Data Load**
Enable: **"Refresh data automatically every N minutes"** → set to **1 minute**

This works in Power BI Desktop while Spark writes new CSV chunks.

---

## Step 7 — Export for Submission

| Export Format | Steps |
|---|---|
| **PDF** | File → Export → Export to PDF |
| **PowerPoint** | File → Export → Export to PowerPoint |
| **Publish online** | Home → Publish → Select Workspace |

---

## Final Dashboard Checklist

- [ ] `sentiment_results_enriched.csv` loaded and column types set
- [ ] All 14 DAX measures added
- [ ] Page 1: Executive Summary (cards, donut, bar, gauge, line, slicers)
- [ ] Page 2: Brand Analysis (4 charts)
- [ ] Page 3: Tweet Feed (table with conditional formatting, scatter, word image)
- [ ] Page 4: Polarity Deep Dive (histogram, area chart, cards)
- [ ] Sentiment colors consistent (Green / Grey / Red) across all pages
- [ ] Report header text boxes added
- [ ] Page navigation buttons added
- [ ] Auto-refresh configured (if doing live demo)
- [ ] Exported to PDF or PowerPoint for project submission

---

## Results Summary (from your data)

| Metric | Value |
|---|---|
| Total Tweets | 30 |
| Positive | 13 (43.3%) |
| Negative | 10 (33.3%) |
| Neutral | 7 (23.3%) |
| Average Polarity | ~0.10 (slightly positive) |
| Average Subjectivity | ~0.49 (moderately subjective) |
| Brands Detected | Amazon, Apple, Borderlands, Call of Duty, Facebook, Google, Microsoft, Netflix, PlayStation, Spotify, Tesla, Verizon, Xbox |

---

*Real-Time Social Media Sentiment Analysis — BDA Project | B.Tech AI & Data Science*
