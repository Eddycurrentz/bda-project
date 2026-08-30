#!/usr/bin/env python3
"""
generate_pbit.py
================
Generates SentimentDashboard.pbit — a ready-to-open Power BI Template for
the Real-Time Social Media Sentiment Analysis project.

Usage:
    python dashboard/generate_pbit.py
Output:
    dashboard/SentimentDashboard.pbit
Then: Open that .pbit in Power BI Desktop — 4 pages, all measures, all visuals.
"""

import json, zipfile, uuid, os

# ─────────────────────────────────────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
TABLE    = "sentiment_results_enriched"
CSV_PATH = r"C:\Users\edwin\OneDrive\Desktop\BDA\bda-project\output\sentiment_results_enriched.csv"
OUT_PATH = r"C:\Users\edwin\OneDrive\Desktop\BDA\bda-project\dashboard\SentimentDashboard.pbit"

CW, CH = 1280, 720   # canvas size (16:9 widescreen)

# Brand palette
C_POS = "#27AE60"; C_NEG = "#E74C3C"; C_NEU = "#95A5A6"
C_ACC = "#2980B9"; C_BG  = "#F0F4F8"; C_TXT = "#2C3E50"
C_HDR = "#1A252F"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
_z = 1000

def gz():
    global _z; _z += 100; return _z

def gn():
    return "v" + uuid.uuid4().hex[:12]

FROM_CLAUSE = [{"Name": "s", "Entity": TABLE, "Type": 0}]

def msel(name):
    """Measure select clause."""
    return {"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": name}, "Name": name}

def csel(field, alias=None):
    """Column select clause."""
    a = alias or f"s.{field}"
    return {"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": field}, "Name": a}

def vcont(x, y, w, h, inner):
    """Wrap a visual dict into a positioned container."""
    z = gz()
    inner["name"] = gn()
    inner["layouts"] = [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}]
    return {"x": x, "y": y, "z": z, "width": w, "height": h,
            "config": json.dumps(inner, ensure_ascii=False), "filters": "[]"}

def title_prop(text):
    return {"title": [{"properties": {
        "show": {"expr": {"Literal": {"Value": "true"}}},
        "text": {"expr": {"Literal": {"Value": f"'{text}'"}}},
        "fontSize": {"expr": {"Literal": {"Value": "11D"}}},
        "fontFamily": {"expr": {"Literal": {"Value": "'Segoe UI, wf_segoe-ui_normal, helvetica, arial, sans-serif'"}}}
    }}]}

# ─────────────────────────────────────────────────────────────────────────────
# VISUAL BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def v_card(x, y, w, h, measure, label, val_color=None):
    vcobj = title_prop(label)
    if val_color:
        vcobj["labels"] = [{"properties": {
            "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{val_color}'"}}}}},
            "fontSize": {"expr": {"Literal": {"Value": "28D"}}}
        }}]
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "Card",
        "projections": {"Values": [{"queryRef": measure, "active": True}]},
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE, "Select": [msel(measure)]},
        "vcObjects": vcobj,
        "drillFilterOtherVisuals": True
    }})

def v_donut(x, y, w, h, field, measure, title):
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "donutChart",
        "projections": {
            "Category": [{"queryRef": f"s.{field}", "active": True}],
            "Y": [{"queryRef": measure, "active": True}]
        },
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE,
                           "Select": [csel(field), msel(measure)]},
        "vcObjects": title_prop(title),
        "drillFilterOtherVisuals": True
    }})

def v_col_chart(x, y, w, h, field, measure, title):
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "clusteredColumnChart",
        "projections": {
            "Category": [{"queryRef": f"s.{field}", "active": True}],
            "Y": [{"queryRef": measure, "active": True}]
        },
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE,
                           "Select": [csel(field), msel(measure)]},
        "vcObjects": title_prop(title),
        "drillFilterOtherVisuals": True
    }})

def v_bar_chart(x, y, w, h, field, measure, title):
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "clusteredBarChart",
        "projections": {
            "Category": [{"queryRef": f"s.{field}", "active": True}],
            "Y": [{"queryRef": measure, "active": True}]
        },
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE,
                           "Select": [csel(field), msel(measure)]},
        "vcObjects": title_prop(title),
        "drillFilterOtherVisuals": True
    }})

def v_stacked_bar(x, y, w, h, cat_field, measure, series_field, title):
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "stackedBarChart",
        "projections": {
            "Category": [{"queryRef": f"s.{cat_field}", "active": True}],
            "Y":        [{"queryRef": measure,              "active": True}],
            "Series":   [{"queryRef": f"s.{series_field}", "active": True}]
        },
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE,
                           "Select": [csel(cat_field), msel(measure), csel(series_field)]},
        "vcObjects": title_prop(title),
        "drillFilterOtherVisuals": True
    }})

