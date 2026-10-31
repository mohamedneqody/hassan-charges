"""Peer-group comparison (مقارنة الأقران) — how analysts actually benchmark.

Static thresholds («current ratio 1.5 is fine») say little; the professional
question is «compared to WHOM?». This module ranks the current company
against every company already solved into the companies library:

- median / interquartile range per metric across the peers
- the current company's standing vs the peer median

Pure statistics over locally saved records — zero API calls. Requires at
least TWO other solved companies; below that the honest answer is «sample
too small», not a made-up benchmark.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.analysis.portfolio import CompanyRecord, load_records

# metric key -> (record attr, YearMetrics attr, display label AR, higher_is_better)
# (record and metric objects name the margins differently: net_margin_pct vs net_margin)
PEER_METRICS = {
    "net_margin": ("net_margin_pct", "net_margin", "هامش صافي الربح", True),
    "roe": ("roe_pct", "roe", "العائد على حقوق الملكية", True),
    "roa": ("roa_pct", "roa", "العائد على الأصول", True),
    "current_ratio": ("current_ratio", "current_ratio", "النسبة الجارية", True),
    "debt_to_equity": ("debt_to_equity", "debt_to_equity", "الدين/حقوق الملكية", False),
    "asset_turnover": ("asset_turnover", "asset_turnover", "دوران الأصول", True),
}

MIN_PEERS = 2  # below this the sample is noise


@dataclass
class PeerRow:
    metric: str
    label: str
    higher_is_better: bool
    value: float | None
    median: float | None
    q25: float | None
    q75: float | None
    n_peers: int
    standing: str  # "أعلى من الأقران" | "قرب الوسيط" | "أدنى من الأقران" | ""


def _quartiles(vals: list[float]) -> tuple[float, float, float]:
    """(q25, median, q75) — small samples handled with plain sorting."""
    s = sorted(vals)
    n = len(s)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    lower = s[: max(1, n // 2)]
    upper = s[n // 2 + (1 if n % 2 else 0):] or s[-1:]
    q25 = lower[len(lower) // 2] if len(lower) % 2 else (lower[len(lower) // 2 - 1] + lower[len(lower) // 2]) / 2
    q75 = upper[len(upper) // 2] if len(upper) % 2 else (upper[len(upper) // 2 - 1] + upper[len(upper) // 2]) / 2
    return q25, med, q75


def peer_comparison(metrics, company: str, curr_year: int,
                    records: list[CompanyRecord] | None = None) -> list[PeerRow]:
    """Rank `metrics` (YearMetrics) against the library peers. The company's
    own record (same name+year) is excluded — you don't benchmark against
    yourself."""
    if records is None:
        records = load_records()
    peers = [r for r in records
             if not (r.company.strip().lower() == company.strip().lower()
                     and r.curr_year == curr_year)]
    if len(peers) < MIN_PEERS:
        return []

    rows: list[PeerRow] = []
    for key, (rec_attr, met_attr, label, hib) in PEER_METRICS.items():
        value = getattr(metrics, met_attr, None)
        peer_vals = [getattr(p, rec_attr) for p in peers if getattr(p, rec_attr) is not None]
        if value is None or len(peer_vals) < MIN_PEERS:
            continue
        q25, med, q75 = _quartiles(peer_vals)
        if hib:
            standing = "أعلى من الأقران" if value > q75 else (
                "أدنى من الأقران" if value < q25 else "قرب وسيط الأقران")
        else:
            standing = "أعلى من الأقران" if value < q25 else (
                "أدنى من الأقران" if value > q75 else "قرب وسيط الأقران")
        rows.append(PeerRow(key, label, hib, value, med, q25, q75,
                            len(peer_vals), standing))
    return rows


# --- Anomaly screen (كشف الشذوذ): ±2σ vs the peer group ---------------------- #

Z_OUTLIER = 2.0  # |z| beyond this = statistical outlier vs peers


@dataclass
class AnomalyRow:
    metric: str
    label: str
    value: float
    peer_mean: float
    peer_std: float
    z: float
    verdict: str  # Arabic reading, aware of higher/lower-is-better


def _sample_std(vals: list[float]) -> float | None:
    n = len(vals)
    if n < 2:
        return None
    mean = sum(vals) / n
    return (sum((v - mean) ** 2 for v in vals) / (n - 1)) ** 0.5


def detect_anomalies(metrics, company: str, curr_year: int,
                     records: list[CompanyRecord] | None = None) -> list[AnomalyRow]:
    """Flag company metrics farther than Z_OUTLIER standard deviations from the
    peer mean (sample std). A metric with no peer spread (std = 0) or fewer
    than MIN_PEERS readings is skipped — no anomaly call without a real
    distribution. Pure statistics, zero API."""
    if records is None:
        records = load_records()
    peers = [r for r in records
             if not (r.company.strip().lower() == company.strip().lower()
                     and r.curr_year == curr_year)]
    out: list[AnomalyRow] = []
    for key, (rec_attr, met_attr, label, hib) in PEER_METRICS.items():
        value = getattr(metrics, met_attr, None)
        peer_vals = [getattr(p, rec_attr) for p in peers if getattr(p, rec_attr) is not None]
        if value is None or len(peer_vals) < MIN_PEERS:
            continue
        std = _sample_std(peer_vals)
        if not std:
            continue
        mean = sum(peer_vals) / len(peer_vals)
        z = (value - mean) / std
        if abs(z) <= Z_OUTLIER:
            continue
        if z > 0:
            verdict = ("ميزة استثنائية مقابل الأقران" if hib
                       else "مخاطرة استثنائية أعلى من الأقران")
        else:
            verdict = ("ضعف استثنائي مقارنة بالأقران" if hib
                       else "تحفظ استثنائي في المؤشر")
        out.append(AnomalyRow(key, label, value, round(mean, 4), round(std, 4),
                              round(z, 2), verdict))
    return out
