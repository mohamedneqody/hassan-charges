# -*- coding: utf-8 -*-
"""Unit tests for v9.20 executive charts, formatting, and empty-data safety."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import plotly.graph_objects as go

PROJ = Path(__file__).resolve().parents[1]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

from src.analysis.calculator import compute_year_metrics
from src.analysis.comparison import build_comparison, growth_metrics
from src.analysis.score import compute_health_score
from src.dashboard import charts


def _sample_data() -> dict[str, dict[int, float]]:
    return {
        "revenue": {2024: 10_000_000.0, 2025: 12_500_000.0},
        "cost_of_goods_sold": {2024: 6_000_000.0, 2025: 7_200_000.0},
        "gross_profit": {2024: 4_000_000.0, 2025: 5_300_000.0},
        "operating_income": {2024: 2_500_000.0, 2025: 3_400_000.0},
        "net_income": {2024: 1_800_000.0, 2025: 2_600_000.0},
        "total_assets": {2024: 15_000_000.0, 2025: 18_000_000.0},
        "current_assets": {2024: 6_000_000.0, 2025: 7_500_000.0},
        "inventory": {2024: 1_200_000.0, 2025: 1_500_000.0},
        "current_liabilities": {2024: 3_000_000.0, 2025: 3_500_000.0},
        "total_liabilities": {2024: 7_000_000.0, 2025: 8_000_000.0},
        "total_debt": {2024: 4_000_000.0, 2025: 4_200_000.0},
        "equity": {2024: 8_000_000.0, 2025: 10_000_000.0},
        "operating_cash_flow": {2024: 2_200_000.0, 2025: 3_100_000.0},
        "investing_cash_flow": {2024: -900_000.0, 2025: -1_200_000.0},
        "financing_cash_flow": {2024: -500_000.0, 2025: -600_000.0},
    }


def test_income_summary_and_balance_structure_charts():
    data = _sample_data()
    prev_m = compute_year_metrics(2024, data)
    curr_m = compute_year_metrics(2025, data, prev_year=2024)

    fig_inc = charts.income_summary_chart(prev_m, curr_m, 2024, 2025, currency="EGP ", scale=1, lang="ar")
    assert isinstance(fig_inc, go.Figure)
    assert len(fig_inc.data) == 2
    assert len(fig_inc.data[0].x) == 4

    fig_bal = charts.balance_structure_chart(prev_m, curr_m, 2024, 2025, currency="EGP ", scale=1, lang="ar")
    assert isinstance(fig_bal, go.Figure)
    assert fig_bal.layout.barmode == "stack"
    assert len(fig_bal.data) == 3  # Equity, Current Liab, Non-Current Liab

    # Empty data returns None gracefully
    empty = SimpleNamespace()
    assert charts.income_summary_chart(empty, empty, 2024, 2025) is None
    assert charts.balance_structure_chart(empty, empty, 2024, 2025) is None


def test_health_radar_chart():
    data = _sample_data()
    curr_m = compute_year_metrics(2025, data, prev_year=2024)
    hs = compute_health_score(curr_m)
    fig = charts.health_radar_chart(hs, lang="ar")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 2  # Benchmark + Company score

    fig_en = charts.health_radar_chart(hs, lang="en")
    assert isinstance(fig_en, go.Figure)

    # Fewer than 3 valid pillars returns None gracefully
    sparse = SimpleNamespace(pillars=[SimpleNamespace(name="A", name_ar="أ", score=50.0)])
    assert charts.health_radar_chart(sparse) is None


def test_growth_bar_and_insights_donut_charts():
    data = _sample_data()
    prev_m = compute_year_metrics(2024, data)
    curr_m = compute_year_metrics(2025, data, prev_year=2024)
    g_rows = growth_metrics(prev_m, curr_m)

    fig_g = charts.growth_bar_chart(g_rows, curr_year=2025, lang="ar")
    assert isinstance(fig_g, go.Figure)
    assert len(fig_g.data) == 1

    # Synthetic growth rows check
    synth = [
        SimpleNamespace(key="revenue_growth", label="Revenue Growth", label_ar="نمو الإيرادات", current=25.0),
        SimpleNamespace(key="net_income_growth", label="Net Income Growth", label_ar="نمو صافي الربح", current=-10.5),
    ]
    fig_s = charts.growth_bar_chart(synth, curr_year=2025, lang="ar")
    assert isinstance(fig_s, go.Figure)
    assert list(fig_s.data[0].marker.color) == ["#EF4444", "#10B981"]

    assert charts.growth_bar_chart([]) is None

    fig_d = charts.insights_donut_chart(5, 2, 1, lang="ar")
    assert isinstance(fig_d, go.Figure)
    assert sum(fig_d.data[0].values) == 8
    assert charts.insights_donut_chart(0, 0, 0) is None


def test_cashflow_chart_supports_unit_scale():
    data = _sample_data()
    prev_m = compute_year_metrics(2024, data)
    curr_m = compute_year_metrics(2025, data, prev_year=2024)
    rows = build_comparison(prev_m, curr_m)
    by_key = {r.key: r for r in rows}

    fig_1x = charts.cashflow_chart(by_key, 2024, 2025, "$", scale=1, lang="en")
    fig_1k = charts.cashflow_chart(by_key, 2024, 2025, "$", scale=1000, lang="ar")
    assert fig_1k.data[0].y[0] == fig_1x.data[0].y[0] * 1000


def test_resolve_cell_bbox_sibling_year_row_band():
    from src.dashboard.new_ui import _extract_bbox_coords
    from src.dashboard.view_model import resolve_cell_bbox

    bbox_map = {
        "revenue|2022": [{"page": 4, "bbox_px": [120, 400, 320, 430], "render_scale": 2.0}]
    }
    # Direct hit keeps original box
    direct = resolve_cell_bbox(bbox_map, "revenue", 2022, [4])
    assert isinstance(direct, list)

    # Sibling year on same page produces a full-row band fallback
    sib = resolve_cell_bbox(bbox_map, "revenue", 2021, [4])
    assert isinstance(sib, dict) and sib.get("row_band") is True
    assert sib.get("page") == 4

    coords = _extract_bbox_coords(sib, page_no=4, img_w=1000, img_h=1400, target_scale=2.0)
    assert coords == (20.0, 400.0, 980.0, 430.0)
