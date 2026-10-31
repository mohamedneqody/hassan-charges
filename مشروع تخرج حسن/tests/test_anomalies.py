"""Anomaly screen (±2σ vs peers): fixtures with a tight peer cluster and a
company far outside it — hand-computed z-scores, plus the honest skips
(zero spread, too few peers)."""
from __future__ import annotations

import pytest

from src.analysis.calculator import YearMetrics
from src.analysis.peers import MIN_PEERS, detect_anomalies
from src.analysis.portfolio import CompanyRecord


def rec(name: str, nm: float, roe: float, roa: float, cr: float, dte: float, at: float) -> CompanyRecord:
    return CompanyRecord(
        company=name, file_name=f"{name}.pdf", prev_year=2023, curr_year=2024,
        net_margin_pct=nm, roe_pct=roe, roa_pct=roa,
        current_ratio=cr, debt_to_equity=dte, asset_turnover=at,
    )


# Tight peer cluster: mean 10.0 ± 0.1 (net margin), 12.0 ± 0.1 (ROE),
# 5.0 ± 0.1 (ROA), 1.8 ± 0.1 (CR), 0.5 ± 0.05 (DtE), 1.0 ± 0.1 (AT)
PEERS = [
    rec("peerA", 9.9, 11.9, 4.9, 1.79, 0.45, 0.99),
    rec("peerB", 10.0, 12.0, 5.0, 1.80, 0.50, 1.00),
    rec("peerC", 10.1, 12.1, 5.1, 1.81, 0.55, 1.01),
]


def target(nm: float, dte: float) -> YearMetrics:
    return YearMetrics(
        year=2024,
        net_margin=nm, roe=12.0, roa=5.0,
        current_ratio=1.8, debt_to_equity=dte, asset_turnover=1.0,
    )


def test_outlier_metrics_are_flagged_with_hand_computed_z():
    # net_margin: mean 10.0, sample std 0.1 → z = (15 − 10)/0.1 = +50
    # debt_to_equity: mean 0.5, sample std 0.05 → z = (5 − 0.5)/0.05 = +90
    rows = detect_anomalies(target(nm=15.0, dte=5.0), "الشركة الهدف", 2024, records=PEERS)
    flagged = {r.metric: r for r in rows}
    assert set(flagged) == {"net_margin", "debt_to_equity"}
    assert flagged["net_margin"].z == pytest.approx(50.0, abs=0.5)
    assert flagged["debt_to_equity"].z == pytest.approx(90.0, abs=0.5)
    # higher-is-better metric far ABOVE peers = exceptional strength
    assert "ميزة" in flagged["net_margin"].verdict
    # lower-is-better metric far ABOVE peers = exceptional risk
    assert "مخاطرة" in flagged["debt_to_equity"].verdict


def test_values_inside_two_sigma_are_not_flagged():
    rows = detect_anomalies(target(nm=10.15, dte=0.5), "الشركة الهدف", 2024, records=PEERS)
    # nm z = +1.5 (inside), dte: peers std 0.05, value 0.5 → z = 0 (inside)
    assert rows == []


def test_low_outlier_on_higher_is_better_reads_as_weakness():
    rows = detect_anomalies(target(nm=2.0, dte=0.5), "الشركة الهدف", 2024, records=PEERS)
    nm = next(r for r in rows if r.metric == "net_margin")
    assert nm.z < -2
    assert "ضعف" in nm.verdict


def test_zero_peer_spread_is_skipped_not_flagged():
    flat = [
        rec("pA", 10.0, 12.0, 5.0, 1.8, 0.5, 1.0),
        rec("pB", 10.0, 12.0, 5.0, 1.8, 0.5, 1.0),
        rec("pC", 10.0, 12.0, 5.0, 1.8, 0.5, 1.0),
    ]
    assert detect_anomalies(target(nm=50.0, dte=9.0), "الشركة الهدف", 2024, records=flat) == []


def test_too_few_peers_returns_empty():
    assert detect_anomalies(target(nm=15.0, dte=5.0), "الشركة الهدف", 2024,
                            records=PEERS[: MIN_PEERS - 1]) == []


def test_self_record_is_excluded_from_its_own_peers():
    self_rec = rec("الشركة الهدف", 15.0, 12.0, 5.0, 1.8, 5.0, 1.0)
    rows = detect_anomalies(target(nm=15.0, dte=5.0), "الشركة الهدف", 2024,
                            records=PEERS + [self_rec])
    flagged = {r.metric for r in rows}
    assert flagged == {"net_margin", "debt_to_equity"}  # unchanged by its own record
