#!/usr/bin/env python3
"""
Generate a Chinese report from merged pipeline JSON and optionally send to Telegram.

Supports multiple templates (morning/evening/weekly) with different article counts.
Translates English titles to Chinese via Google Translate.

Usage:
    python3 generate-report.py --input merged.json --template morning --output report.md
    python3 generate-report.py --input merged.json --template morning --telegram --coins
"""

import json
import sys
import os
if sys.platform == "win32" and sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace"); sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import argparse
import logging
import re
import datetime as dt
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.request import urlopen, Request
from urllib.parse import quote

TIMEOUT = 25
MAX_TELEGRAM_LEN = 3900

# Template configs: (top_n per topic, ai_focus_n, github_n, hot_n)
TEMPLATES = {
    "morning": {"top_n": 3, "ai_n": 5, "gh_n": 5, "hot_n": 5, "label": "早报"},
    "evening": {"top_n": 5, "ai_n": 8, "gh_n": 8, "hot_n": 8, "label": "晚报"},
    "weekly":  {"top_n": 10, "ai_n": 15, "gh_n": 10, "hot_n": 10, "label": "周报"},
}

TOPIC_DISPLAY = {
    "llm": ("🧠", "AI / LLM"),
    "ai-agent": ("🤖", "AI Agent"),
    "crypto": ("💰", "区块链"),
    "frontier-tech": ("🔬", "前沿科技"),
}

COINS = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple"]
SYMBOL = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "binancecoin": "BNB", "ripple": "XRP"}

_translate_cache: Dict[str, str] = {}


def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    return logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def _has_chinese(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s))

def _looks_english(s: str) -> bool:
    letters = re.findall(r"[A-Za-z]", s or "")
    if not letters:
        return False
    return (len(letters) / max(len(s), 1)) > 0.35 and not _has_chinese(s)

def _get_json(url: str) -> Any:
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}

def translate_to_zh(text: str) -> str:
    if not text or not _looks_english(text):
        return text
    if text in _translate_cache:
        return _translate_cache[text]
    try:
        u = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=" + quote(text)
        data = _get_json(u)
        if isinstance(data, list) and data and isinstance(data[0], list):
            translated = "".join(seg[0] for seg in data[0] if isinstance(seg, list) and seg).strip()
            if translated:
                _translate_cache[text] = translated
                return translated
    except Exception:
        pass
    _translate_cache[text] = text
    return text


# ---------------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------------

