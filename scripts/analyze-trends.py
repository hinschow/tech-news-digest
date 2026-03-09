#!/usr/bin/env python3
"""
Analyze historical data for trends, keyword frequency, and topic heatmaps.

Reads archived raw-data JSON files and produces trend analysis.

Usage:
    python3 analyze-trends.py --input-dir archive/raw-data --keyword "DeepSeek" --days 7 --output trend.json
    python3 analyze-trends.py --input-dir archive/raw-data --days 30 --top-keywords 20 --output overview.json
"""

import json
import sys
import os
if sys.platform == "win32" and sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace"); sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import argparse
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger(__name__)


def parse_file_datetime(filename: str) -> Optional[datetime]:
    m = re.match(r"(\d{4}-\d{2}-\d{2}-\d{2})\.json$", filename)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d-%H").replace(tzinfo=timezone.utc)
    m = re.match(r"(\d{4}-\d{2}-\d{2})\.json$", filename)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return None


def load_all_articles(input_dir: Path, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
    """Load all articles from files in the time range."""
    articles = []
    for f in sorted(input_dir.glob("*.json")):
        fdt = parse_file_datetime(f.name)
        if fdt is None or fdt < start_dt or fdt > end_dt:
            continue
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            continue

        topics = data.get("topics", {})
        if isinstance(topics, dict):
            for topic_id, topic_data in topics.items():
                if isinstance(topic_data, dict):
                    for a in topic_data.get("articles", []):
                        a["_file_date"] = fdt.strftime("%Y-%m-%d")
                        a.setdefault("_topic", topic_id)
                        articles.append(a)
                elif isinstance(topic_data, list):
                    for a in topic_data:
                        a["_file_date"] = fdt.strftime("%Y-%m-%d")
                        a.setdefault("_topic", topic_id)
                        articles.append(a)
    return articles


def keyword_trend(articles: List[Dict[str, Any]], keyword: str) -> Dict[str, Any]:
    """Analyze mention frequency of a keyword over time."""
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    daily: Dict[str, List[Dict]] = defaultdict(list)

    for a in articles:
        title = a.get("title", "")
        text = a.get("full_text", "")
        if pattern.search(title) or pattern.search(text):
            date = a.get("_file_date", "unknown")
            daily[date].append(a)

    daily_mentions = []
    for date in sorted(daily.keys()):
        items = daily[date]
        daily_mentions.append({
            "date": date,
            "count": len(items),
            "top_title": max(items, key=lambda x: x.get("quality_score", 0)).get("title", ""),
        })

    # Top articles mentioning this keyword
    all_matched = []
    for items in daily.values():
        all_matched.extend(items)
    # Dedup by link
    seen = set()
    unique = []
    for a in sorted(all_matched, key=lambda x: -x.get("quality_score", 0)):
        link = a.get("link", "")
        if link and link not in seen:
            seen.add(link)
            unique.append(a)

    top_articles = [
        {
            "title": a.get("title", ""),
            "link": a.get("link", ""),
            "date": a.get("_file_date", ""),
            "quality_score": a.get("quality_score", 0),
            "source_type": a.get("source_type", ""),
        }
        for a in unique[:10]
    ]

    return {
        "keyword": keyword,
        "total_mentions": sum(d["count"] for d in daily_mentions),
        "daily_mentions": daily_mentions,
        "top_articles": top_articles,
    }


def topic_heatmap(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate daily article counts per topic."""
    daily_topic: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for a in articles:
        date = a.get("_file_date", "unknown")
        topic = a.get("_topic", "uncategorized")
        daily_topic[date][topic] += 1

    heatmap = []
    for date in sorted(daily_topic.keys()):
        entry = {"date": date}
        entry.update(daily_topic[date])
        heatmap.append(entry)

    return {"daily_topic_counts": heatmap}


def top_keywords_analysis(articles: List[Dict[str, Any]], top_n: int = 20) -> List[Dict[str, Any]]:
    """Find the most frequently mentioned terms across all articles."""
    # Common stop words to exclude
    stop = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "and", "or", "but", "nor", "not", "so", "yet", "both", "either",
        "neither", "each", "every", "all", "any", "few", "more", "most",
        "other", "some", "such", "no", "only", "own", "same", "than",
        "too", "very", "just", "because", "as", "until", "while", "of",
        "at", "by", "for", "with", "about", "against", "between", "through",
        "during", "before", "after", "above", "below", "to", "from", "up",
        "down", "in", "out", "on", "off", "over", "under", "again",
        "further", "then", "once", "here", "there", "when", "where", "why",
        "how", "this", "that", "these", "those", "i", "me", "my", "we",
        "our", "you", "your", "he", "him", "his", "she", "her", "it",
        "its", "they", "them", "their", "what", "which", "who", "whom",
        "new", "now", "get", "one", "two", "also", "use", "using", "used",
        "via", "like", "into", "make", "first", "says", "said",
    }

    word_counter: Counter = Counter()
    for a in articles:
        title = a.get("title", "")
        words = re.findall(r"[A-Za-z][A-Za-z0-9.#+\-]{2,}", title)
        for w in words:
            wl = w.lower()
            if wl not in stop and len(wl) >= 3:
                word_counter[w] += 1

    return [{"keyword": w, "count": c} for w, c in word_counter.most_common(top_n)]


def source_stats(articles: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count articles by source_type."""
    counter: Counter = Counter()
    for a in articles:
        counter[a.get("source_type", "unknown")] += 1
    return dict(counter.most_common())


def main():
    parser = argparse.ArgumentParser(description="Analyze historical news trends")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory with raw-data JSON files")
    parser.add_argument("--days", type=int, default=7, help="Analysis window in days (default 7)")
    parser.add_argument("--keyword", type=str, default=None, help="Track a specific keyword")
    parser.add_argument("--top-keywords", type=int, default=20, help="Show top N keywords")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output JSON (default: stdout)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    logger = setup_logging(args.verbose)

    if not args.input_dir.exists():
        logger.error(f"Input directory not found: {args.input_dir}")
        return 1

    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=args.days)
    end_dt = now

    logger.info(f"Loading articles from {args.days} days...")
    articles = load_all_articles(args.input_dir, start_dt, end_dt)

    if not articles:
        logger.warning("No articles found in the specified range")
        return 0

    # Dedup by link for analysis
    seen = set()
    unique = []
    for a in articles:
        link = a.get("link", "")
        if link and link not in seen:
            seen.add(link)
            unique.append(a)

    logger.info(f"Loaded {len(articles)} total, {len(unique)} unique articles")

    result: Dict[str, Any] = {
        "generated": now.isoformat(),
        "time_range": {"start": start_dt.strftime("%Y-%m-%d"), "end": end_dt.strftime("%Y-%m-%d")},
        "total_articles": len(unique),
        "source_distribution": source_stats(unique),
    }

    # Keyword tracking
    if args.keyword:
        result["keyword_trend"] = keyword_trend(articles, args.keyword)

    # Topic heatmap
    result["topic_heatmap"] = topic_heatmap(articles)

    # Top keywords
    result["top_keywords"] = top_keywords_analysis(unique, args.top_keywords)

    # Output
    json_out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_out)
        logger.info(f"✅ Trend analysis saved to {args.output}")
    else:
        sys.stdout.buffer.write(json_out.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")

    # Print summary
    if args.keyword:
        kt = result["keyword_trend"]
        logger.info(f"Keyword '{args.keyword}': {kt['total_mentions']} mentions over {args.days} days")

    logger.info(f"Top keywords: {', '.join(k['keyword'] for k in result['top_keywords'][:10])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
