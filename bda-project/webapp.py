"""Local SentinelPulse dashboard API for the existing sentiment pipeline."""
from __future__ import annotations

import csv
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import BASE_DIR, DATASET, OUTPUT

app = FastAPI(title="SentinelPulse", version="1.0.0", description="Social sentiment analytics dashboard")
STATIC = BASE_DIR / "web"
_lock = threading.RLock()
_demo_active = False
_demo_speed = 1.0
_demo_index = 0
_demo_touched = False
_replay_thread: threading.Thread | None = None
_replay_stop = threading.Event()
_alerts: list[dict[str, Any]] = []
_alert_statuses: dict[str, str] = {}
_records: list[dict[str, Any]] = []


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_records() -> list[dict[str, Any]]:
    candidates = [BASE_DIR / "output" / "sentiment_results_enriched.csv", OUTPUT.sentiment_csv_path]
    candidates.extend(OUTPUT.sentiment_csv_dir.glob("part-*.csv"))
    available = [p for p in candidates if p.exists() and p.is_file()]
    path = max(available, key=lambda p: p.stat().st_mtime) if available else None
    rows: list[dict[str, Any]] = []
    if path:
        try:
            with path.open(newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    tweet = row.get("tweet") or row.get("tweet_text") or row.get("text") or ""
                    if not tweet:
                        continue
                    rows.append({
                        "timestamp": row.get("timestamp") or row.get("produced_at") or "",
                        "tweet": tweet, "brand": row.get("brand") or row.get("entity") or "Other",
                        "sentiment": (row.get("sentiment") or row.get("sentiment_label") or "Neutral").title(),
                        "polarity": _number(row.get("polarity")),
                        "subjectivity": _number(row.get("subjectivity")),
                        "confidence": _number(row.get("confidence")),
                    })
        except (OSError, csv.Error):
            pass
    if not rows and DATASET.sample_csv_path.exists():
        with DATASET.sample_csv_path.open(newline="", encoding="utf-8-sig") as f:
            for i, row in enumerate(csv.DictReader(f)):
                rows.append({"timestamp": (datetime.now() - timedelta(minutes=29-i)).isoformat(timespec="seconds"),
                    "tweet": row.get("tweet_text", ""), "brand": row.get("entity", "Other"),
                    "sentiment": (row.get("sentiment_label") or "Neutral").title(),
                    "polarity": {"Positive": .42, "Negative": -.42, "Neutral": 0}[ (row.get("sentiment_label") or "Neutral").title() ],
                    "subjectivity": .5, "confidence": .72})
    return rows


def _data() -> list[dict[str, Any]]:
    with _lock:
        if not _records:
            _records.extend(_read_records())
        return list(_records)


def _replay() -> None:
    global _demo_index, _demo_touched
    source = _data()
    if not source:
        return
    while not _replay_stop.wait(max(.125, 1 / _demo_speed)):
        row = dict(source[_demo_index % len(source)])
        _demo_index += 1
        row["timestamp"] = datetime.now().isoformat(timespec="seconds")
        with _lock:
            _records.append(row)
            _demo_touched = True
            if len(_records) > 5000:
                del _records[:1000]


def _filtered(records: list[dict[str, Any]], brand: str = "all", sentiment: str = "all", search: str = "") -> list[dict[str, Any]]:
    return [r for r in records if (brand.lower() == "all" or r["brand"].lower() == brand.lower())
            and (sentiment.lower() == "all" or r["sentiment"].lower() == sentiment.lower())
            and (not search or search.lower() in r["tweet"].lower() or search.lower() in r["brand"].lower())]


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "SentinelPulse", "records": len(_data())}


@app.post("/api/refresh")
def refresh():
    if _demo_touched:
        return {"records": len(_data()), "source": "demo replay"}
    rows = _read_records()
    with _lock:
        _records.clear()
        _records.extend(rows)
    return {"records": len(rows), "source": "latest CSV"}


@app.get("/api/dashboard")
def dashboard(brand: str = "all", search: str = ""):
    rows = _filtered(_data(), brand, "all", search)
    n = len(rows) or 1
    counts = Counter(r["sentiment"] for r in rows)
    by_brand: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_minute: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_brand[r["brand"]].append(r)
        stamp = str(r["timestamp"] or "")
        try:
            dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            key = dt.strftime("%H:%M")
        except ValueError:
            key = "—"
        by_minute[key].append(r)
    return {"total": len(rows), "positive": counts["Positive"], "negative": counts["Negative"],
            "neutral": counts["Neutral"], "positive_pct": round(counts["Positive"] / n * 100, 1),
            "negative_pct": round(counts["Negative"] / n * 100, 1),
            "avg_polarity": round(sum(r["polarity"] for r in rows) / n, 3),
            "tweets_per_min": round(len(rows) / 30, 1), "active_alerts": sum(a["status"] == "Open" for a in alerts()),
            "brands": [{"brand": k, "total": len(v), "polarity": round(sum(x["polarity"] for x in v)/len(v), 3),
                        "negative": round(sum(x["sentiment"] == "Negative" for x in v)/len(v)*100)}
                       for k, v in sorted(by_brand.items(), key=lambda p: len(p[1]), reverse=True)],
            "timeline": [{"time": k, "positive": sum(x["sentiment"] == "Positive" for x in v),
                          "negative": sum(x["sentiment"] == "Negative" for x in v),
                          "neutral": sum(x["sentiment"] == "Neutral" for x in v),
                          "polarity": round(sum(x["polarity"] for x in v)/len(v), 3)}
                         for k, v in sorted(by_minute.items())],
            "brands_list": sorted({r["brand"] for r in _data() if r["brand"] != "Other"})}


