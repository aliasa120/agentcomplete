"""
Feeder Pipeline - 5-Layer article deduplication.

Layer -2: Time filter (drop old articles)
Layer -1: Domain whitelist (keep only trusted sources)
Layer  0: Event clustering (best source per event cluster)
Layer  1: GUID check (Supabase, CHECK-ONLY)
Layer  2: Hash check (SHA-256 title+desc+url, Supabase, CHECK-ONLY)
Layer  AI: Feeder Dedup Agent (LLM-based dedup, replaces L3/L4/L5)
          Phase 1 — in-batch dedup (group by event, keep best source)
          Phase 2 — DB comparison (drop already-covered stories)

DEFERRED STORAGE: Nothing written to DB during any layer check.
Atomic storage block runs ONLY after article passes ALL layers.
"""
import calendar
import feedparser
from datetime import datetime, timezone
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

from feeder.db import supabase_client
from feeder.models import FeederArticle
from feeder.layer_minus2_time import layer_minus2_time
from feeder.layer_minus1_domain import layer_minus1_domain, reset_whitelist_cache
from feeder.layer_0_event_clustering import layer_0_event_clustering
from feeder.layer_1_guid import layer_1_guid
from feeder.layer_2_hash import layer_2_hash
from feeder_agent.agent import run_feeder_dedup_agent


# --- Settings from Supabase -----------------------------------------------
def load_settings() -> dict:
    defaults = {
        "batch_size": 30,
        "max_age_hours": 24,
        "cluster_threshold": 70,
        "agent_db_title_limit": 300,   # how many recent DB titles the agent compares against
    }
    try:
        res = supabase_client.table("feeder_settings").select("key,value").execute()
        for row in (res.data or []):
            k, v = row["key"], row["value"]
            if k in ("batch_size", "max_age_hours", "cluster_threshold", "agent_db_title_limit"):
                defaults[k] = int(v)
    except Exception as e:
        print(f"Warning: Could not load settings: {e}")
    return defaults


def load_domain_priority() -> dict[str, int]:
    try:
        res = supabase_client.table("feeder_whitelisted_domains") \
            .select("domain").order("created_at", desc=False).execute()
        return {row["domain"].lower(): idx for idx, row in enumerate(res.data or [])}
    except Exception as e:
        print(f"Warning: Could not load domain priority: {e}")
        return {}


def load_feed_sources() -> list[str]:
    try:
        res = supabase_client.table("feeder_sources").select("url").eq("is_active", True).execute()
        urls = [r["url"] for r in (res.data or [])]
        if urls:
            return urls
    except Exception as e:
        print(f"Warning: Could not load feed sources: {e}")
    return ["https://news.google.com/rss/search?q=pakistan&hl=en-PK&gl=PK&ceid=PK:en"]


def fetch_rss_feed(url: str) -> list[FeederArticle]:
    feed = feedparser.parse(url)
    articles = []
    for entry in feed.entries:
        link = getattr(entry, "link", "")
        source = getattr(entry, "source", None)
        if isinstance(source, dict) and source.get("href"):
            raw_domain = urlparse(source["href"]).netloc
        else:
            raw_domain = urlparse(link).netloc
        domain = raw_domain.lower().removeprefix("www.")

        pub_date = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                pub_date = datetime.fromtimestamp(
                    calendar.timegm(entry.published_parsed), tz=timezone.utc
                )
            except Exception:
                pass

        articles.append(FeederArticle(
            title=getattr(entry, "title", ""),
            link=link,
            description=getattr(entry, "summary", ""),
            guid=getattr(entry, "id", link),
            published_parsed=pub_date,
            domain=domain,
        ))
    return articles


# --- Verbose drop logger ---------------------------------------------------
def _log_drop(layer: str, article_title: str, reason: str):
    """Print a consistent drop log line visible in the pipeline output."""
    print(f"  [DROP L{layer}] '{article_title[:70]}'"
          f"\n             Reason: {reason}")


