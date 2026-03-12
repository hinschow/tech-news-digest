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
    "morning": {"top_n": 15, "ai_n": 15, "gh_n": 12, "hot_n": 15, "label": "早报"},
    "evening": {"top_n": 20, "ai_n": 20, "gh_n": 15, "hot_n": 20, "label": "晚报"},
    "weekly":  {"top_n": 25, "ai_n": 30, "gh_n": 20, "hot_n": 25, "label": "周报"},
}

TOPIC_DISPLAY = {
    "llm": ("🧠", "AI / LLM"),
    "ai-agent": ("🤖", "AI Agent"),
    "crypto": ("💰", "区块链"),
    "frontier-tech": ("🔬", "前沿科技"),
    "international-news": ("🌍", "国际新闻"),
    "china-news": ("🇨🇳", "国内新闻"),
    "military-defense": ("⚔️", "军事国防"),
}

COINS = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple", "dogecoin"]
SYMBOL = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "binancecoin": "BNB", "ripple": "XRP", "dogecoin": "DOGE"}

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
    """Fetch coin prices with CNY conversion, openclaw-sync style."""
    ids = ",".join(COINS)
    data = _get_json(f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true")
    rows: List[str] = []
    if not isinstance(data, dict):
        return rows
    # Get CNY rate
    rate_data = _get_json("https://api.exchangerate-api.com/v4/latest/USD")
    cny_rate = 7.25
    if isinstance(rate_data, dict) and "rates" in rate_data:
        cny_rate = rate_data["rates"].get("CNY", 7.25)
    for coin in COINS:
        d = data.get(coin, {})
        price = d.get("usd")
        if price is None:
            continue
        chg = d.get("usd_24h_change")
        arrow = "🟢" if (chg or 0) >= 0 else "🔴"
        chg_s = "--" if chg is None else f"{chg:+.2f}%"
        cny = price * cny_rate
        if price >= 1:
            rows.append(f"{arrow} {SYMBOL[coin]} ${price:,.2f} / ¥{cny:,.0f} ({chg_s})")
        else:
            rows.append(f"{arrow} {SYMBOL[coin]} ${price:.4f} / ¥{cny:.2f} ({chg_s})")
    # Gold price via CoinGecko BTC/XAU
    try:
        xau_data = _get_json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,xau")
        if isinstance(xau_data, dict) and "bitcoin" in xau_data:
            btc_usd = xau_data["bitcoin"].get("usd", 0)
            btc_xau = xau_data["bitcoin"].get("xau", 0)
            if btc_xau and btc_usd:
                gold = btc_usd / btc_xau
                rows.append(f"🥇 黄金 ${gold:,.0f}/oz / ¥{gold * cny_rate:,.0f}/oz")
    except Exception:
        pass
    rows.append(f"💱 汇率 1 USD = ¥{cny_rate:.2f}")
    return rows


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------

def _is_valid_title(title: str) -> bool:
    """Check if title is valid (not too short, not just emojis/symbols)"""
    if not title or len(title) < 5:
        return False
    
    # Reject obvious spam/profanity and low-quality patterns
    bad_patterns = [
        '这个小屎', 'this little shit', '😭😭😭', '🤣🤣🤣',
        '我累了', '可笑的是', '确实有人', '吸一口气',
        'i\'m tired', 'ridiculous that', 'literally someone'
    ]
    title_lower = title.lower()
    if any(p in title_lower for p in bad_patterns):
        return False
    
    # Count actual characters (exclude emojis and symbols) - relaxed threshold
    chars = re.findall(r'[\u4e00-\u9fffA-Za-z0-9]', title)
    if len(chars) < 5:
        return False
    
    # Allow more emojis
    emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', title))
    if emoji_count > 5:
        return False
    
    return True

def _get_top_articles(topic_data: Dict[str, Any], n: int) -> List[Dict[str, Any]]:
    articles = topic_data.get("articles", [])
    # Filter out invalid titles
    valid_articles = [a for a in articles if _is_valid_title(a.get("title", ""))]
    valid_articles.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
    return valid_articles[:n]


def build_report(data: Dict[str, Any], template: str = "morning", include_coins: bool = False) -> str:
    cfg = TEMPLATES.get(template, TEMPLATES["morning"])
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    topics = data.get("topics", {})
    stats = data.get("output_stats", {})

    label = cfg["label"]
    lines: List[str] = [f"🧠 科技新闻{label} | {now}", ""]

    # -- 行情速览 (placed first like openclaw-sync) --
    if include_coins:
        lines.append("💰 行情速览")
        coins = collect_coins()
        if coins:
            for c in coins:
                lines.append(f"  {c}")
        else:
            lines.append("  ⚠️ 行情接口暂不可用")
        lines.append("")

    # -- 今日重点: top 1 per category --
    lines.append("📌 今日重点")
    has_picks = False
    for topic_id, (emoji, cat_name) in TOPIC_DISPLAY.items():
        topic_data = topics.get(topic_id, {})
        top = _get_top_articles(topic_data, 1)
        if top:
            title = translate_to_zh(top[0].get("title", ""))
            lines.append(f"  {emoji} {cat_name}：{title}")
            has_picks = True
    if not has_picks:
        lines.append("  本轮源更新较少")
    lines.append("")

    # -- Category sections --
    # Group related topics for cleaner layout
    SECTION_GROUPS = [
        ("🤖 AI 前沿", ["llm", "ai-agent"]),
        ("🪙 区块链", ["crypto", "market-prices"]),
        ("🔬 前沿科技", ["frontier-tech"]),
        ("🌍 国际要闻", ["international-news"]),
        ("🇨🇳 国内动态", ["china-news"]),
        ("⚔️ 军事国防", ["military-defense"]),
    ]

    for section_title, topic_ids in SECTION_GROUPS:
        # Collect articles from all topics in this group
        all_articles = []
        for tid in topic_ids:
            all_articles.extend(_get_top_articles(topics.get(tid, {}), cfg["top_n"]))
        # Deduplicate by title
        seen = set()
        unique = []
        for a in sorted(all_articles, key=lambda x: x.get("quality_score", 0), reverse=True):
            t = a.get("title", "")
            if t not in seen:
                seen.add(t)
                unique.append(a)
        if not unique:
            continue
        lines.append(section_title)
        for a in unique[:cfg["top_n"]]:
            title = translate_to_zh(a.get("title", ""))
            sources = a.get("source_count", 1)
            src_str = f" [{sources}源]" if sources > 1 else ""
            lines.append(f"  • {title}{src_str}")
        lines.append("")

    # -- GitHub trending --
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
        lines.append("💻 GitHub 热门")
        for a in unique_gh[:cfg["gh_n"]]:
            title = a.get("title", "")
            stars = a.get("stars", 0) or a.get("daily_stars_est", 0)
            star_str = f" ⭐{stars}" if stars else ""
            lines.append(f"  • {title}{star_str}")
        lines.append("")

    # -- Hot topics (multi-source) --
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
        lines.append("🔥 热议话题")
        for a in unique_hot[:cfg["hot_n"]]:
            title = translate_to_zh(a.get("title", ""))
            sources = a.get("source_count", 1)
            src_str = f" [{sources}源]" if sources > 1 else ""
            lines.append(f"  • {title}{src_str}")
        lines.append("")

    lines.append(f"📊 共采集 {stats.get('total_articles', 0)} 条 | RSS/Twitter/GitHub/Reddit/Web")

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

def build_markdown(data: Dict[str, Any], template: str = "morning", include_coins: bool = False) -> str:
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

    # Add crypto prices if requested
    if include_coins:
        lines.append("## 💰 代币行情")
        lines.append("")
        coins = collect_coins()
        if coins:
            for c in coins:
                lines.append(f"- {c}")
        else:
            lines.append("- 行情接口暂不可用")
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
            md = build_markdown(data, args.template, include_coins=args.coins)
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