def v_line(x, y, w, h, time_field, measure, title):
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "lineChart",
        "projections": {
            "Category": [{"queryRef": f"s.{time_field}", "active": True}],
            "Y":        [{"queryRef": measure,            "active": True}]
        },
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE,
                           "Select": [csel(time_field), msel(measure)]},
        "vcObjects": title_prop(title),
        "drillFilterOtherVisuals": True
    }})

def v_area(x, y, w, h, time_field, measure, title):
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "areaChart",
        "projections": {
            "Category": [{"queryRef": f"s.{time_field}", "active": True}],
            "Y":        [{"queryRef": measure,            "active": True}]
        },
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE,
                           "Select": [csel(time_field), msel(measure)]},
        "vcObjects": title_prop(title),
        "drillFilterOtherVisuals": True
    }})

def v_gauge(x, y, w, h, measure, title):
    vcobj = title_prop(title)
    vcobj["gauge"] = [{"properties": {
        "minValue": {"expr": {"Literal": {"Value": "0D"}}},
        "maxValue": {"expr": {"Literal": {"Value": "100D"}}}
    }}]
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "gauge",
        "projections": {"Y": [{"queryRef": measure, "active": True}]},
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE, "Select": [msel(measure)]},
        "vcObjects": vcobj,
        "drillFilterOtherVisuals": True
    }})

def v_slicer(x, y, w, h, field, label, style="Dropdown"):
    vcobj = title_prop(label)
    vcobj["data"] = [{"properties": {"mode": {"expr": {"Literal": {"Value": f"'{style}'"}}}}}]
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "slicer",
        "projections": {"Values": [{"queryRef": f"s.{field}", "active": True}]},
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE, "Select": [csel(field)]},
        "vcObjects": vcobj
    }})

def v_scatter(x, y, w, h, xf, yf, szf, legf, title):
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "scatterChart",
        "projections": {
            "X":        [{"queryRef": f"s.{xf}",   "active": True}],
            "Y":        [{"queryRef": f"s.{yf}",   "active": True}],
            "Size":     [{"queryRef": f"s.{szf}",  "active": True}],
            "Category": [{"queryRef": f"s.{legf}", "active": True}]
        },
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE,
                           "Select": [csel(xf), csel(yf), csel(szf), csel(legf)]},
        "vcObjects": title_prop(title),
        "drillFilterOtherVisuals": True
    }})

def v_table(x, y, w, h, cols, title):
    """cols: list of (field_or_measure, is_measure)"""
    proj, sel = [], []
    for f, is_m in cols:
        ref = f if is_m else f"s.{f}"
        proj.append({"queryRef": ref, "active": True})
        sel.append(msel(f) if is_m else csel(f))
    return vcont(x, y, w, h, {"singleVisual": {
        "visualType": "tableEx",
        "projections": {"Values": proj},
        "prototypeQuery": {"Version": 2, "From": FROM_CLAUSE, "Select": sel},
        "vcObjects": title_prop(title),
        "drillFilterOtherVisuals": True
    }})

def v_textbox(x, y, w, h, text, size=14, bold=True, color="#FFFFFF", bg=C_HDR, align="Center"):
    z = gz()
    n = gn()
    return {
        "x": x, "y": y, "z": z, "width": w, "height": h,
        "config": json.dumps({
            "name": n,
            "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}],
            "singleVisual": {
                "visualType": "textbox",
                "vcObjects": {"general": [{"properties": {
                    "paragraphs": [{
                        "horizontalTextAlignment": align,
                        "textRuns": [{"value": text, "textRunStyle": {
                            "fontWeight": "Bold" if bold else "normal",
                            "fontSize": str(size),
                            "color": color,
                            "fontFamily": "Segoe UI, wf_segoe-ui_normal, helvetica, arial, sans-serif"
                        }}]
                    }],
                    "background": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{bg}'"}}}}}
                }}]}
            }
        }, ensure_ascii=False),
        "filters": "[]"
    }

