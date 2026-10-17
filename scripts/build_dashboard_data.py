#!/usr/bin/env python3
"""Build the STMA dashboard snapshot from sentiment.db without any AI/API calls.

The source database is always opened in SQLite read-only mode.  The generated
JSON is a disposable presentation snapshot; sentiment.db remains the canonical
source of truth.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


THEMES = (
    "inflation",
    "fed",
    "consumer",
    "energy",
    "ai",
    "semiconductor",
    "housing",
    "china",
    "tariffs",
    "geopolitics",
)

CONFIDENCE_WEIGHT = {"low": 1, "medium": 2, "high": 3}


def connect_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Database not found: {resolved}")
    con = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def rows_as_dicts(con: sqlite3.Connection, query: str) -> list[dict]:
    return [dict(row) for row in con.execute(query).fetchall()]


def round_or_none(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in xs)
        * sum((y - mean_y) ** 2 for y in ys)
    )
    return None if denominator == 0 else numerator / denominator


def validate_observations(rows: list[dict]) -> list[str]:
    issues: list[str] = []
    by_date: dict[str, list[dict]] = defaultdict(list)
    keys: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        by_date[row["pub_date"]].append(row)
        keys[(row["pub_date"], row["theme"], row["taxonomy_version"])] += 1
        not_mentioned = row["assessment"] == "not_mentioned"
        if not_mentioned and not (
            row["score"] is None
            and row["evidence_count"] == 0
            and row["confidence"] == "low"
        ):
            issues.append(f"{row['pub_date']}/{row['theme']}: invalid not_mentioned row")
        if not not_mentioned and row["score"] is None:
            issues.append(f"{row['pub_date']}/{row['theme']}: mentioned row has null score")
    for pub_date, day_rows in by_date.items():
        if len(day_rows) != len(THEMES) or {row["theme"] for row in day_rows} != set(THEMES):
            issues.append(f"{pub_date}: expected exactly {len(THEMES)} canonical themes")
    if any(count > 1 for count in keys.values()):
        issues.append("duplicate canonical observation key")
    return sorted(set(issues))


def build_theme_summary(rows: list[dict], publication_days: int) -> list[dict]:
    output = []
    for theme in THEMES:
        subset = [row for row in rows if row["theme"] == theme]
        observed = [row for row in subset if row["score"] is not None]
        scores = [float(row["score"]) for row in observed]
        assessments = Counter(row["assessment"] for row in subset)
        confidence = Counter(row["confidence"] for row in observed)
        output.append(
            {
                "theme": theme,
                "publication_days": publication_days,
                "observed_days": len(observed),
                "coverage_pct": round(100 * len(observed) / publication_days, 1)
                if publication_days
                else 0,
                "mean_score": round_or_none(statistics.mean(scores) if scores else None, 3),
                "median_score": round_or_none(statistics.median(scores) if scores else None, 3),
                "score_stdev": round_or_none(
                    statistics.stdev(scores) if len(scores) > 1 else None, 3
                ),
                "mean_abs_score": round_or_none(
                    statistics.mean(abs(score) for score in scores) if scores else None, 3
                ),
                "positive_days": assessments["positive"],
                "negative_days": assessments["negative"],
                "neutral_days": assessments["neutral"],
                "mixed_days": assessments["mixed"],
                "not_mentioned_days": assessments["not_mentioned"],
                "high_confidence_days": confidence["high"],
                "evidence_total": sum(row["evidence_count"] for row in observed),
            }
        )
    return output


def build_daily_breadth(rows: list[dict]) -> list[dict]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_date[row["pub_date"]].append(row)
    output = []
    for pub_date in sorted(by_date):
        observed = [row for row in by_date[pub_date] if row["score"] is not None]
        scores = [float(row["score"]) for row in observed]
        output.append(
            {
                "date": pub_date,
                "mean_score": round_or_none(statistics.mean(scores) if scores else None, 3),
                "observed_themes": len(observed),
                "coverage_pct": round(100 * len(observed) / len(THEMES), 1),
                "positive": sum(score > 0 for score in scores),
                "negative": sum(score < 0 for score in scores),
                "neutral": sum(score == 0 for score in scores),
                "evidence_total": sum(row["evidence_count"] for row in observed),
                "confidence_points": sum(
                    CONFIDENCE_WEIGHT.get(row["confidence"], 0) for row in observed
                ),
            }
        )
    return output


def build_correlations(rows: list[dict]) -> list[dict]:
    scores: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        if row["score"] is not None:
            scores[row["theme"]][row["pub_date"]] = float(row["score"])
    output = []
    for left in THEMES:
        for right in THEMES:
            common_dates = sorted(set(scores[left]) & set(scores[right]))
            pairs = [(scores[left][date], scores[right][date]) for date in common_dates]
            value = 1.0 if left == right and pairs else pearson(pairs)
            output.append(
                {
                    "left": left,
                    "right": right,
                    "value": round_or_none(value, 3),
                    "n": len(pairs),
                }
            )
    return output


def build_snapshot(db_path: Path) -> dict:
    with closing(connect_read_only(db_path)) as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        observations = rows_as_dicts(
            con,
            """SELECT pub_date, theme, score, assessment, confidence,
                      evidence_count, reason, taxonomy_version, prompt_version,
                      actual_model, evidence_refs_json
               FROM macro_observations
               WHERE taxonomy_version='macro_v1'
               ORDER BY pub_date, theme""",
        )
        summaries = rows_as_dicts(
            con,
            """SELECT pub_date AS date, summary, overall_score, actual_model
               FROM macro_daily_summary
               WHERE taxonomy_version='macro_v1'
               ORDER BY pub_date""",
        )
        quality = rows_as_dicts(
            con,
            """SELECT pub_date AS date, status, article_count,
                      articles_per_kept_page, median_words, short_article_count,
                      empty_headline_count, duplicate_text_hash_count, issues_json
               FROM extraction_quality
               ORDER BY pub_date""",
        )
        ingestions = rows_as_dicts(
            con,
            """SELECT pub_date AS date, file_name, pages_total, pages_kept,
                      extraction_version
               FROM pdf_ingestions
               ORDER BY pub_date""",
        )
        run_log = rows_as_dicts(
            con,
            """SELECT run_date AS date, status, pages_processed,
                      articles_extracted, portfolio_hits, tokens_used,
                      error_detail, created_at
               FROM run_log
               ORDER BY run_date, id""",
        )
    validation_issues = validate_observations(observations)
    dates = sorted({row["pub_date"] for row in observations})
    observed_cells = sum(row["score"] is not None for row in observations)
    for row in observations:
        try:
            row["evidence_refs"] = json.loads(row.pop("evidence_refs_json") or "[]")
        except json.JSONDecodeError:
            row["evidence_refs"] = []
            validation_issues.append(
                f"{row['pub_date']}/{row['theme']}: invalid evidence_refs_json"
            )
    for row in quality:
        try:
            row["issues"] = json.loads(row.pop("issues_json") or "[]")
        except json.JSONDecodeError:
            row["issues"] = ["invalid issues_json"]

    latest_runs: dict[str, dict] = {}
    for row in run_log:
        latest_runs[row["date"]] = row

    models = sorted({row["actual_model"] for row in observations if row["actual_model"]})
    prompts = sorted({row["prompt_version"] for row in observations})
    taxonomies = sorted({row["taxonomy_version"] for row in observations})
    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "database_name": db_path.name,
            "integrity_check": integrity,
            "dataset_status": "ok" if integrity == "ok" and not validation_issues else "warning",
            "validation_issues": validation_issues,
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "publication_days": len(dates),
            "canonical_observations": len(observations),
            "observed_cells": observed_cells,
            "coverage_pct": round(100 * observed_cells / len(observations), 1)
            if observations
            else 0,
            "taxonomies": taxonomies,
            "prompts": prompts,
            "models": models,
        },
        "themes": list(THEMES),
        "dates": dates,
        "observations": observations,
        "theme_summary": build_theme_summary(observations, len(dates)),
        "daily_breadth": build_daily_breadth(observations),
        "correlations": build_correlations(observations),
        "daily_summaries": summaries,
        "extraction_quality": quality,
        "ingestions": ingestions,
        "latest_runs": [latest_runs[date] for date in sorted(latest_runs)],
        "methodology": {
            "missing_policy": "not_mentioned is null and is never converted to zero",
            "breadth": "unweighted mean across mentioned themes on each publication date",
            "correlation": "Pearson correlation on pairwise overlapping non-null dates; n is always shown",
            "portfolio_policy": "signals are excluded from the macro dashboard and all calculations",
            "api_policy": "snapshot generation uses local SQLite only; no AI or external API call",
        },
    }


def main() -> int:
    dashboard_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=dashboard_dir.parents[1] / "data" / "sentiment.db",
        help="Path to the canonical STMA SQLite database",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=dashboard_dir / "public" / "data" / "dashboard.json",
        help="Generated dashboard snapshot",
    )
    args = parser.parse_args()
    snapshot = build_snapshot(args.db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    meta = snapshot["meta"]
    print(
        f"Dashboard snapshot: {meta['publication_days']} days, "
        f"{meta['canonical_observations']} observations, status={meta['dataset_status']}"
    )
    print(f"Output: {args.output.resolve()}")
    return 0 if meta["dataset_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