@app.get("/api/tweets")
def tweets(brand: str = "all", sentiment: str = "all", search: str = "", page: int = Query(1, ge=1), limit: int = Query(12, ge=1, le=100)):
    rows = list(reversed(_filtered(_data(), brand, sentiment, search)))
    start = (page - 1) * limit
    return {"items": rows[start:start+limit], "total": len(rows), "page": page, "pages": max(1, (len(rows)+limit-1)//limit)}


@app.get("/api/alerts")
def alerts():
    auto = []
    rows = _data()
    neg = sum(r["sentiment"] == "Negative" for r in rows)
    if rows and neg / len(rows) > .3:
        auto.append({"id": "negative-share", "title": "Elevated negative sentiment", "detail": f"{neg/len(rows)*100:.0f}% of the current stream is negative.", "severity": "High", "status": _alert_statuses.get("negative-share", "Open"), "time": "Now"})
    known = {a["id"] for a in _alerts}
    return auto + [a for a in reversed(_alerts) if a["id"] not in known or a["id"] != "negative-share"]


@app.post("/api/alerts/{alert_id}/{action}")
def update_alert(alert_id: str, action: str):
    if action not in {"acknowledge", "resolve"}:
        return {"error": "Unknown action"}
    _alert_statuses[alert_id] = "Acknowledged" if action == "acknowledge" else "Resolved"
    with _lock:
        for alert in _alerts:
            if alert["id"] == alert_id:
                alert["status"] = "Acknowledged" if action == "acknowledge" else "Resolved"
                return alert
    return {"id": alert_id, "status": "Acknowledged" if action == "acknowledge" else "Resolved"}


@app.get("/api/control")
def control_state():
    return {"active": _demo_active, "speed": _demo_speed, "mode": "demo", "source": "local CSV replay"}


@app.post("/api/control/{action}")
def control(action: str, speed: float = Query(1.0, ge=.25, le=8)):
    global _demo_active, _demo_speed, _replay_thread
    if action not in {"start", "pause"}:
        return {"error": "Unknown action"}
    _demo_speed = speed
    _demo_active = action == "start"
    if _demo_active and (_replay_thread is None or not _replay_thread.is_alive()):
        _replay_stop.clear()
        _replay_thread = threading.Thread(target=_replay, name="sentinelpulse-demo-replay", daemon=True)
        _replay_thread.start()
    elif not _demo_active:
        _replay_stop.set()
    return control_state()


@app.post("/api/inject-anomaly")
def inject_anomaly():
    global _demo_index, _demo_touched
    source = _data()
    neg = [r for r in source if r["sentiment"] == "Negative"]
    seed = neg[_demo_index % len(neg)] if neg else {"brand": "Demo brand", "tweet": "Service is broken and the experience is terrible", "polarity": -.8, "subjectivity": .9, "sentiment": "Negative", "confidence": .9}
    _demo_index += 1
    row = {**seed, "timestamp": datetime.now().isoformat(timespec="seconds"), "tweet": f"[DEMO SPIKE] {seed['tweet']}", "brand": seed["brand"]}
    with _lock:
        _records.append(row)
        _demo_touched = True
        _alerts.append({"id": f"demo-{_demo_index}", "title": f"Negative sentiment spike · {row['brand']}",
            "detail": "Demo anomaly injected into the local stream for dashboard review.", "severity": "High", "status": "Open", "time": "Just now"})
    return {"tweet": row, "alert": _alerts[-1]}


@app.get("/api/export.csv")
def export_csv(brand: str = "all", sentiment: str = "all", search: str = ""):
    import io
    from fastapi.responses import StreamingResponse
    out = io.StringIO()
    fields = ["timestamp", "tweet", "brand", "sentiment", "polarity", "subjectivity", "confidence"]
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(_filtered(_data(), brand, sentiment, search))
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sentinelpulse-report.csv"})


app.mount("/assets", StaticFiles(directory=STATIC), name="assets")
