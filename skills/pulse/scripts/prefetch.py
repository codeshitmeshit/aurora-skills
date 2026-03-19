#!/usr/bin/env python3
"""
Pulse Prefetch — parallel data fetching for all scriptable sources.
Outputs a single JSON blob to stdout.

Usage:
    python3 prefetch.py

Dependencies:
    pip install aiohttp feedparser requests
"""

import asyncio
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import aiohttp

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = aiohttp.ClientTimeout(total=15)

WEATHER_EMOJI = {
    "Sunny": "☀️", "Clear": "☀️",
    "Partly Cloudy": "⛅", "Partly cloudy": "⛅",
    "Cloudy": "☁️", "Overcast": "☁️",
    "Light rain": "🌧️", "Light rain shower": "🌧️",
    "Moderate rain": "🌧️🌧️", "Heavy rain": "🌧️🌧️",
    "Patchy light rain": "🌦️", "Light drizzle": "🌦️",
    "Patchy rain possible": "🌦️", "Patchy rain nearby": "🌦️",
    "Light snow": "❄️", "Moderate snow": "❄️",
    "Heavy snow": "🌨️", "Blizzard": "🌨️",
    "Thundery outbreaks possible": "⛈️", "Thunderstorm": "⛈️",
    "Fog": "🌫️", "Mist": "🌫️", "Haze": "🌫️",
}

PODCAST_URLS = [
    ("硅谷101", "https://www.xiaoyuzhoufm.com/podcast/5e5c52c9418a84a04625e6cc"),
    ("晚点聊", "https://www.xiaoyuzhoufm.com/podcast/61933ace1b4320461e91fd55"),
    ("张小珺Jùn｜商业访谈录", "https://www.xiaoyuzhoufm.com/podcast/626b46ea9cbbf0451cf5a962"),
]

# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

async def fetch_weather(session: aiohttp.ClientSession, city: str) -> dict:
    """Fetch weather from wttr.in."""
    url = f"https://wttr.in/{city}?format=j1"
    async with session.get(url) as resp:
        data = await resp.json(content_type=None)

    result = {}
    for i, label in enumerate(["today", "tomorrow"]):
        day = data["weather"][i]
        desc = day["hourly"][4]["weatherDesc"][0]["value"].strip()
        emoji = WEATHER_EMOJI.get(desc, "🌡️")
        result[label] = {
            "high": int(day["maxtempC"]),
            "low": int(day["mintempC"]),
            "desc": desc,
            "emoji": emoji,
        }
    return result


# ---------------------------------------------------------------------------
# Product Hunt
# ---------------------------------------------------------------------------

async def fetch_producthunt(session: aiohttp.ClientSession) -> dict:
    """Fetch Product Hunt feed and extract product items."""
    url = "https://www.producthunt.com/feed"
    headers = {"User-Agent": UA}
    async with session.get(url, headers=headers) as resp:
        html = await resp.text()
        status = resp.status

    # Extract product items from the page
    items = []
    # Try to parse structured data from the HTML
    name_matches = re.findall(
        r'data-test="post-name"[^>]*>([^<]+)<', html
    )
    tagline_matches = re.findall(
        r'data-test="post-tagline"[^>]*>([^<]+)<', html
    )
    link_matches = re.findall(
        r'href="(/posts/[^"?]+)', html
    )

    seen_links = set()
    for i in range(min(len(name_matches), 15)):
        link = f"https://www.producthunt.com{link_matches[i]}" if i < len(link_matches) else ""
        if link in seen_links:
            continue
        seen_links.add(link)
        items.append({
            "name": name_matches[i].strip() if i < len(name_matches) else "",
            "tagline": tagline_matches[i].strip() if i < len(tagline_matches) else "",
            "url": link,
        })

    return {"items": items[:10], "status": status}


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
    for article in articles[1:8]:  # top 7
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

    items = []
    tasks = []
    for story_id in ids[:20]:
        tasks.append(fetch_hn_item(session, story_id))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, dict) and r.get("title"):
            items.append(r)

    # Sort by score descending
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

        # Check if within 48 hours
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
    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "producthunt": None,
        "github_trending": None,
        "hacker_news": None,
        "podcasts": None,
        "weather": {},
        "errors": {},
    }

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        # Launch all fetchers in parallel
        tasks = {
            "producthunt": fetch_producthunt(session),
            "github_trending": fetch_github_trending(session),
            "hacker_news": fetch_hacker_news(session),
            "podcasts": fetch_podcasts(session),
            "weather_beijing": fetch_weather(session, "Beijing"),
            "weather_shanghai": fetch_weather(session, "Shanghai"),
            "weather_nanjing": fetch_weather(session, "Nanjing"),
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

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
