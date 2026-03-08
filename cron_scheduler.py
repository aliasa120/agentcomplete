"""
cron_scheduler.py — Single source of truth for all auto-triggers.

Runs as a dedicated process (python cron_scheduler.py) alongside:
  - feeder_server.py  (port 8080, HTTP-only, no scheduler)
  - langgraph dev     (port 2024)

On every 60-second tick it reads Supabase settings and fires
the feeder and/or agent if their interval has elapsed.

Environment variables (same .env as the rest of the project):
  SUPABASE_URL           / NEXT_PUBLIC_SUPABASE_URL
  SUPABASE_ANON_KEY      / NEXT_PUBLIC_SUPABASE_ANON_KEY
  FEEDER_SERVER_URL      (default: http://localhost:8080)
  LANGGRAPH_URL          / NEXT_PUBLIC_API_URL (default: http://localhost:2024)
"""

import os
import re
import time
import json
import logging
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# ── Load env ────────────────────────────────────────────────────────────────
load_dotenv()           # root .env
load_dotenv("deep-agents-ui-main/.env.local", override=False)   # frontend .env

SUPABASE_URL = (
    os.getenv("SUPABASE_URL")
    or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
)
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
)
FEEDER_URL   = os.getenv("FEEDER_SERVER_URL", "http://localhost:8080")
LG_URL       = os.getenv("LANGGRAPH_URL") or os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:2024")
# URL of the Next.js frontend (used to call /api/publish)
NEXT_UI_URL  = os.getenv("NEXT_UI_URL", "http://localhost:3000")  # override: http://frontend:3000 in Docker

TICK_SECONDS = 60   # how often we check

# In-memory set of post IDs currently being published — prevents double-fire
# across ticks if publishing takes longer than TICK_SECONDS.
_publishing_in_progress: set = set()

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Cron] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cron")


# ── Supabase helpers ─────────────────────────────────────────────────────────
def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _sb_get(table: str, params: str = "") -> list:
    """Simple Supabase REST GET."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    r = requests.get(url, headers=_sb_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def _sb_upsert(table: str, rows: list) -> None:
    """Simple Supabase REST UPSERT (on_conflict=key)."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {**_sb_headers(), "Prefer": "resolution=merge-duplicates"}
    r = requests.post(url, headers=headers, json=rows, timeout=10)
    r.raise_for_status()


def _sb_patch(table: str, params: str, body: dict) -> None:
    """Simple Supabase REST PATCH."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    r = requests.patch(url, headers=_sb_headers(), json=body, timeout=10)
    r.raise_for_status()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _elapsed_since(iso_str: str) -> float:
    """Seconds elapsed since the given ISO timestamp."""
    if not iso_str:
        return float("inf")
    try:
        ts = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return float("inf")


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities — matches page.tsx stripHtml."""
    if not text:
        return ""
    # Remove tags
    clean = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    clean = clean.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    clean = clean.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return clean.strip()


