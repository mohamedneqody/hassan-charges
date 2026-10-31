"""Optional sector-benchmark loader for the Overview comparison table.

Two sources, in priority order for a chosen sector:
  1. `sector_benchmarks/<sector>.csv` — one preset file per sector (the file
     NAME is the sector label, e.g. «الحديد والصلب.csv»). Shipped presets are
     conservative guideline ranges; edit them with your own sourced numbers.
  2. `sector_benchmarks.csv` at the project root — the user's own custom file.

Format (header row required; one row per metric; "higher is better" assumed
for all listed metrics — use the inverse metric when that is not true, e.g.
debt_ratio is NOT listed by default):

    metric,weak,fair,good
    current_ratio,1.0,1.5,2.0
    net_margin,3,8,15

Values are plain numbers in the metric's own unit (x for ratios, % for
margins). When nothing matches, the loader returns the built-in GENERAL
guideline levels — clearly labelled "إرشادي عام" in the UI so nobody mistakes
them for sector data.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/analysis/… → project root
BENCHMARKS_CSV = PROJECT_ROOT / "sector_benchmarks.csv"
SECTOR_DIR = PROJECT_ROOT / "sector_benchmarks"

# metric-key -> (display label AR, higher_is_better)
DISPLAY = {
    "current_ratio": ("النسبة الجارية (x)", True),
    "quick_ratio": ("النسبة السريعة (x)", True),
    "cash_ratio": ("نسبة النقدية (x)", True),
    "net_margin": ("هامش صافي الربح (%)", True),
    "gross_margin": ("هامش مجمل الربح (%)", True),
    "operating_margin": ("هامش التشغيل (%)", True),
    "roe": ("العائد على حقوق الملكية (%)", True),
    "roa": ("العائد على الأصول (%)", True),
    "asset_turnover": ("دوران الأصول (x)", True),
    "debt_to_equity": ("الدين/حقوق الملكية (x)", False),
}

# Built-in GENERAL guideline levels (never presented as sector data).
GENERAL = {
    "current_ratio": (1.0, 1.5, 2.0),
    "quick_ratio": (0.7, 1.0, 1.5),
    "cash_ratio": (0.2, 0.5, 1.0),
    "net_margin": (3.0, 8.0, 15.0),
    "roe": (8.0, 12.0, 18.0),
    "roa": (3.0, 5.0, 10.0),
    "asset_turnover": (0.5, 1.0, 2.0),
    "debt_to_equity": (2.0, 1.0, 0.5),
}


@dataclass
class Benchmarks:
    source: str  # "sector" | "general"
    rows: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    sector_name: str | None = None  # set when source == "sector"


def _parse_levels_csv(path: Path) -> dict[str, tuple[float, float, float]] | None:
    try:
        with open(path, encoding="utf-8-sig") as f:
            rows: dict[str, tuple[float, float, float]] = {}
            for rec in csv.DictReader(f):
                key = (rec.get("metric") or "").strip()
                try:
                    weak, fair, good = (
                        float(rec["weak"]), float(rec["fair"]), float(rec["good"])
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                if key in DISPLAY:
                    rows[key] = (weak, fair, good)
            return rows or None
    except Exception:
        return None


def available_sectors() -> list[str]:
    """Sector preset names = the .csv file names inside sector_benchmarks/."""
    if not SECTOR_DIR.exists():
        return []
    return sorted(p.stem for p in SECTOR_DIR.glob("*.csv"))


def general_benchmarks() -> Benchmarks:
    """The explicit «عام» choice — built-in guidelines, never file-backed."""
    return Benchmarks(source="general", rows=dict(GENERAL))


def load_benchmarks(sector: str | None = None) -> Benchmarks:
    """sector=None → the root custom file (or GENERAL). Otherwise the named
    preset file first, then the root file, then GENERAL."""
    if sector:
        # keep the sector label out of path traversal
        safe = sector.replace("/", " ").replace("\\", " ").strip()
        path = SECTOR_DIR / f"{safe}.csv"
        if path.exists():
            rows = _parse_levels_csv(path)
            if rows:
                return Benchmarks(source="sector", rows=rows, sector_name=safe)
    if BENCHMARKS_CSV.exists():
        rows = _parse_levels_csv(BENCHMARKS_CSV)
        if rows:
            return Benchmarks(source="sector", rows=rows, sector_name="مخصص")
    return Benchmarks(source="general", rows=dict(GENERAL))


def band_for(value: float | None, levels: tuple[float, float, float],
             higher_is_better: bool) -> str:
    """'ضعيف' / 'مقبول' / 'جيد' — or '' when no value."""
    if value is None:
        return ""
    weak, fair, good = levels
    if higher_is_better:
        if value >= good:
            return "جيد"
        if value >= fair:
            return "مقبول"
        return "ضعيف"
    if value <= good:
        return "جيد"
    if value <= fair:
        return "مقبول"
    return "ضعيف"
