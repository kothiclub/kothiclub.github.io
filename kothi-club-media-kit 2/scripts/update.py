#!/usr/bin/env python3
"""
Refreshes data/live.json for the Kothi Club media kit.

No packages needed (standard library only). Settings come from environment
variables, which you set as GitHub Actions secrets:

  IG_ACCESS_TOKEN  required  never-expiring Page token (see README) with instagram_basic,
                             instagram_manage_insights, pages_read_engagement
  IG_USER_ID       required  Instagram professional account id (starts with 1784...)
  IG_GRAPH_HOST    optional  graph.facebook.com (default) or graph.instagram.com
  IG_API_VERSION   optional  default v24.0
  FB_PAGE_ID       optional  only needed if IG_ACCESS_TOKEN is not a Page token
  FB_PAGE_TOKEN    optional  Page token (falls back to IG_ACCESS_TOKEN)
  YT_API_KEY       optional  YouTube Data API v3 key
  YT_CHANNEL_ID    optional  YouTube channel id (starts with UC...)
  TOP_N            optional  how many top reels / posts to show (default 6)
  MEDIA_LOOKBACK   optional  how many recent posts to scan (default 120)
  AVG_WINDOW       optional  how many recent reels to average (default 12)
"""
import datetime as dt
import json
import os
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MEDIA_DIR = ROOT / "media"
LIVE_FILE = DATA_DIR / "live.json"

HOST = os.environ.get("IG_GRAPH_HOST") or "graph.facebook.com"
VERSION = os.environ.get("IG_API_VERSION") or "v24.0"
TOP_N = int(os.environ.get("TOP_N") or 6)
LOOKBACK = int(os.environ.get("MEDIA_LOOKBACK") or 120)
AVG_WINDOW = int(os.environ.get("AVG_WINDOW") or 12)
MATURE_DAYS = 3  # reels younger than this are left out of averages

NOW = dt.datetime.now(dt.timezone.utc)

COUNTRIES = {
    "IN": "India", "AE": "United Arab Emirates", "US": "United States",
    "GB": "United Kingdom", "CA": "Canada", "AU": "Australia", "SG": "Singapore",
    "SA": "Saudi Arabia", "QA": "Qatar", "OM": "Oman", "KW": "Kuwait", "NP": "Nepal",
    "BD": "Bangladesh", "PK": "Pakistan", "LK": "Sri Lanka", "DE": "Germany",
    "NZ": "New Zealand", "MY": "Malaysia",
}
GENDERS = {"F": "Women", "M": "Men", "U": "Not specified"}