def collect_coins() -> List[str]:
    ids = ",".join(COINS)
    data = _get_json(f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true")
    rows: List[str] = []
    if not isinstance(data, dict):
        return rows
    for coin in COINS:
        d = data.get(coin, {})
        price = d.get("usd", "n/a")
        chg = d.get("usd_24h_change")
        chg_s = "n/a" if chg is None else f"{chg:+.2f}%"
        rows.append(f"{SYMBOL[coin]} ${price} ({chg_s})")
    return rows


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------

def _get_top_articles(topic_data: Dict[str, Any], n: int) -> List[Dict[str, Any]]:
    articles = topic_data.get("articles", [])
    articles.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    return articles[:n]


def build_report(data: Dict[str, Any], template: str = "morning", include_coins: bool = False) -> str:
    cfg = TEMPLATES.get(template, TEMPLATES["morning"])
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    topics = data.get("topics", {})
    stats = data.get("output_stats", {})
    time_range = data.get("time_range", {})

    lines: List[str] = [
        f"🦞 科技新闻{cfg['label']}",
        f"时间：{now} · 共 {stats.get('total_articles', 0)} 条",
        "━━━━━━━━━━━━",
        "【1) 今日重点】",
    ]

    # Key picks: top 1 per category
    key_picks: List[str] = []
    for topic_id, (emoji, cat_name) in TOPIC_DISPLAY.items():
        topic_data = topics.get(topic_id, {})
        top = _get_top_articles(topic_data, 1)
        if top:
            title = translate_to_zh(top[0].get("title", ""))
            key_picks.append(f"{emoji} {cat_name}：{title}")
    if key_picks:
        for i, pick in enumerate(key_picks, 1):
            lines.append(f"{i}. {pick}")
    else:
        lines.append("- 本轮源更新较少")

    # Category details
    lines += ["", "━━━━━━━━━━━━", "【2) 板块明细】"]
    labels = [chr(ord("A") + i) for i in range(cfg["top_n"])]
    for idx, (topic_id, (emoji, cat_name)) in enumerate(TOPIC_DISPLAY.items(), 1):
        topic_data = topics.get(topic_id, {})
        top = _get_top_articles(topic_data, cfg["top_n"])
        lines.append(f"{idx}. {emoji} {cat_name}")
        if top:
            for i, article in enumerate(top):
                title = translate_to_zh(article.get("title", ""))
                score = article.get("quality_score", 0)
                lbl = labels[i] if i < len(labels) else str(i + 1)
                lines.append(f"   {lbl}. {title} [{score:.0f}分]")
        else:
            lines.append("   - 本轮无更新")

    # AI focus
    lines += ["", "━━━━━━━━━━━━", "【3) AI 焦点】"]
    ai_articles = []
    for tid in ("llm", "ai-agent"):
        ai_articles.extend(_get_top_articles(topics.get(tid, {}), cfg["ai_n"]))
    seen = set()
    unique_ai = []
    for a in sorted(ai_articles, key=lambda x: x.get("quality_score", 0), reverse=True):
        t = a.get("title", "")
        if t not in seen:
            seen.add(t)
            unique_ai.append(a)
    for i, article in enumerate(unique_ai[:cfg["ai_n"]], 1):
        title = translate_to_zh(article.get("title", ""))
        lines.append(f"{i}. {title}")

    # GitHub trending
    lines += ["", "━━━━━━━━━━━━", "【4) GitHub 热门项目】"]
    gh_articles = []
    for topic_data in topics.values():
        if isinstance(topic_data, dict):
            for a in topic_data.get("articles", []):
                if a.get("source_type") in ("github", "github_trending"):
                    gh_articles.append(a)
    seen_gh = set()
    unique_gh = []
    for a in sorted(gh_articles, key=lambda x: x.get("quality_score", 0), reverse=True):
        link = a.get("link", "")
        if link not in seen_gh:
            seen_gh.add(link)
            unique_gh.append(a)
    if unique_gh:
        for i, a in enumerate(unique_gh[:cfg["gh_n"]], 1):
            title = a.get("title", "")
            stars = a.get("stars", 0) or a.get("daily_stars_est", 0)
            star_str = f"（⭐{stars}）" if stars else ""
            lines.append(f"{i}. {title}{star_str}")
    else:
        lines.append("- GitHub 热门源本轮更新较少")

    # Crypto
    if include_coins:
        lines += ["", "━━━━━━━━━━━━", "【5) 代币行情】"]
        coins = collect_coins()
        if coins:
            for c in coins:
                lines.append(f"- {c}")
        else:
            lines.append("- 行情接口暂不可用")

    # Hot topics
    section_n = 6 if include_coins else 5
    lines += ["", "━━━━━━━━━━━━", f"【{section_n}) 热议话题】"]
    hot = []
    for topic_data in topics.values():
        if isinstance(topic_data, dict):
            for a in topic_data.get("articles", []):
                if a.get("multi_source") or a.get("quality_score", 0) >= 20:
                    hot.append(a)
    seen_hot = set()
    unique_hot = []
    for a in sorted(hot, key=lambda x: x.get("quality_score", 0), reverse=True):
        t = a.get("title", "")
        if t not in seen_hot:
            seen_hot.add(t)
            unique_hot.append(a)
    if unique_hot:
        for i, a in enumerate(unique_hot[:cfg["hot_n"]], 1):
            title = translate_to_zh(a.get("title", ""))
            sources = a.get("source_count", 1)
            src_str = f" [{sources}源]" if sources > 1 else ""
            lines.append(f"{i}. {title}{src_str}")
    else:
        lines.append("- 本轮无多源热议话题")

    lines += ["", "━━━━━━━━━━━━", "📊 数据来源：RSS/Twitter/GitHub/Reddit/Web"]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram(token: str, chat_id: str, text: str) -> None:
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=TIMEOUT) as resp:
        result = json.loads(resp.read().decode())
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result}")


