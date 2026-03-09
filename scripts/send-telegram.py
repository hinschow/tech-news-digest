#!/usr/bin/env python3
"""
Format merged pipeline output into a Telegram message and send it.

Reads the merged JSON from merge-sources.py, translates English titles
to Chinese via Google Translate, optionally appends crypto prices from
CoinGecko, and sends the report to a Telegram bot.

Usage:
    python3 send-telegram.py --input merged.json [--coins] [--verbose]

Environment:
    TELEGRAM_BOT_TOKEN  - Telegram bot token (required)
    NEWS_CHAT_ID        - Telegram chat ID (default: from env)
"""

import json
import sys
import os
if sys.platform == "win32" and sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace"); sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
import re
import argparse
import logging
import datetime as dt
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.request import urlopen, Request
from urllib.parse import quote, urlencode

TIMEOUT = 25
MAX_LEN = 3900  # Telegram message limit

# Topic ID -> display category mapping
TOPIC_DISPLAY = {
    "llm": ("🧠", "AI / LLM"),
    "ai-agent": ("🤖", "AI Agent"),
    "crypto": ("💰", "区块链"),
    "frontier-tech": ("🔬", "前沿科技"),
}

# Categories shown in "今日重点"
KEY_CATEGORIES = ["AI / LLM", "AI Agent", "区块链", "前沿科技"]

COINS = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple"]
SYMBOL = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binancecoin": "BNB",
    "ripple": "XRP",
}

_translate_cache: Dict[str, str] = {}


def setup_logging(verbose: bool) -> logging.Logger:
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
    """Translate English text to Chinese via Google Translate API."""
    if not text or not _looks_english(text):
        return text
    if text in _translate_cache:
        return _translate_cache[text]
    try:
        u = (
            "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q="
            + quote(text)
        )
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
# Crypto prices
# ---------------------------------------------------------------------------

def collect_coins() -> List[str]:
    """Fetch crypto prices from CoinGecko."""
    ids = ",".join(COINS)
    data = _get_json(
        f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
    )
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
# Report formatting
# ---------------------------------------------------------------------------

def load_merged(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_top_articles(topic_data: Dict[str, Any], n: int = 3) -> List[Dict[str, Any]]:
    """Get top N articles from a topic, sorted by quality_score."""
    articles = topic_data.get("articles", [])
    articles.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    return articles[:n]


def build_report(data: Dict[str, Any], include_coins: bool = True) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    topics = data.get("topics", {})
    stats = data.get("output_stats", {})

    lines: List[str] = [
        "🦞 科技新闻简报",
        f"时间：{now} · 共 {stats.get('total_articles', 0)} 条",
        "━━━━━━━━━━━━",
        "【1) 今日重点】",
    ]

    # Key picks: top 1 from each category
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

    # Category details: top 3 per topic
    lines += ["", "━━━━━━━━━━━━", "【2) 板块明细】"]
    labels = ["A", "B", "C"]
    for idx, (topic_id, (emoji, cat_name)) in enumerate(TOPIC_DISPLAY.items(), 1):
        topic_data = topics.get(topic_id, {})
        top = _get_top_articles(topic_data, 3)
        lines.append(f"{idx}. {emoji} {cat_name}")
        if top:
            for i, article in enumerate(top):
                title = translate_to_zh(article.get("title", ""))
                score = article.get("quality_score", 0)
                lines.append(f"   {labels[i]}. {title} [{score:.0f}分]")
        else:
            lines.append(f"   - 本轮无更新")

    # AI focus: combine llm + ai-agent top articles
    lines += ["", "━━━━━━━━━━━━", "【3) AI 焦点】"]
    ai_articles = []
    for tid in ("llm", "ai-agent"):
        ai_articles.extend(_get_top_articles(topics.get(tid, {}), 4))
    # Deduplicate by title and re-sort
    seen_titles = set()
    unique_ai = []
    for a in sorted(ai_articles, key=lambda x: x.get("quality_score", 0), reverse=True):
        t = a.get("title", "")
        if t not in seen_titles:
            seen_titles.add(t)
            unique_ai.append(a)
    for i, article in enumerate(unique_ai[:5], 1):
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
    # Deduplicate
    seen = set()
    unique_gh = []
    for a in sorted(gh_articles, key=lambda x: x.get("quality_score", 0), reverse=True):
        link = a.get("link", "")
        if link not in seen:
            seen.add(link)
            unique_gh.append(a)
    if unique_gh:
        for i, a in enumerate(unique_gh[:5], 1):
            title = a.get("title", "")
            stars = a.get("stars", 0) or a.get("daily_stars_est", 0)
            star_str = f"（⭐{stars}）" if stars else ""
            lines.append(f"{i}. {title}{star_str}")
    else:
        lines.append("- GitHub 热门源本轮更新较少")

    # Crypto prices
    if include_coins:
        lines += ["", "━━━━━━━━━━━━", "【5) 代币行情】"]
        coins = collect_coins()
        if coins:
            for c in coins:
                lines.append(f"- {c}")
        else:
            lines.append("- 行情接口暂不可用")

    # Hot topics: multi-source or high engagement articles
    lines += ["", "━━━━━━━━━━━━", "【6) 热议话题】"]
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
        for i, a in enumerate(unique_hot[:5], 1):
            title = translate_to_zh(a.get("title", ""))
            sources = a.get("source_count", 1)
            src_str = f" [{sources}源]" if sources > 1 else ""
            lines.append(f"{i}. {title}{src_str}")
    else:
        lines.append("- 本轮无多源热议话题")

    lines += ["", "━━━━━━━━━━━━", "📊 数据来源：RSS/Twitter/GitHub/Reddit/Web"]

    return "\n".join(lines)[:MAX_LEN]


# ---------------------------------------------------------------------------
# Telegram sending
# ---------------------------------------------------------------------------

def send_telegram(token: str, chat_id: str, text: str) -> None:
    """Send message to Telegram bot."""
    import urllib.request
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=TIMEOUT) as resp:
        result = json.loads(resp.read().decode())
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result}")


def main():
    parser = argparse.ArgumentParser(description="Send pipeline output to Telegram")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Merged JSON from pipeline")
    parser.add_argument("--coins", action="store_true", help="Include crypto prices")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print report without sending")
    args = parser.parse_args()
    logger = setup_logging(args.verbose)

    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("NEWS_CHAT_ID", "").strip()

    if not args.dry_run and not token:
        logger.error("Missing TELEGRAM_BOT_TOKEN environment variable")
        return 1

    try:
        data = load_merged(args.input)
        report = build_report(data, include_coins=args.coins)

        if args.dry_run:
            sys.stdout.buffer.write(report.encode("utf-8", errors="replace"))
            sys.stdout.buffer.write(f"\n--- ({len(report)} chars) ---\n".encode("utf-8"))
            return 0

        send_telegram(token, chat_id, report)
        logger.info(f"✅ Report sent to Telegram ({len(report)} chars)")
        return 0

    except Exception as e:
        logger.error(f"💥 Failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
