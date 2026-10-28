from datetime import datetime, timedelta, timezone

from anomaly import score_windows, window_metrics


def test_volume_and_negative_ratio_spike_are_scored():
    base=datetime(2026,1,1,tzinfo=timezone.utc)
    rows=[]
    for minute in range(8):
        count=8 if minute==7 else 2
        negative=minute==7
        for i in range(count):
            rows.append({"timestamp":(base+timedelta(minutes=minute,seconds=i)).isoformat(),
                "tweet":f"post {minute}-{i}","brand":"Acme" if i < 2 else "NewBrand",
                "sentiment":"Negative" if negative else "Positive","polarity":-.7 if negative else .5})
    windows=window_metrics(rows)
    assert len(windows)==8
    found={alert["metric"] for alert in score_windows(rows)}
    assert "volume" in found
    assert "negative_ratio" in found


def test_insufficient_window_history_does_not_alert():
    rows=[{"timestamp":"2026-01-01T00:00:00+00:00","sentiment":"Negative","polarity":-.5,"brand":"A"}]
    assert score_windows(rows)==[]