# ---------------------------------------------------------------------------
# Markdown file output
# ---------------------------------------------------------------------------

def build_markdown(data: Dict[str, Any], template: str = "morning") -> str:
    """Generate a full Markdown report (for file output, no char limit)."""
    cfg = TEMPLATES.get(template, TEMPLATES["morning"])
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    topics = data.get("topics", {})
    stats = data.get("output_stats", {})

    lines: List[str] = [
        f"# 科技新闻{cfg['label']} - {now}",
        f"",
        f"共 {stats.get('total_articles', 0)} 条文章",
        "",
    ]

    for topic_id, (emoji, cat_name) in TOPIC_DISPLAY.items():
        topic_data = topics.get(topic_id, {})
        top = _get_top_articles(topic_data, cfg["top_n"])
        lines.append(f"## {emoji} {cat_name}")
        lines.append("")
        if top:
            for i, article in enumerate(top, 1):
                title = article.get("title", "")
                zh_title = translate_to_zh(title)
                score = article.get("quality_score", 0)
                
                # Format: 🔥score | **Title**
                lines.append(f"🔥{score:.0f} | **{zh_title}**")
                
                # Add summary from full_text or summary field
                full_text = article.get("full_text", "")
                summary = article.get("summary", "")
                
                if full_text:
                    # Use first 200 chars of full_text as summary
                    snippet = full_text[:200].strip()
                    if len(full_text) > 200:
                        snippet += "..."
                    lines.append(snippet)
                elif summary:
                    # Use existing summary
                    lines.append(summary)
                
                lines.append("")
        else:
            lines.append("- 本轮无更新")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate report from merged JSON")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Merged JSON from merge-historical.py or pipeline")
    parser.add_argument("--template", choices=list(TEMPLATES.keys()), default="morning", help="Report template")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output Markdown file")
    parser.add_argument("--telegram", action="store_true", help="Send to Telegram")
    parser.add_argument("--coins", action="store_true", help="Include crypto prices")
    parser.add_argument("--top-n", type=int, default=None, help="Override articles per topic")
    parser.add_argument("--dry-run", action="store_true", help="Print report without sending")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--force", action="store_true", help="Ignored (pipeline compat)")
    args = parser.parse_args()
    logger = setup_logging(args.verbose)

    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1

    # Override top_n if specified
    if args.top_n:
        TEMPLATES[args.template]["top_n"] = args.top_n

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Generate Markdown file if --output specified
        if args.output:
            md = build_markdown(data, args.template)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(md)
            logger.info(f"✅ Report saved to {args.output}")

        # Telegram output
        if args.telegram or args.dry_run:
            report = build_report(data, args.template, include_coins=args.coins)
            report = report[:MAX_TELEGRAM_LEN]

            if args.dry_run:
                sys.stdout.buffer.write(report.encode("utf-8", errors="replace"))
                sys.stdout.buffer.write(f"\n--- ({len(report)} chars) ---\n".encode("utf-8"))
                return 0

            token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            chat_id = os.getenv("NEWS_CHAT_ID", "").strip()
            if not token:
                logger.error("Missing TELEGRAM_BOT_TOKEN environment variable")
                return 1

            send_telegram(token, chat_id, report)
            logger.info(f"✅ Report sent to Telegram ({len(report)} chars)")

        if not args.output and not args.telegram and not args.dry_run:
            # Default: print to stdout
            report = build_report(data, args.template, include_coins=args.coins)
            sys.stdout.buffer.write(report.encode("utf-8", errors="replace"))
            sys.stdout.buffer.write(b"\n")

        return 0

    except Exception as e:
        logger.error(f"💥 Failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
