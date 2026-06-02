#!/usr/bin/env python
"""Generate docs/FEATURE-METRICS.md from docs/_features.yaml + live source stats.

Usage:
    python scripts/build_feature_metrics.py            # write the file
    python scripts/build_feature_metrics.py --check    # fail if file would change

Sources of truth:
  - Feature list:        docs/_features.yaml (hand-maintained)
  - LOC per module:      walk src/substrate/<mod>/*.py
  - Public symbols:      __all__ in __init__.py modules
  - Friction examples:   examples/before/*.py and examples/after/*.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "substrate"
DOCS = REPO / "docs"
EXAMPLES = REPO / "examples"
FEATURES_FILE = DOCS / "_features.yaml"
OUTPUT_FILE = DOCS / "FEATURE-METRICS.md"


# ─── module statistics ─────────────────────────────────────────────────────


MODULE_BUCKETS = [
    ("_http", "_http"),
    ("models", "models"),
    ("resources", "resources"),
    ("workloads", "workloads"),
    ("cli", "cli"),
    ("declarative", "declarative"),
    ("client", "client.py"),
    ("config", "config.py"),
]


def loc_of(path: Path) -> int:
    if path.is_file():
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    if path.is_dir():
        total = 0
        for p in path.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            total += loc_of(p)
        return total
    return 0


def public_symbols_count(path: Path) -> int:
    """Count names in __all__ of __init__.py files under `path`."""
    count = 0
    init_files = list(path.rglob("__init__.py")) if path.is_dir() else [
        path.parent / "__init__.py"
    ]
    for f in init_files:
        if not f.exists():
            continue
        text = f.read_text()
        if "__all__" not in text:
            continue
        # crude but adequate — count quoted strings in the __all__ block
        start = text.find("__all__")
        block = text[start : start + 2000]
        end = block.find("]")
        if end > 0:
            block = block[:end]
        count += block.count('"') // 2 + block.count("'") // 2
    return count


def module_stats() -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for name, rel in MODULE_BUCKETS:
        p = SRC / rel
        stats.append(
            {
                "module": name,
                "loc": loc_of(p),
                "public": public_symbols_count(p) if p.is_dir() else 0,
            }
        )
    total_loc = sum(s["loc"] for s in stats)
    total_public = sum(s["public"] for s in stats)
    stats.append({"module": "Total", "loc": total_loc, "public": total_public})
    return stats


# ─── before/after friction examples ────────────────────────────────────────


def friction_table() -> list[dict[str, Any]]:
    before_dir = EXAMPLES / "before"
    after_dir = EXAMPLES / "after"
    if not before_dir.exists() or not after_dir.exists():
        return []
    rows = []
    for before_file in sorted(before_dir.glob("*.py")):
        after_file = after_dir / before_file.name
        before_loc = loc_of(before_file)
        after_loc = loc_of(after_file) if after_file.exists() else None
        rows.append(
            {
                "task": before_file.stem.replace("_", " "),
                "before": str(before_loc),
                "after": str(after_loc) if after_loc is not None else "n/a",
            }
        )
    return rows


# ─── render ────────────────────────────────────────────────────────────────


STATUS_RANK = {"stable": 0, "preview": 1, "optional": 2, "api-blocked": 3, "missing": 4}


def render_features_table(features: list[dict[str, Any]]) -> str:
    header = (
        "| Feature | Status | Layer | Python | Manifest | CLI | Since |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for f in sorted(features, key=lambda x: (STATUS_RANK.get(x["status"], 99), x["name"])):
        rows.append(
            "| {name} | `{status}` | {layer} | `{python}` | `{manifest}` | `{cli}` | {since} |".format(
                **{k: f.get(k, "—") for k in ("name", "status", "layer", "python", "manifest", "cli", "since")}
            )
        )
    return header + "\n".join(rows)


def render_module_table(stats: list[dict[str, Any]]) -> str:
    header = (
        "| Module | LOC | Public API count |\n"
        "|---|---:|---:|\n"
    )
    rows = []
    for s in stats:
        rows.append("| {module} | {loc} | {public} |".format(**s))
    return header + "\n".join(rows)


def render_friction(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "_No before/after examples found yet — add files in "
            "`examples/before/` and `examples/after/` to populate this section._"
        )
    header = "| Task | Before (LOC) | After (LOC) |\n|---|---:|---:|\n"
    body = "\n".join(
        "| {task} | {before} | **{after}** |".format(**r) for r in rows
    )
    return header + body


def render_report(features: list[dict[str, Any]]) -> str:
    stats = module_stats()
    total = next(s for s in stats if s["module"] == "Total")
    status_counts: dict[str, int] = {}
    for f in features:
        status_counts[f["status"]] = status_counts.get(f["status"], 0) + 1
    by_status_line = ", ".join(
        f"{c} {s}" for s, c in sorted(status_counts.items(), key=lambda kv: STATUS_RANK.get(kv[0], 99))
    )
    today = datetime.now(timezone.utc).date().isoformat()
    return f"""# Substrate SDK — Feature Metrics

_Auto-generated by `scripts/build_feature_metrics.py` on {today}._

## 1. Executive summary

| Metric | Value |
|---|---:|
| Total source LOC | {total['loc']} |
| Public API symbols (sum of `__all__` across modules) | {total['public']} |
| Feature rows in catalogue | {len(features)} |
| Feature mix | {by_status_line} |

To launch a GPU you write:
- **1 line of Python**: `Substrate().launch(name="x", gpu="A100", image="...")`
- **1 manifest**: `substrate apply substrate.yaml`
- **1 CLI command**: `substrate instance launch --gpu A100 --name x`

## 2. Capability matrix

{render_features_table(features)}

## 3. Code health (per module)

{render_module_table(stats)}

> Source: live `wc -l` over `src/substrate/`, and `__all__` counts in each `__init__.py`.

## 4. Adoption / friction (before vs after)

{render_friction(friction_table())}

## 5. Open API dependencies (unchanged in v0.2)

1. Non-Docker `launch_configuration` shape — `workload.type: boot_script` stays `preview`.
2. Instance logs API — no SDK log streaming until the API exposes an endpoint.
3. Webhooks / event streaming — completion detection stays out-of-band until the API ships events.
4. Server-side `max_runtime` / `max_spend` enforcement — billing stops on `destroy` only today.
5. Instance metadata service — not used yet.
"""


# ─── main ──────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Exit nonzero if file would change.")
    args = parser.parse_args()

    if not FEATURES_FILE.exists():
        print(f"missing {FEATURES_FILE}", file=sys.stderr)
        return 2

    data = yaml.safe_load(FEATURES_FILE.read_text())
    features = data.get("features", [])
    output = render_report(features)

    if args.check:
        if not OUTPUT_FILE.exists() or OUTPUT_FILE.read_text() != output:
            print(f"{OUTPUT_FILE} is out of date. Run scripts/build_feature_metrics.py.", file=sys.stderr)
            return 1
        return 0

    OUTPUT_FILE.write_text(output)
    print(f"wrote {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