# --- Main Pipeline ---------------------------------------------------------
def run_feeder_pipeline() -> tuple[list[FeederArticle], list[tuple[FeederArticle, str]]]:
    settings = load_settings()
    batch_size    = settings["batch_size"]
    max_age       = settings["max_age_hours"]
    cluster_thr   = settings["cluster_threshold"]
    agent_db_limit = settings["agent_db_title_limit"]

    domain_priority = load_domain_priority()
    feed_urls       = load_feed_sources()
    reset_whitelist_cache()

    dropped: list[tuple[FeederArticle, str]] = []

    # -- Fetch --
    raw: list[FeederArticle] = []
    for url in feed_urls:
        raw.extend(fetch_rss_feed(url))
    print(f"Fetched {len(raw)} raw articles from {len(feed_urls)} feed(s).")

    # -- Layer -2: Time filter --
    after_time = [a for a in raw if layer_minus2_time(a.published_parsed, max_age)]
    for a in raw:
        if a not in after_time:
            reason = f"Too old (max {max_age}h, published: {a.published_parsed})"
            dropped.append((a, reason))
    print(f"-> {len(after_time)} passed Layer -2 (time filter <={max_age}h). "
          f"{len(raw)-len(after_time)} dropped.")

    # -- Layer -1: Domain whitelist --
    after_domain = [a for a in after_time if layer_minus1_domain(a.domain)]
    for a in after_time:
        if a not in after_domain:
            reason = f"Domain '{a.domain}' not in whitelist"
            dropped.append((a, reason))
    print(f"-> {len(after_domain)} passed Layer -1 (whitelist). "
          f"{len(after_time)-len(after_domain)} dropped.")

    # -- Layer 0: Event clustering --
    after_cluster, cluster_dropped = layer_0_event_clustering(
        after_domain, domain_priority, cluster_threshold=cluster_thr
    )
    for a, r in cluster_dropped:
        dropped.append((a, r))
    print(f"-> {len(after_cluster)} passed Layer 0 "
          f"(event clustering {cluster_thr}%; {len(cluster_dropped)} same-event removed).")

    # Batch cap
    batch = after_cluster[:batch_size]
    print(f"-> Processing batch of {len(batch)} through Layers 1-2 then Feeder Dedup Agent.")

    # -- Layers 1-2: GUID + Hash check (deterministic, CHECK-ONLY) --
    passed: list[FeederArticle] = []

    for art in batch:
        t = art.title

        # L1 - GUID
        is_new, note = layer_1_guid(art.guid)
        if not is_new:
            _log_drop("-1 GUID", t, note)
            dropped.append((art, "L1 GUID duplicate")); continue

        # L2 - Hash
        is_new, h, note = layer_2_hash(art.title, art.description, art.link)
        art.hash = h
        if not is_new:
            _log_drop("-2 Hash", t, note)
            dropped.append((art, "L2 Hash duplicate")); continue

        passed.append(art)

    print(f"-> {len(passed)} passed Layers 1-2 (GUID / Hash). "
          f"{len(batch)-len(passed)} dropped in L1-L2.")

    # -- Feeder Dedup Agent: replaces L3 (Fuzzy) + L4 (NER) + L5 (Semantic) --
    print(f"\n-> Running Feeder Dedup Agent on {len(passed)} articles...")
    final, agent_dropped = run_feeder_dedup_agent(
        passed, db_title_limit=agent_db_limit
    )
    for art, reason in agent_dropped:
        dropped.append((art, f"Agent dedup: {reason}"))

    print(f"-> {len(final)} passed Agent dedup. {len(agent_dropped)} dropped by agent.")

    # ====================================================================
    # ATOMIC STORAGE: ALL layers passed -> store everything now
    # ====================================================================
    if final:
        pinecone_index = None
        try:
            from feeder.layer_5_semantic import _get_pinecone
            _, pinecone_index = _get_pinecone()
        except Exception as e:
            print(f"Warning: Pinecone connect failed: {e}")

        print(f"\nStoring {len(final)} articles atomically...")
        for art in final:
            try:
                supabase_client.table("feeder_seen_guids").insert({"guid": art.guid}).execute()
            except Exception as e:
                print(f"  [store] GUID error: {e}")
            try:
                supabase_client.table("feeder_seen_hashes").insert({"hash": art.hash}).execute()
            except Exception as e:
                print(f"  [store] Hash error: {e}")
            try:
                row = {
                    "guid": art.guid,
                    "hash": art.hash,
                    "title": art.title,
                    "description": art.description,
                    "url": art.link,
                    "source_domain": art.domain,
                    "status": "Pending",
                }
                if art.published_parsed is not None:
                    row["published_at"] = art.published_parsed.isoformat()
                supabase_client.table("feeder_articles").upsert(row, on_conflict="guid").execute()
                print(f"  [stored] '{art.title[:80]}'")
            except Exception as e:
                print(f"  [store] Article error: {e}")

    # ====================================================================
    # FINAL SUMMARY: Full drop report
    # ====================================================================
    print(f"\n{'='*60}")
    print(f"PIPELINE SUMMARY")
    print(f"{'='*60}")
    print(f"  Fetched:      {len(raw)}")
    print(f"  After L-2:    {len(after_time)}")
    print(f"  After L-1:    {len(after_domain)}")
    print(f"  After L0:     {len(after_cluster)}")
    print(f"  After L1-2:   {len(passed)}")
    print(f"  After Agent:  {len(final)}")
    print(f"  STORED/Final: {len(final)}")
    print(f"  Total Dropped:{len(dropped)}")
    print(f"{'='*60}")
    print(f"[ok] {len(final)} new unique articles stored as Pending!")
    return final, dropped


if __name__ == "__main__":
    run_feeder_pipeline()
