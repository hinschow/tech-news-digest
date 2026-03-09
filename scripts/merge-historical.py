#!/usr/bin/env python3
"""
Merge historical raw-data JSON files into a single deduplicated dataset.

Reads hourly pipeline outputs from archive/raw-data/, merges all articles,
deduplicates by link (keeping highest quality_score), and preserves full_text.

Usage:
    python3 merge-historical.py --input-dir archive/raw-data --hours 24 --output merged.json
    python3 merge-historical.py --input-dir archive/raw-data --today-only --output merged.json
    python3 merge-historical.py --input-dir archive/raw-data --start-date 2026-03-01 --end-date 2026-03-10 --output merged.json
"""

import json
import sys
import os
if sys.platform == "win32" and sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace"); sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import argparse
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger(__name__)


def parse_file_datetime(filename: str) -> Optional[datetime]:
    """Extract datetime from filename like '2026-03-10-08.json'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2}-\d{2})\.json$", filename)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d-%H").replace(tzinfo=timezone.utc)
    # Also support 'YYYY-MM-DD.json' format
    m = re.match(r"(\d{4}-\d{2}-\d{2})\.json$", filename)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return None


def find_files_in_range(
    input_dir: Path,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
) -> List[Path]:
    """Find JSON files in input_dir within the given time range."""
    files = []
    for f in sorted(input_dir.glob("*.json")):
        fdt = parse_file_datetime(f.name)
        if fdt is None:
            continue
        if start_dt and fdt < start_dt:
            continue
        if end_dt and fdt > end_dt:
            continue
        files.append(f)
    return files


def load_articles_from_file(path: Path) -> List[Dict[str, Any]]:
    """Extract all articles from a pipeline output JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logging.warning(f"Skipping {path}: {e}")
        return []

    articles = []
    topics = data.get("topics", {})
    if isinstance(topics, dict):
        for topic_id, topic_data in topics.items():
            if isinstance(topic_data, dict):
                for a in topic_data.get("articles", []):
                    a.setdefault("_topic", topic_id)
                    a.setdefault("_source_file", path.name)
                    articles.append(a)
            elif isinstance(topic_data, list):
                for a in topic_data:
                    a.setdefault("_topic", topic_id)
                    a.setdefault("_source_file", path.name)
                    articles.append(a)
    return articles


def merge_and_dedup(all_articles: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Deduplicate articles by link, keeping the one with highest quality_score.
    Preserves full_text from any version that has it."""
    by_link: Dict[str, Dict[str, Any]] = {}

    for a in all_articles:
        link = a.get("link", "")
        if not link:
            continue

        existing = by_link.get(link)
        if existing is None:
            by_link[link] = a
        else:
            # Keep the version with higher quality_score
            new_score = a.get("quality_score", 0)
            old_score = existing.get("quality_score", 0)
            # Preserve full_text from whichever version has it
            full_text = existing.get("full_text") or a.get("full_text")
            if new_score > old_score:
                by_link[link] = a
            # Ensure full_text is preserved
            if full_text:
                by_link[link]["full_text"] = full_text
                by_link[link].setdefault("full_text_method", a.get("full_text_method") or existing.get("full_text_method"))

            # Merge topic lists
            topics_old = set(existing.get("topics", []))
            topics_new = set(a.get("topics", []))
            by_link[link]["topics"] = list(topics_old | topics_new)

    return by_link


def group_by_topic(articles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group articles by their primary topic."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for a in articles:
        topic = a.get("_topic", "uncategorized")
        groups.setdefault(topic, []).append(a)
    # Sort each group by quality_score desc
    for topic in groups:
        groups[topic].sort(key=lambda x: -x.get("quality_score", 0))
    return groups


def main():
    parser = argparse.ArgumentParser(description="Merge historical raw-data files")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory with raw-data JSON files")
    parser.add_argument("--hours", type=int, default=None, help="Time window: last N hours from now")
    parser.add_argument("--today-only", action="store_true", help="Only include today's files")
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Output merged JSON")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--force", action="store_true", help="Ignored (pipeline compat)")
    args = parser.parse_args()
    logger = setup_logging(args.verbose)

    if not args.input_dir.exists():
        logger.error(f"Input directory not found: {args.input_dir}")
        return 1

    # Determine time range
    now = datetime.now(timezone.utc)
    start_dt = None
    end_dt = None

    if args.hours:
        start_dt = now - timedelta(hours=args.hours)
        end_dt = now
    elif args.today_only:
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now
    elif args.start_date:
        start_dt = datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.end_date:
            end_dt = datetime.strptime(args.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        else:
            end_dt = now

    files = find_files_in_range(args.input_dir, start_dt, end_dt)
    if not files:
        logger.warning("No files found in the specified range")
        # Write empty output
        output = {
            "generated": now.isoformat(),
            "time_range": {"start": str(start_dt), "end": str(end_dt)},
            "input_files": [],
            "total_input_articles": 0,
            "total_output_articles": 0,
            "topics": {},
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return 0

    logger.info(f"Found {len(files)} files in range")

    # Load all articles
    all_articles = []
    for fp in files:
        articles = load_articles_from_file(fp)
        logger.debug(f"  {fp.name}: {len(articles)} articles")
        all_articles.extend(articles)

    total_input = len(all_articles)
    logger.info(f"Total input articles: {total_input}")

    # Deduplicate
    deduped = merge_and_dedup(all_articles)
    unique_articles = list(deduped.values())
    unique_articles.sort(key=lambda x: -x.get("quality_score", 0))

    # Group by topic
    topic_groups = group_by_topic(unique_articles)

    # Clean internal fields
    for a in unique_articles:
        a.pop("_topic", None)
        a.pop("_source_file", None)

    output = {
        "generated": now.isoformat(),
        "time_range": {
            "start": start_dt.isoformat() if start_dt else None,
            "end": end_dt.isoformat() if end_dt else None,
        },
        "input_files": [f.name for f in files],
        "total_input_articles": total_input,
        "total_output_articles": len(unique_articles),
        "output_stats": {
            "total_articles": len(unique_articles),
            "topics_count": len(topic_groups),
            "topic_distribution": {t: len(a) for t, a in topic_groups.items()},
        },
        "topics": {
            topic: {
                "count": len(articles),
                "articles": articles,
            }
            for topic, articles in topic_groups.items()
        },
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"✅ Merged: {total_input} → {len(unique_articles)} articles across {len(topic_groups)} topics")
    logger.info(f"   Files: {files[0].name} .. {files[-1].name}")
    enriched = sum(1 for a in unique_articles if a.get("full_text"))
    logger.info(f"   With full text: {enriched}")
    logger.info(f"   Output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