# ── Feeder trigger ───────────────────────────────────────────────────────────
def check_feeder() -> None:
    try:
        rows = _sb_get("feeder_settings", "key=in.(feeder_auto_trigger_enabled,feeder_auto_trigger_interval_minutes,feeder_last_trigger_at)")
        smap = {r["key"]: r["value"] for r in rows}

        enabled = smap.get("feeder_auto_trigger_enabled", "false").lower() == "true"
        if not enabled:
            return

        interval_min = float(smap.get("feeder_auto_trigger_interval_minutes", "30") or "30")
        interval_sec = interval_min * 60
        last_at = smap.get("feeder_last_trigger_at", "") or ""
        elapsed = _elapsed_since(last_at)

        if elapsed >= interval_sec:
            run_time = now_iso()
            log.info(f"⏰ FEEDER trigger due (elapsed={elapsed/60:.1f}min, interval={interval_min}min) — firing...")
            # Save timestamp FIRST to prevent double-fire
            _sb_upsert("feeder_settings", [{"key": "feeder_last_trigger_at", "value": run_time, "updated_at": run_time}])
            # Call feeder HTTP server (synchronous OK here — runs in background thread)
            try:
                resp = requests.post(f"{FEEDER_URL}/run", json={}, timeout=310)
                if resp.ok:
                    log.info("✅ Feeder pipeline completed successfully.")
                else:
                    log.warning(f"❌ Feeder pipeline returned {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                log.error(f"❌ Feeder HTTP call failed: {e}")
        else:
            remaining = interval_sec - elapsed
            log.info(f"Feeder: next run in {remaining/60:.1f}min (interval={interval_min}min)")

    except Exception as e:
        log.error(f"check_feeder error: {e}")


# ── LangGraph helpers ────────────────────────────────────────────────────────
def _lg_list_assistants() -> list:
    r = requests.post(
        f"{LG_URL}/assistants/search",
        headers={"Content-Type": "application/json"},
        json={"limit": 10, "offset": 0},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _lg_create_thread() -> str:
    r = requests.post(f"{LG_URL}/threads", headers={"Content-Type": "application/json"}, json={}, timeout=10)
    r.raise_for_status()
    return r.json()["thread_id"]


def _lg_create_run(thread_id: str, assistant_id: str, content: str) -> None:
    payload = {
        "assistant_id": assistant_id,
        "input": {"messages": [{"role": "human", "content": content}]},
    }
    r = requests.post(
        f"{LG_URL}/threads/{thread_id}/runs",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    r.raise_for_status()


# ── Agent trigger ────────────────────────────────────────────────────────────
def check_agent() -> None:
    try:
        rows = _sb_get(
            "agent_settings",
            "key=in.(auto_trigger_enabled,auto_trigger_interval_minutes,auto_trigger_last_at,queue_batch_size)"
        )
        smap = {r["key"]: r["value"] for r in rows}

        enabled = smap.get("auto_trigger_enabled", "false").lower() == "true"
        if not enabled:
            return

        interval_min = float(smap.get("auto_trigger_interval_minutes", "30") or "30")
        interval_sec = interval_min * 60
        last_at = smap.get("auto_trigger_last_at", "") or ""
        elapsed = _elapsed_since(last_at)
        batch_size = int(smap.get("queue_batch_size", "2") or "2")

        if elapsed >= interval_sec:
            # Check for pending articles
            pending = _sb_get(
                "feeder_articles",
                f"status=eq.Pending&order=created_at.asc&limit={batch_size}&select=id,title,description,url"
            )
            if not pending:
                log.info("Agent: trigger due but queue empty — skipping.")
                return

            run_time = now_iso()
            log.info(f"⏰ AGENT trigger due (elapsed={elapsed/60:.1f}min, interval={interval_min}min) — firing {len(pending)} articles...")

            # Save timestamp FIRST to prevent double-fire
            _sb_upsert("agent_settings", [{"key": "auto_trigger_last_at", "value": run_time, "updated_at": run_time}])

            # Mark articles as Processing
            ids = [a["id"] for a in pending]
            ids_filter = "(" + ",".join(f'"{i}"' for i in ids) + ")"
            _sb_patch("feeder_articles", f"id=in.{ids_filter}", {"status": "Processing"})

            # Discover assistant_id from LangGraph
            assistant_id = "research"   # fallback
            try:
                assistants = _lg_list_assistants()
                if assistants:
                    assistant_id = assistants[0]["assistant_id"]
                    log.info(f"Using assistant: {assistant_id}")
            except Exception as e:
                log.warning(f"Could not fetch assistants — using fallback 'research': {e}")

            # Create one LangGraph run per article
            for article in pending:
                try:
                    thread_id = _lg_create_thread()
                    # Match page.tsx format: strip HTML, no URL
                    clean_title = _strip_html(article.get('title', ''))
                    clean_desc  = _strip_html(article.get('description', ''))
                    content = f"Title: {clean_title}\nDescription: {clean_desc}"
                    _lg_create_run(thread_id, assistant_id, content)
                    log.info(f"  ✅ Created run for article: {clean_title[:60]}")
                except Exception as e:
                    # Revert article to Pending so it can be retried
                    try:
                        _sb_patch("feeder_articles", f"id=eq.{article['id']}", {"status": "Pending"})
                    except Exception:
                        pass
                    log.error(f"  ❌ Failed to create run for article {article['id']}: {e}")

        else:
            remaining = interval_sec - elapsed
            log.info(f"Agent:  next run in {remaining/60:.1f}min (interval={interval_min}min)")

    except Exception as e:
        log.error(f"check_agent error: {e}")


# ── Auto-publish social posts ─────────────────────────────────────────────────
def check_auto_publish() -> None:
    """
    Runs on every tick. Finds social_posts that are not yet fully published
    to all enabled platforms and calls /api/publish (the Next.js endpoint).

    Reliability guarantees:
      - REQUIRES auto_publish_since: if not set, saves current time and skips.
        This means "turning on auto-publish" is the gate — old posts are NEVER
        published automatically.
      - Uses _publishing_in_progress to prevent double-fire across slow ticks.
      - After a publish attempt, marks failed platforms as False in published_to
        in Supabase so they are NOT retried on future ticks. A post is only
        retried if the user manually toggles auto-publish off → on again
        (which refreshes auto_publish_since) and the post is after that cutoff.
      - Per-post error handling: one failure never blocks others.
    """
    global _publishing_in_progress
    try:
        # ── 1. Read settings ──────────────────────────────────────────────────
        rows = _sb_get(
            "agent_settings",
            "key=in.(social_auto_publish,auto_publish_since,"
            "social_twitter_enabled,social_fb_enabled,social_ig_enabled)"
        )
        smap = {r["key"]: r["value"] for r in rows}

        enabled = smap.get("social_auto_publish", "false").lower() == "true"
        if not enabled:
            return   # silent — no log spam when disabled

        # ── 2. STRICT cutoff guard ────────────────────────────────────────────
        since_str = (smap.get("auto_publish_since", "") or "").strip()
        if not since_str:
            # auto_publish_since was never written — set it NOW and skip.
            # Next tick onward, only posts created after this moment are eligible.
            cutoff = now_iso()
            _sb_upsert("agent_settings", [{"key": "auto_publish_since", "value": cutoff, "updated_at": cutoff}])
            log.info(f"AutoPublish: auto_publish_since was missing — set to {cutoff}. No posts published this tick.")
            return

        # ── 3. Build enabled platforms ────────────────────────────────────────
        platforms: list[str] = []
        if smap.get("social_twitter_enabled") == "true":
            platforms.append("twitter")
        if smap.get("social_fb_enabled") == "true":
            platforms.append("facebook")
        if smap.get("social_ig_enabled") == "true":
            platforms.append("instagram")

        if not platforms:
            return

        # ── 4. Query ONLY posts created after the cutoff ──────────────────────
        posts = _sb_get(
            "social_posts",
            f"select=id,created_at,published_to&order=created_at.asc"
            f"&created_at=gte.{since_str}"
        )

        if not posts:
            return   # nothing new to publish

        # ── 5. Filter to posts that still need publishing ─────────────────────
        to_publish = []
        for post in posts:
            post_id = post["id"]
            if post_id in _publishing_in_progress:
                continue
            published_to: dict = post.get("published_to") or {}
            # Only include platforms where value is not True (False or missing)
            # Note: value == False means we already tried and failed — skip it.
            # value == None / missing means never attempted — try it.
            needed = [p for p in platforms if published_to.get(p) is None or published_to.get(p) == ""]
            if needed:
                to_publish.append((post_id, needed, published_to))

        if not to_publish:
            return

        log.info(f"▶ AUTO-PUBLISH: {len(to_publish)} new post(s) to publish...")

        # ── 6. Publish each post ──────────────────────────────────────────────
        for post_id, needed_platforms, current_published_to in to_publish:
            _publishing_in_progress.add(post_id)
            try:
                resp = requests.post(
                    f"{NEXT_UI_URL}/api/publish",
                    json={"post_id": post_id, "platforms": needed_platforms},
                    headers={"Content-Type": "application/json"},
                    timeout=120,   # Instagram container processing can take ~60 s
                )
                if resp.ok:
                    result = resp.json()
                    results_detail = result.get("results", {})
                    successes = [p for p, r in results_detail.items() if r.get("success")]
                    failures  = {p: r.get("error") for p, r in results_detail.items() if not r.get("success")}

                    if successes:
                        log.info(f"  ✅ Post {post_id[:8]}… published to: {', '.join(successes)}")

                    # Mark failed platforms as False in Supabase so they aren't
                    # retried every tick — only a fresh auto_publish_since will
                    # re-enable retrying them.
                    if failures:
                        # Use the published_to returned by the API so we don't overwrite successes
                        new_published_to = dict(result.get("published_to", current_published_to))
                        for plat, err in failures.items():
                            log.warning(f"  ⚠️  Post {post_id[:8]}… failed on {plat}: {err}")
                            # Use False (not None) to mark "attempted but failed"
                            new_published_to[plat] = False
                        try:
                            _sb_patch(
                                "social_posts",
                                f"id=eq.{post_id}",
                                {"published_to": new_published_to}
                            )
                        except Exception as patch_err:
                            log.error(f"  ❌ Could not save failure state for post {post_id[:8]}…: {patch_err}")
                else:
                    log.error(f"  ❌ /api/publish HTTP {resp.status_code} for post {post_id[:8]}…: {resp.text[:200]}")
            except requests.exceptions.Timeout:
                log.error(f"  ❌ Timeout publishing post {post_id[:8]}… (>120s)")
            except Exception as e:
                log.error(f"  ❌ Error publishing post {post_id[:8]}…: {e}")
            finally:
                _publishing_in_progress.discard(post_id)

    except Exception as e:
        log.error(f"check_auto_publish error: {e}")


# ── Main loop ────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("Cron Scheduler started.")
    log.info(f"  Feeder URL:    {FEEDER_URL}")
    log.info(f"  LangGraph URL: {LG_URL}")
    log.info(f"  Next.js URL:   {NEXT_UI_URL}")
    log.info(f"  Supabase URL:  {SUPABASE_URL[:40]}...")
    log.info(f"  Tick interval: {TICK_SECONDS}s")
    log.info("=" * 60)

    while True:
        log.info("--- tick ---")
        check_feeder()
        check_agent()
        check_auto_publish()
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