# ─────────────────────────────────────────────────────────────────────────────
# PAGE 1 — EXECUTIVE SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
def page1():
    vcs = []
    # Header bar
    vcs.append(v_textbox(0, 0, CW, 45,
        "Real-Time Social Media Sentiment Analysis  |  Kafka · PySpark · TextBlob · Power BI",
        size=14, bold=True))

    # ── KPI Cards row (y=50, h=90) ──────────────────────────────────────────
    CW6 = 210; CH_CARD = 90; cy = 50
    card_defs = [
        ("Total Tweets",        "Total Tweets",        None),
        ("Positive Tweets",     "Positive Tweets",     C_POS),
        ("Negative Tweets",     "Negative Tweets",     C_NEG),
        ("Neutral Tweets",      "Neutral Tweets",      C_NEU),
        ("Average Polarity",    "Avg Polarity",        C_ACC),
        ("Average Subjectivity","Avg Subjectivity",    C_ACC),
    ]
    for i, (m, lbl, col) in enumerate(card_defs):
        vcs.append(v_card(i * (CW6 + 2), cy, CW6, CH_CARD, m, lbl, col))

    # ── Row 2 — Charts (y=145, h=265) ───────────────────────────────────────
    ry, rh = 145, 265
    vcs.append(v_donut    (  0, ry, 330, rh, "sentiment",  "Total Tweets",     "Sentiment Distribution (%)"))
    vcs.append(v_col_chart(335, ry, 320, rh, "sentiment",  "Total Tweets",     "Tweet Count by Sentiment"))
    vcs.append(v_gauge    (660, ry, 225, rh, "Sentiment Score",                "Sentiment Health Score"))
    vcs.append(v_line     (890, ry, 390, rh, "timestamp",  "Average Polarity", "Polarity Trend Over Time"))

    # ── Row 3 — Slicers (y=415, h=60) ───────────────────────────────────────
    sy = 415; sh = 60
    vcs.append(v_slicer(  0, sy, 418, sh, "sentiment", "Filter: Sentiment"))
    vcs.append(v_slicer(422, sy, 418, sh, "brand",     "Filter: Brand"))
    vcs.append(v_slicer(844, sy, 436, sh, "timestamp", "Filter: Date Range", style="Between"))

    # ── Row 4 — Live Tweet Table (y=480, h=235) ─────────────────────────────
    vcs.append(v_table(0, 480, CW, 235,
        [("timestamp",False),("brand",False),("tweet",False),
         ("sentiment",False),("polarity",False),("confidence",False)],
        "Live Tweet Sentiment Feed  (latest first)"))

    return vcs

# ─────────────────────────────────────────────────────────────────────────────
# PAGE 2 — BRAND ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
def page2():
    vcs = []
    vcs.append(v_textbox(0, 0, CW, 45, "Brand Analysis — Sentiment by Entity",
        size=14, bold=True))

    HW, HH = 630, 325  # half-width, half-height

    vcs.append(v_bar_chart  (  0,  50, HW, HH, "brand", "Total Tweets",      "Tweet Volume by Brand"))
    vcs.append(v_stacked_bar(645,  50, HW, HH, "brand", "Total Tweets", "sentiment", "Sentiment Mix by Brand (stacked)"))
    vcs.append(v_bar_chart  (  0, 380, HW, HH, "brand", "Average Polarity",  "Average Polarity by Brand"))
    vcs.append(v_bar_chart  (645, 380, HW, HH, "brand", "Brand Net Sentiment","Net Sentiment Score by Brand"))

    return vcs

# ─────────────────────────────────────────────────────────────────────────────
# PAGE 3 — TWEET FEED
# ─────────────────────────────────────────────────────────────────────────────
def page3():
    vcs = []
    vcs.append(v_textbox(0, 0, CW, 45, "Tweet Detail — Live Feed & Polarity Analysis",
        size=14, bold=True))

    # Full-width tweet table
    vcs.append(v_table(0, 50, CW, 330,
        [("timestamp",False),("brand",False),("tweet",False),
         ("sentiment",False),("polarity",False),("subjectivity",False),("confidence",False)],
        "Full Tweet Sentiment Feed"))

    # Bottom row
    vcs.append(v_scatter(  0, 385, 630, 330,
        "polarity","subjectivity","confidence","sentiment",
        "Polarity vs. Subjectivity (size = Confidence)"))
    vcs.append(v_col_chart(645, 385, 635, 330,
        "polarity_bucket", "Total Tweets",
        "Tweet Count by Polarity Bucket"))

    return vcs

