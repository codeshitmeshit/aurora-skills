#!/usr/bin/env python3
"""
Pulse Prefetch — parallel data fetching for all scriptable sources.
Outputs a single JSON blob to stdout.

Usage:
    python3 prefetch.py

Environment variables:
    AMAP_WEATHER_KEY     — 高德天气 API Key (required for weather)
    VOLCENGINE_SEARCH_API_KEY  — 火山引擎搜索 API Key (optional, for news)
    VOLCENGINE_SEARCH_BOT_ID   — 火山引擎搜索 Bot ID (optional, for news)

Dependencies:
    pip install aiohttp requests
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import aiohttp
import requests

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = aiohttp.ClientTimeout(total=15)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

AMAP_WEATHER_KEY = os.environ.get("AMAP_WEATHER_KEY", "78f3c9d4942fad46113f9fa136cea50f")

# 高德天气城市 adcode 映射
AMAP_CITIES = {
    "beijing":  {"adcode": "110000", "name": "北京"},
    "shanghai": {"adcode": "310000", "name": "上海"},
    "nanjing":  {"adcode": "320100", "name": "南京"},
}

# 天气描述 → emoji 映射（高德天气中文描述）
WEATHER_EMOJI_CN = {
    "晴": "☀️", "多云": "⛅", "阴": "☁️",
    "小雨": "🌧️", "中雨": "🌧️🌧️", "大雨": "🌧️🌧️", "暴雨": "🌧️🌧️🌧️",
    "阵雨": "🌦️", "雷阵雨": "⛈️", "雷阵雨并伴有冰雹": "⛈️",
    "雨夹雪": "🌨️", "小雪": "❄️", "中雪": "❄️", "大雪": "🌨️", "暴雪": "🌨️",
    "雾": "🌫️", "霾": "🌫️", "浮尘": "🌫️", "扬沙": "🌫️", "沙尘暴": "🌪️",
    "强沙尘暴": "🌪️", "有风": "🌬️", "微风": "🌬️", "和风": "🌬️",
    "清风": "🌬️", "强风": "💨", "疾风": "💨", "大风": "💨",
    "烈风": "💨", "风暴": "🌪️", "狂暴风": "🌪️", "飓风": "🌪️",
}

PODCAST_URLS = [
    ("硅谷101", "https://www.xiaoyuzhoufm.com/podcast/5e5c52c9418a84a04625e6cc"),
    ("晚点聊", "https://www.xiaoyuzhoufm.com/podcast/61933ace1b4320461e91fd55"),
    ("张小珺Jùn｜商业访谈录", "https://www.xiaoyuzhoufm.com/podcast/626b46ea9cbbf0451cf5a962"),
]

# 火山引擎搜索配置
VOLCENGINE_API_KEY = os.environ.get("VOLCENGINE_SEARCH_API_KEY", "")
VOLCENGINE_BOT_ID = os.environ.get("VOLCENGINE_SEARCH_BOT_ID", "")


# ---------------------------------------------------------------------------
# Weather (高德天气 API)
# ---------------------------------------------------------------------------

async def fetch_weather_amap(session: aiohttp.ClientSession, city_key: str) -> dict:
    """Fetch weather from 高德天气 API (base + forecast)."""
    city_info = AMAP_CITIES[city_key]
    adcode = city_info["adcode"]

    # 实况天气 (base)
    base_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={adcode}&key={AMAP_WEATHER_KEY}&extensions=base"

    async with session.get(base_url) as resp:
        base_data = await resp.json(content_type=None)

    result = {"city": city_info["name"]}

    # 实况
    if base_data.get("status") == "1" and base_data.get("lives"):
        live = base_data["lives"][0]
        desc = live.get("weather", "")
        result["now"] = {
            "temp": live.get("temperature", ""),
            "desc": desc,
            "emoji": WEATHER_EMOJI_CN.get(desc, "🌡️"),
            "humidity": live.get("humidity", ""),
            "wind": f"{live.get('winddirection', '')}风 {live.get('windpower', '')}级",
        }

    # 预报（今天 + 明天）— 单独请求
    forecast_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={adcode}&key={AMAP_WEATHER_KEY}&extensions=all"
    async with session.get(forecast_url) as resp:
        forecast_data = await resp.json(content_type=None)

    if forecast_data.get("status") == "1":
        forecasts = forecast_data.get("forecasts", [])
        if forecasts:
            casts = forecasts[0].get("casts", [])
            for i, label in enumerate(["today", "tomorrow"]):
                if i < len(casts):
                    day = casts[i]
                    day_desc = day.get("dayweather", "")
                    night_desc = day.get("nightweather", "")
                    desc = day_desc if day_desc == night_desc else f"{day_desc}转{night_desc}"
                    result[label] = {
                        "high": day.get("daytemp", ""),
                        "low": day.get("nighttemp", ""),
                        "desc": desc,
                        "emoji": WEATHER_EMOJI_CN.get(day_desc, "🌡️"),
                        "wind": f"{day.get('daywind', '')}风 {day.get('daypower', '')}级",
                        "date": day.get("date", ""),
                    }

    return result


# ---------------------------------------------------------------------------
# Volcengine Search (火山引擎联网搜索)
# ---------------------------------------------------------------------------

def volcengine_search_sync(query: str) -> dict:
    """Search using Volcengine Search Web API (sync, runs in executor)."""
    if not VOLCENGINE_API_KEY or not VOLCENGINE_BOT_ID:
        return {"error": "VOLCENGINE credentials not configured"}

    url = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {VOLCENGINE_API_KEY}",
    }
    payload = {
        "bot_id": VOLCENGINE_BOT_ID,
        "stream": False,
        "messages": [{"role": "user", "content": query}],
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        content = ""
        references = []

        # Extract content from choices
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        # Extract references
        refs = data.get("references", [])
        for ref in refs[:8]:
            references.append({
                "title": ref.get("title", ""),
                "url": ref.get("url", ""),
                "source": ref.get("source_name", ""),
            })

        return {"content": content, "references": references}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Product Hunt (Atom Feed)
# ---------------------------------------------------------------------------

async def fetch_producthunt(session: aiohttp.ClientSession) -> dict:
    """Fetch Product Hunt Atom feed and parse entries."""
    url = "https://www.producthunt.com/feed"
    headers = {"User-Agent": UA}
    async with session.get(url, headers=headers) as resp:
        text = await resp.text()
        status = resp.status

    items = []
    # Parse Atom XML entries
    entries = re.findall(r"<entry>(.*?)</entry>", text, re.DOTALL)
    for entry in entries[:10]:
        title_match = re.search(r"<title>(.*?)</title>", entry)
        link_match = re.search(r'<link[^>]*href="([^"]+)"', entry)
        content_match = re.search(r"<content[^>]*>(.*?)</content>", entry, re.DOTALL)

        title = title_match.group(1).strip() if title_match else ""
        link = link_match.group(1).strip() if link_match else ""

        tagline = ""
        if content_match:
            # Extract tagline from <p> tag
            p_match = re.search(r"&lt;p&gt;\s*(.*?)\s*&lt;/p&gt;", content_match.group(1))
            if p_match:
                tagline = p_match.group(1).strip()

        if title:
            items.append({
                "name": title,
                "tagline": tagline,
                "url": link,
            })

    return {"items": items, "status": status}


# ---------------------------------------------------------------------------
# GitHub Trending
# ---------------------------------------------------------------------------

async def fetch_github_trending(session: aiohttp.ClientSession) -> list:
    """Parse GitHub Trending page for top repos."""
    url = "https://github.com/trending?since=daily"
    async with session.get(url, headers={"User-Agent": UA}) as resp:
        html = await resp.text()

    repos = []
    articles = re.split(r'<article\s+class="Box-row"', html)
    for article in articles[1:8]:
        name_matches = re.findall(r'<a\s+href="(/[^"]+)"', article)
        full_name = ""
        for href in name_matches:
            parts = href.strip("/").split("/")
            if len(parts) == 3 and parts[2] in ("stargazers", "forks"):
                full_name = f"{parts[0]}/{parts[1]}"
                break
        if not full_name:
            for href in name_matches:
                parts = href.strip("/").split("/")
                if (len(parts) == 2 and "?" not in href
                    and parts[0] not in ("login", "sponsors", "settings", "features")):
                    full_name = "/".join(parts)
                    break
        if not full_name:
            continue

        desc_match = re.search(r'<p\s+class="[^"]*">\s*(.*?)\s*</p>', article, re.DOTALL)
        desc = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip() if desc_match else ""
        desc = desc.replace("&amp;", "&")

        lang_match = re.search(r'itemprop="programmingLanguage">(.*?)<', article)
        lang = lang_match.group(1).strip() if lang_match else ""

        stars_today_match = re.search(r"([\d,]+)\s+stars\s+today", article)
        stars_today = stars_today_match.group(1).replace(",", "") if stars_today_match else "0"

        total_match = re.findall(
            r'href="/[^"]+/stargazers"[^>]*>\s*(?:<[^>]*>\s*)*([\d,]+)\s*', article
        )
        total_stars = total_match[0].replace(",", "") if total_match else ""

        repos.append({
            "name": full_name,
            "description": desc,
            "language": lang,
            "stars_today": int(stars_today),
            "total_stars": total_stars,
            "url": f"https://github.com/{full_name}",
        })

    return repos


# ---------------------------------------------------------------------------
# Hacker News
# ---------------------------------------------------------------------------

async def fetch_hacker_news(session: aiohttp.ClientSession) -> list:
    """Fetch top stories from Hacker News API."""
    async with session.get("https://hacker-news.firebaseio.com/v0/topstories.json") as resp:
        ids = await resp.json()

    tasks = [fetch_hn_item(session, sid) for sid in ids[:20]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = [r for r in results if isinstance(r, dict) and r.get("title")]
    items.sort(key=lambda x: x.get("points", 0), reverse=True)
    return items[:10]


async def fetch_hn_item(session: aiohttp.ClientSession, item_id: int) -> dict:
    """Fetch a single HN item."""
    async with session.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json") as resp:
        data = await resp.json()
    return {
        "title": data.get("title", ""),
        "url": data.get("url", f"https://news.ycombinator.com/item?id={item_id}"),
        "points": data.get("score", 0),
        "comments": data.get("descendants", 0),
        "hn_url": f"https://news.ycombinator.com/item?id={item_id}",
    }


# ---------------------------------------------------------------------------
# Podcasts (小宇宙 FM)
# ---------------------------------------------------------------------------

async def fetch_single_podcast(
    session: aiohttp.ClientSession, name: str, url: str
) -> dict | None:
    """Fetch a single podcast page and extract latest episode."""
    try:
        async with session.get(url, headers={"User-Agent": UA}) as resp:
            html = await resp.text()

        nd_match = re.search(r"__NEXT_DATA__[^>]*>(.*?)</script>", html)
        if not nd_match:
            return None

        next_data = json.loads(nd_match.group(1))
        podcast_data = next_data.get("props", {}).get("pageProps", {}).get("podcast", {})
        episodes = podcast_data.get("episodes", [])
        if not episodes:
            return None

        ep = episodes[0]
        title = ep.get("title", "").strip()
        eid = ep.get("eid", "")
        pub_date_str = ep.get("pubDate", "")
        shownotes = ep.get("shownotes") or ep.get("description") or ""
        shownotes = re.sub(r"<[^>]+>", "", shownotes).strip()

        if not title or not eid:
            return None

        if pub_date_str:
            try:
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                if pub_date < datetime.now(timezone.utc) - timedelta(hours=48):
                    return None
            except (ValueError, TypeError):
                pass

        return {
            "name": name,
            "url": url,
            "episode_title": title,
            "episode_url": f"https://www.xiaoyuzhoufm.com/episode/{eid}",
            "episode_date": pub_date_str,
            "shownotes": shownotes[:500],
        }
    except Exception:
        return None


async def fetch_podcasts(session: aiohttp.ClientSession) -> list:
    """Fetch all podcasts in parallel."""
    tasks = [fetch_single_podcast(session, name, url) for name, url in PODCAST_URLS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if r and not isinstance(r, Exception)]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    today_str = datetime.now().strftime("%Y年%m月%d日")
    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "producthunt": None,
        "github_trending": None,
        "hacker_news": None,
        "podcasts": None,
        "news_search": None,
        "weather": {},
        "errors": {},
    }

    loop = asyncio.get_event_loop()

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        # Launch all async fetchers in parallel
        tasks = {
            "producthunt": fetch_producthunt(session),
            "github_trending": fetch_github_trending(session),
            "hacker_news": fetch_hacker_news(session),
            "podcasts": fetch_podcasts(session),
            "weather_beijing": fetch_weather_amap(session, "beijing"),
            "weather_shanghai": fetch_weather_amap(session, "shanghai"),
            "weather_nanjing": fetch_weather_amap(session, "nanjing"),
        }

        keys = list(tasks.keys())
        coros = list(tasks.values())
        results = await asyncio.gather(*coros, return_exceptions=True)

        for key, res in zip(keys, results):
            if isinstance(res, Exception):
                result["errors"][key] = str(res)
                continue

            if key.startswith("weather_"):
                city = key.replace("weather_", "")
                result["weather"][city] = res
            else:
                result[key] = res

    # Sync: Volcengine news search (runs in thread)
    if VOLCENGINE_API_KEY and VOLCENGINE_BOT_ID:
        try:
            news_result = await loop.run_in_executor(
                None,
                volcengine_search_sync,
                f"今天{today_str}科技行业和AI领域有什么重大新闻？包括OpenAI、Google、阿里巴巴、字节跳动等公司的最新动态。请列出最重要的5条新闻，每条包含标题和简短摘要。"
            )
            result["news_search"] = news_result
        except Exception as e:
            result["errors"]["news_search"] = str(e)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
