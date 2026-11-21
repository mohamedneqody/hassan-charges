"""Company-results library for the EGX applied study (مقارنة الشركات).

Every successful analysis is saved as one small JSON record under
`companies_library/`. The «مقارنة الشركات» tab reads them all and builds the
cross-company table + chart + CSV export that the thesis's applied-study
chapter needs. Fully deterministic — no API calls.

A record is keyed by (company, current year): re-analyzing the same company
and year overwrites its record, so the library never grows stale duplicates.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = PROJECT_ROOT / "companies_library"

_LOCK = threading.Lock()

_SAVE_FIELDS = (
    "revenue", "net_income", "net_margin_pct", "roe_pct", "roa_pct",
    "current_ratio", "debt_to_equity", "asset_turnover",
    "health_total", "health_label", "altman_score", "altman_zone",
)


@dataclass
class CompanyRecord:
    company: str
    file_name: str
    prev_year: int
    curr_year: int
    currency: str = "$"
    saved_at: str = ""
    revenue: float | None = None
    net_income: float | None = None
    net_margin_pct: float | None = None
    roe_pct: float | None = None
    roa_pct: float | None = None
    current_ratio: float | None = None
    debt_to_equity: float | None = None
    asset_turnover: float | None = None
    health_total: float | None = None
    health_label: str = ""
    altman_score: float | None = None
    altman_zone: str = ""  # zone_ar


def record_from_results(results: dict) -> CompanyRecord:
    """Extract the study-relevant snapshot from a pipeline result dict."""
    from src.analysis.advanced import altman_z
    from src.analysis.score import compute_health_score

    m = results["curr_metrics"]
    blocked = set(results.get("blocked_fields") or [])
    score = compute_health_score(m, blocked_fields=blocked)
    try:
        az = altman_z(m)
        alt_score, alt_zone = az.score, az.zone_ar
    except Exception:
        alt_score, alt_zone = None, ""

    def num(value: float | None) -> float | None:
        try:
            return None if value is None else round(float(value), 4)
        except (TypeError, ValueError):
            return None

    return CompanyRecord(
        company=str(results.get("company") or results.get("file_name") or "غير معروف"),
        file_name=str(results.get("file_name") or ""),
        prev_year=int(results["prev_year"]),
        curr_year=int(results["curr_year"]),
        currency=str(results.get("currency_hint") or "$"),
        saved_at=datetime.now().isoformat(timespec="seconds"),
        revenue=num(m.revenue),
        net_income=num(m.net_income),
        net_margin_pct=num(m.net_margin),
        roe_pct=num(m.roe),
        roa_pct=num(m.roa),
        current_ratio=num(m.current_ratio),
        debt_to_equity=num(m.debt_to_equity),
        asset_turnover=num(m.asset_turnover),
        health_total=num(score.total),
        health_label=str(score.label or ""),
        altman_score=num(alt_score),
        altman_zone=str(alt_zone),
    )


def _record_key(rec: CompanyRecord) -> str:
    """Stable file stem: company + current year, filesystem-safe."""
    safe = re.sub(r'[\\/:*?"<>|]+', " ", rec.company).strip()
    safe = re.sub(r"\s+", "_", safe) or "company"
    return f"{safe}_{rec.curr_year}"


def save_record(rec: CompanyRecord) -> Path:
    """Write (or overwrite, same company+year) one record JSON."""
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    path = LIBRARY_DIR / f"{_record_key(rec)}.json"
    with _LOCK:
        path.write_text(
            json.dumps(asdict(rec), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return path


def load_records() -> list[CompanyRecord]:
    """All saved records, alphabetical by company (missing/corrupt skipped)."""
    if not LIBRARY_DIR.exists():
        return []
    records: list[CompanyRecord] = []
    for path in sorted(LIBRARY_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            records.append(
                CompanyRecord(**{k: data[k] for k in CompanyRecord.__dataclass_fields__})
            )
        except Exception:
            continue  # a corrupt file must not break the comparison screen
    return sorted(records, key=lambda r: (r.company.lower(), r.curr_year))


def clear_library() -> int:
    """Delete every record. Returns how many were removed."""
    if not LIBRARY_DIR.exists():
        return 0
    n = 0
    with _LOCK:
        for path in LIBRARY_DIR.glob("*.json"):
            try:
                path.unlink()
                n += 1
            except OSError:
                pass
    return n