# ─────────────────────────────────────────────────────────────────────────────
# PAGE 4 — POLARITY DEEP DIVE
# ─────────────────────────────────────────────────────────────────────────────
def page4():
    vcs = []
    vcs.append(v_textbox(0, 0, CW, 45, "Polarity Deep Dive — Distribution & Trends",
        size=14, bold=True))

    # 4 KPI cards
    for i, (m, lbl, col) in enumerate([
        ("Sentiment Score",    "Sentiment Health",   C_ACC),
        ("Average Confidence", "Avg Confidence",     C_ACC),
        ("Positive %",         "Positive Rate",      C_POS),
        ("Negative %",         "Negative Rate",      C_NEG),
    ]):
        vcs.append(v_card(i * 320, 50, 317, 88, m, lbl, col))

    # Polarity histogram
    vcs.append(v_col_chart(  0, 145, 630, 280,
        "polarity_bucket", "Total Tweets", "Polarity Bucket Distribution"))

    # Subjectivity area trend
    vcs.append(v_area      (645, 145, 635, 280,
        "timestamp", "Average Subjectivity", "Subjectivity Trend Over Time"))

    # Summary table
    vcs.append(v_table(0, 430, 630, 285,
        [("sentiment",False),("Total Tweets",True),
         ("Average Polarity",True),("Positive %",True),("Negative %",True)],
        "Sentiment Summary Statistics"))

    # Brand positive rate
    vcs.append(v_bar_chart(645, 430, 635, 285,
        "brand", "Brand Positive %", "Brand Positive Rate"))

    return vcs

# ─────────────────────────────────────────────────────────────────────────────
# REPORT LAYOUT JSON
# ─────────────────────────────────────────────────────────────────────────────
def build_layout():
    page_defs = [
        ("ReportSectionPage1", "Executive Summary",  page1()),
        ("ReportSectionPage2", "Brand Analysis",     page2()),
        ("ReportSectionPage3", "Tweet Feed",         page3()),
        ("ReportSectionPage4", "Polarity Deep Dive", page4()),
    ]
    sections = [{
        "id": i, "name": name, "displayName": display,
        "filters": "[]", "ordinal": i,
        "width": CW, "height": CH,
        "config": json.dumps({"relationships": [], "objects": {
            "reportPage": [{"properties": {
                "background": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{C_BG}'"}}}}}
            }}]
        }}),
        "visualContainers": vcs
    } for i, (name, display, vcs) in enumerate(page_defs)]

    layout = {
        "id": 0,
        "resourcePackages": [],
        "sections": sections,
        "config": json.dumps({
            "version": "5.47",
            "activeSectionIndex": 0,
            "themeCollection": {
                "baseTheme": {"name": "CY24SU10", "version": "5.47", "type": 2}
            },
            "objects": {}
        })
    }
    return json.dumps(layout, ensure_ascii=False)