class ApiError(Exception):
    pass


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def http_json(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise ApiError(f"HTTP {e.code}: {body[:400]}")
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise ApiError(str(e))


def graph(path, token, **params):
    params["access_token"] = token
    return http_json(f"https://{HOST}/{VERSION}/{path}?{urllib.parse.urlencode(params)}")


def metric_values(payload):
    out = {}
    for m in payload.get("data", []):
        if "total_value" in m:
            out[m["name"]] = m["total_value"].get("value")
        elif m.get("values"):
            out[m["name"]] = m["values"][-1].get("value")
    return out


def parse_time(ts):
    try:
        return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")
    except (TypeError, ValueError):
        return None


# ---------- media ----------

MEDIA_METRICS = ["views", "reach", "likes", "comments", "saved", "shares", "total_interactions"]


def list_media(user_id, token):
    fields = ("id,caption,media_type,media_product_type,permalink,"
              "thumbnail_url,media_url,timestamp,like_count,comments_count")
    page = graph(f"{user_id}/media", token, fields=fields, limit=50)
    items = []
    while True:
        items += page.get("data", [])
        nxt = page.get("paging", {}).get("next")
        if len(items) >= LOOKBACK or not nxt:
            break
        page = http_json(nxt)
    return items[:LOOKBACK]


def media_insights(media_id, token):
    try:
        return metric_values(graph(f"{media_id}/insights", token, metric=",".join(MEDIA_METRICS)))
    except ApiError:
        # Older posts can reject one metric and fail the whole call; ask one at a time.
        out = {}
        for name in MEDIA_METRICS:
            try:
                out.update(metric_values(graph(f"{media_id}/insights", token, metric=name)))
            except ApiError:
                pass
        return out


def first_line(caption, limit=96):
    line = (caption or "").strip().split("\n")[0].strip()
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def to_card(m, ins):
    likes = ins.get("likes", m.get("like_count"))
    comments = ins.get("comments", m.get("comments_count"))
    saves, shares = ins.get("saved"), ins.get("shares")
    interactions = ins.get("total_interactions")
    if interactions is None:
        interactions = sum(v or 0 for v in (likes, comments, saves, shares))
    return {
        "id": m["id"],
        "permalink": m.get("permalink"),
        "type": m.get("media_type"),
        "posted": m.get("timestamp"),
        "caption": first_line(m.get("caption")),
        "views": ins.get("views"),
        "reach": ins.get("reach"),
        "likes": likes,
        "comments": comments,
        "saves": saves,
        "shares": shares,
        "interactions": interactions,
        "thumb": None,
        "_image_url": m.get("thumbnail_url") or m.get("media_url"),
    }


def save_thumb(card):
    url = card.get("_image_url")
    path = MEDIA_DIR / f"{card['id']}.jpg"
    if path.exists():
        return f"media/{path.name}"
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            path.write_bytes(r.read())
        return f"media/{path.name}"
    except Exception as e:  # noqa: BLE001
        warn(f"thumbnail for {card['id']}: {e}")
        return None


# ---------- account ----------

def last_30_days(user_id, token):
    until = int(NOW.timestamp())
    since = until - 30 * 86400 + 120
    out = {}
    for metric in ("views", "reach", "accounts_engaged", "total_interactions"):
        try:
            out.update(metric_values(graph(
                f"{user_id}/insights", token, metric=metric, period="day",
                metric_type="total_value", since=since, until=until)))
        except ApiError as e:
            warn(f"account {metric}: {e}")
    return out


def label_for(breakdown, key):
    if breakdown == "gender":
        return GENDERS.get(key, key)
    if breakdown == "country":
        return COUNTRIES.get(key, key)
    if breakdown == "city":
        return key.split(",")[0].strip()
    return key


def demographics(user_id, token):
    out = {}
    for bd in ("gender", "age", "city", "country"):
        payload, last_error = None, None
        for extra in ({}, {"timeframe": "this_month"}):
            try:
                payload = graph(f"{user_id}/insights", token, metric="follower_demographics",
                                period="lifetime", metric_type="total_value", breakdown=bd, **extra)
                break
            except ApiError as e:
                last_error = e
        if payload is None:
            warn(f"demographics {bd}: {last_error}")
            continue
        rows = []
        for m in payload.get("data", []):
            for b in m.get("total_value", {}).get("breakdowns", []):
                for r in b.get("results", []):
                    rows.append((r["dimension_values"][0], r["value"]))
        total = sum(v for _, v in rows) or 1
        if bd == "age":
            rows.sort(key=lambda r: r[0])
        else:
            rows.sort(key=lambda r: -r[1])
        if bd in ("city", "country"):
            rows = rows[:6]
        key = {"gender": "gender", "age": "age", "city": "cities", "country": "countries"}[bd]
        out[key] = [
            {"label": label_for(bd, k), "share": round(v * 100 / total, 1)} for k, v in rows
        ]
    return out


# ---------- other platforms ----------

def facebook_followers(token):
    # With a Page token, "me" is the Page itself, so no extra setup is needed.
    page_id = os.environ.get("FB_PAGE_ID") or "me"
    tok = os.environ.get("FB_PAGE_TOKEN") or token
    try:
        d = http_json(f"https://graph.facebook.com/{VERSION}/{page_id}?" +
                      urllib.parse.urlencode({"fields": "followers_count,fan_count", "access_token": tok}))
        return d.get("followers_count") or d.get("fan_count")
    except ApiError as e:
        warn(f"facebook: {e}")
        return None


def youtube_subscribers():
    key, channel = os.environ.get("YT_API_KEY"), os.environ.get("YT_CHANNEL_ID")
    if not key or not channel:
        return None
    try:
        d = http_json("https://www.googleapis.com/youtube/v3/channels?" +
                      urllib.parse.urlencode({"part": "statistics", "id": channel, "key": key}))
        items = d.get("items") or []
        return int(items[0]["statistics"]["subscriberCount"]) if items else None
    except (ApiError, KeyError, ValueError) as e:
        warn(f"youtube: {e}")
        return None


# ---------- main ----------

def main():
    token, user_id = os.environ.get("IG_ACCESS_TOKEN"), os.environ.get("IG_USER_ID")
    if not token or not user_id:
        sys.exit("Set IG_ACCESS_TOKEN and IG_USER_ID first (see README).")
    DATA_DIR.mkdir(exist_ok=True)
    MEDIA_DIR.mkdir(exist_ok=True)
    previous = json.loads(LIVE_FILE.read_text()) if LIVE_FILE.exists() else {}

    profile = graph(user_id, token, fields="username,name,followers_count,media_count")
    media = list_media(user_id, token)
    print(f"Scanning {len(media)} posts…")

    reels, posts = [], []
    for m in media:
        card = to_card(m, media_insights(m["id"], token))
        (reels if m.get("media_product_type") == "REELS" else posts).append(card)

    top_reels = sorted(reels, key=lambda c: c["views"] or c["reach"] or 0, reverse=True)[:TOP_N]
    top_posts = sorted(posts, key=lambda c: c["reach"] or c["views"] or 0, reverse=True)[:TOP_N]

    keep = set()
    for c in top_reels + top_posts:
        c["thumb"] = save_thumb(c)
        keep.add(c["id"])
    for c in reels + posts:
        c.pop("_image_url", None)
    for f in MEDIA_DIR.glob("*.jpg"):
        if f.stem not in keep:
            f.unlink()

    mature = [c for c in reels
              if (p := parse_time(c["posted"])) and NOW - p > dt.timedelta(days=MATURE_DAYS)][:AVG_WINDOW]
    total_reach = sum(c["reach"] or 0 for c in mature)
    averages = {
        "reel_views": round(statistics.mean([c["views"] or 0 for c in mature])) if mature else None,
        "reel_reach": round(total_reach / len(mature)) if mature else None,
        "engagement_rate": round(sum(c["interactions"] or 0 for c in mature) * 100 / total_reach, 2) if total_reach else None,
        "reel_shares": round(statistics.mean([c["shares"] or 0 for c in mature])) if mature else None,
        "reels_counted": len(mature),
    }

    prev_platforms = previous.get("platforms", {})
    live = {
        "generated_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "profile": {
            "username": profile.get("username"),
            "name": profile.get("name"),
            "followers": profile.get("followers_count"),
            "media_count": profile.get("media_count"),
        },
        "platforms": {
            "instagram": profile.get("followers_count"),
            "facebook": facebook_followers(token) or prev_platforms.get("facebook"),
            "youtube": youtube_subscribers() or prev_platforms.get("youtube"),
        },
        "last_30_days": last_30_days(user_id, token),
        "averages": averages,
        "top_reels": top_reels,
        "top_posts": top_posts,
        "audience": demographics(user_id, token) or previous.get("audience", {}),
    }
    LIVE_FILE.write_text(json.dumps(live, indent=2, ensure_ascii=False))
    print(f"Wrote {LIVE_FILE.relative_to(ROOT)}: {len(top_reels)} reels, {len(top_posts)} posts.")


if __name__ == "__main__":
    main()
