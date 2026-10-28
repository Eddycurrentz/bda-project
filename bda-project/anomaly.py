"""Windowed sentiment anomaly scoring using rolling z scores and Isolation Forest."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import sqrt
from statistics import mean, pstdev
from typing import Any


def _time(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def window_metrics(records: list[dict[str, Any]], seconds: int = 60) -> list[dict[str, Any]]:
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        dt = _time(row.get("timestamp"))
        if dt:
            epoch = int(dt.timestamp())
            buckets[epoch - epoch % seconds].append(row)
    return [{"window_start": datetime.fromtimestamp(key, timezone.utc).isoformat(),
             "volume": len(rows),
             "mean_polarity": sum(float(r.get("polarity", 0)) for r in rows) / len(rows),
             "negative_ratio": sum(r.get("sentiment") == "Negative" for r in rows) / len(rows),
             "brands": {brand: sum(r.get("brand") == brand for r in rows) for brand in {r.get("brand", "Other") for r in rows}}}
            for key, rows in sorted(buckets.items())]


def _z(value: float, baseline: list[float]) -> float:
    if len(baseline) < 3:
        return 0.0
    sd = pstdev(baseline)
    if sd < 1e-9:
        return 0.0 if abs(value - mean(baseline)) < 1e-9 else 5.0
    return (value - mean(baseline)) / sd


def score_windows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    windows = window_metrics(records)
    if len(windows) < 4:
        return []
    current = windows[-1]
    history = windows[:-1][-30:]
    volumes = [float(w["volume"]) for w in history]
    negatives = [float(w["negative_ratio"]) for w in history]
    volume_z = _z(float(current["volume"]), volumes)
    negative_z = _z(float(current["negative_ratio"]), negatives)
    isolation_score = 0.0
    if len(windows) >= 8:
        try:
            from sklearn.ensemble import IsolationForest
            rows = [[w["volume"], w["mean_polarity"], w["negative_ratio"]] for w in windows]
            model = IsolationForest(n_estimators=100, contamination="auto", random_state=31)
            model.fit(rows[:-1])
            isolation_score = float(-model.decision_function([rows[-1]])[0])
        except (ImportError, ValueError, ZeroDivisionError):
            isolation_score = 0.0
    alerts = []
    if volume_z >= 2.5 and current["volume"] >= 3:
        alerts.append({"id": "window-volume-" + current["window_start"], "title": "Tweet volume spike", "severity": "High" if volume_z >= 4 else "Medium",
                       "reason": f"Current window has {current['volume']} mentions ({volume_z:.1f} standard deviations above baseline).",
                       "score": round(min(volume_z/5, 1), 3), "metric": "volume", "window": current["window_start"]})
    if negative_z >= 2.5 and current["negative_ratio"] >= .5:
        alerts.append({"id": "window-negative-" + current["window_start"], "title": "Negative sentiment surge", "severity": "High" if negative_z >= 4 else "Medium",
                       "reason": f"Negative share is {current['negative_ratio']*100:.0f}% ({negative_z:.1f} standard deviations above baseline).",
                       "score": round(min(negative_z/5, 1), 3), "metric": "negative_ratio", "window": current["window_start"]})
    if isolation_score >= .08:
        alerts.append({"id": "window-isolation-" + current["window_start"], "title": "Unusual sentiment pattern", "severity": "Medium",
                       "reason": "Isolation Forest flagged an atypical combination of volume and sentiment metrics.",
                       "score": round(min(isolation_score, 1), 3), "metric": "multivariate", "window": current["window_start"]})
    brands = set(current["brands"])
    for brand in brands:
        baseline = [float(w["brands"].get(brand, 0)) for w in history]
        count = int(current["brands"].get(brand, 0))
        brand_z = _z(float(count), baseline)
        if count >= 3 and brand_z >= 2.5:
            alerts.append({"id": f"brand-{brand}-" + current["window_start"], "title": f"Unusual activity · {brand}", "severity": "Medium",
                           "reason": f"{count} mentions for {brand} landed in one window ({brand_z:.1f} standard deviations above baseline).",
                           "score": round(min(brand_z/5, 1), 3), "metric": "brand_volume", "brand": brand,
                           "window": current["window_start"]})
    return alerts