# ─────────────────────────────────────────────────────────────────────────────
# DATA MODEL SCHEMA  (measures + M query + columns)
# ─────────────────────────────────────────────────────────────────────────────
def build_data_model():
    # Power Query M expression
    m_query = "\n".join([
        "let",
        f'    Source = Csv.Document(File.Contents("{CSV_PATH}"),[Delimiter=",", Columns=9, Encoding=1252, QuoteStyle=QuoteStyle.None]),',
        '    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        '    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{',
        '        {"timestamp", type datetime},',
        '        {"tweet", type text},',
        '        {"clean_tweet", type text},',
        '        {"polarity", type number},',
        '        {"subjectivity", type number},',
        '        {"sentiment", type text},',
        '        {"confidence", type number},',
        '        {"brand", type text},',
        '        {"polarity_bucket", type text}',
        '    })',
        "in",
        '    #"Changed Type"',
    ])

    T = TABLE  # shorthand
    measures = [
        ("Total Tweets",         f"COUNTROWS('{T}')",                              "#,0"),
        ("Positive Tweets",      f"CALCULATE(COUNTROWS('{T}'),'{T}'[sentiment]=\"Positive\")", "#,0"),
        ("Negative Tweets",      f"CALCULATE(COUNTROWS('{T}'),'{T}'[sentiment]=\"Negative\")", "#,0"),
        ("Neutral Tweets",       f"CALCULATE(COUNTROWS('{T}'),'{T}'[sentiment]=\"Neutral\")",  "#,0"),
        ("Average Polarity",     f"AVERAGE('{T}'[polarity])",                      "#,##0.00"),
        ("Average Subjectivity", f"AVERAGE('{T}'[subjectivity])",                  "#,##0.00"),
        ("Average Confidence",   f"AVERAGE('{T}'[confidence])",                    "#,##0.00"),
        ("Positive %",           "DIVIDE([Positive Tweets],[Total Tweets],0)",     "0.0%"),
        ("Negative %",           "DIVIDE([Negative Tweets],[Total Tweets],0)",     "0.0%"),
        ("Neutral %",            "DIVIDE([Neutral Tweets],[Total Tweets],0)",      "0.0%"),
        ("Sentiment Score",      f"ROUND((AVERAGE('{T}'[polarity])+1)/2*100,1)",   "#,##0.0"),
        ("Brand Positive %",     f"DIVIDE(CALCULATE(COUNTROWS('{T}'),'{T}'[sentiment]=\"Positive\"),COUNTROWS('{T}'),0)", "0.0%"),
        ("Brand Net Sentiment",  f"DIVIDE(CALCULATE(COUNTROWS('{T}'),'{T}'[sentiment]=\"Positive\")"
                                 f"-CALCULATE(COUNTROWS('{T}'),'{T}'[sentiment]=\"Negative\"),COUNTROWS('{T}'),0)", "0.0%"),
    ]

    columns = [
        {"name": "timestamp",       "dataType": "dateTime", "formatString": "General Date", "summarizeBy": "none"},
        {"name": "tweet",           "dataType": "string",                                   "summarizeBy": "none"},
        {"name": "clean_tweet",     "dataType": "string",                                   "summarizeBy": "none"},
        {"name": "polarity",        "dataType": "double",   "formatString": "#,##0.00",     "summarizeBy": "average"},
        {"name": "subjectivity",    "dataType": "double",   "formatString": "#,##0.00",     "summarizeBy": "average"},
        {"name": "sentiment",       "dataType": "string",                                   "summarizeBy": "none"},
        {"name": "confidence",      "dataType": "double",   "formatString": "#,##0.00",     "summarizeBy": "average"},
        {"name": "brand",           "dataType": "string",                                   "summarizeBy": "none"},
        {"name": "polarity_bucket", "dataType": "string",                                   "summarizeBy": "none"},
    ]

    schema = {
        "name": "Model",
        "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "tables": [{
            "name": T,
            "columns": [{
                "name": c["name"],
                "dataType": c["dataType"],
                "sourceColumn": c["name"],
                "formatString": c.get("formatString", ""),
                "summarizeBy": c["summarizeBy"],
                "annotations": [{"name": "SummarizationSetBy", "value": "Automatic"}]
            } for c in columns],
            "measures": [{
                "name": name,
                "expression": expr,
                "formatString": fmt
            } for name, expr, fmt in measures],
            "partitions": [{
                "name": f"Partition-{T}",
                "mode": "import",
                "source": {"type": "m", "expression": m_query}
            }],
            "annotations": [
                {"name": "PBI_ResultType",         "value": "Table"},
                {"name": "PBI_NavigationStepName", "value": "Navigation"}
            ]
        }],
        "relationships": [],
        "cultures": [{"name": "en-US", "linguisticMetadata": {"version": "1.0.0", "language": "en-US"}}],
        "annotations": [
            {"name": "__PBI_TimeIntelligenceEnabled", "value": "1"},
            {"name": "PBIDesktopVersion",             "value": "2.136.0.0"}
        ]
    }
    return json.dumps(schema, indent=2, ensure_ascii=False)

# ─────────────────────────────────────────────────────────────────────────────
# STATIC FILES
# ─────────────────────────────────────────────────────────────────────────────
CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="xml"  ContentType="application/xml"/>
  <Override PartName="/DataModelSchema" ContentType="application/json"/>
  <Override PartName="/Report/Layout"   ContentType="application/json"/>
</Types>"""

SETTINGS        = json.dumps({"Version": 3, "QueryGroupsSerializationVersion": 1})
METADATA        = json.dumps({"version": "4.0", "cultures": ["en-US"]})
DIAGRAM_LAYOUT  = json.dumps({
    "version": 1,
    "tables": [{"id": 0, "name": TABLE, "x": 100, "y": 100, "height": 300, "width": 300}]
})

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    print("Building data model schema ...")
    data_model = build_data_model()

    print("Building report layout (4 pages) ...")
    layout = build_layout()

    print(f"Writing {OUT_PATH} ...")
    with zipfile.ZipFile(OUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("Version",             "2.0")
        zf.writestr("Settings",            SETTINGS)
        zf.writestr("Metadata",            METADATA)
        zf.writestr("DataModelSchema",     data_model)
        zf.writestr("DiagramLayout",       DIAGRAM_LAYOUT)
        zf.writestr("Report/Layout",       layout)

    size_kb = os.path.getsize(OUT_PATH) // 1024
    print(f"\nDone! SentimentDashboard.pbit ({size_kb} KB)")
    print(f"   Path: {OUT_PATH}")
    print("\n   Next: Double-click SentimentDashboard.pbit to open in Power BI Desktop.")
    print("         All 4 pages, 13 measures, and all visuals are pre-built.")

if __name__ == "__main__":
    main()
