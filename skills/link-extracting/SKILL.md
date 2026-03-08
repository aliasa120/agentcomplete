---
name: link-extracting
description: Use after a linkup_search when snippets are too short to complete a research target. Covers URL selection, call format, fallback chain, and budget rules. Trigger keywords: extract content, read article, tavily, full text, URL extract, article content, partial result.
---

# Link Extracting Skill

## Critical Constraints (Read First)

- **Maximum 3 `tavily_extract` calls total** — hard limit
- **Maximum 2 URLs per call** — never pass more
- **Only extract when a target is Partially Complete** and a snippet hints at the answer
- **Never retry the same URL twice** — if it fails, move on
- **Always call `think_tool` immediately after** extraction results arrive

---

## When to Extract vs. When to Skip

| Condition | Action |
|---|---|
| All targets ✅ Complete after search | **Skip** — no extraction needed |
| Target ⚠️ Partial AND credible URL snippet hints at answer | **Extract** this URL |
| Target ❌ Not Found AND no on-topic URLs in results | **Skip extract, run next search round** |
| Already used 3 `tavily_extract` calls | **Skip** — budget exhausted |
| URL snippet is off-topic / vague mention | **Skip this URL** |

---

## URL Selection Rules

**Pick from credible outlets only:**
> Dawn, Geo TV, Al Jazeera, Reuters, BBC, ARY News, The News, Tribune, Express Tribune

**Disqualify immediately:**
- Any URL where the snippet shows NO direct relevance to remaining targets
- Social media links (twitter.com, facebook.com, instagram.com)
- Unknown blogs or aggregator sites without a clear outlet brand
- URLs already extracted in a previous call

---

## How to Call

```python
tavily_extract(
    urls=["https://credible-outlet-1.com/article/...", "https://credible-outlet-2.com/..."],
    query="[same keyword string you used in the preceding linkup_search]"
)
```

The `query` parameter causes Tavily to rank extracted chunks by relevance — always pass it.

---

## Fallback Chain

```
Extract URL1 + URL2
↓
think_tool: URL1 → rich / thin / failed?
           URL2 → rich / thin / failed?
↓
If target still ⚠️ Partial AND extract budget remaining:
  → Pick next-best unused URL from same search round
  → Call tavily_extract again with just that 1 URL
↓
If no more budget OR no more candidate URLs:
  → Mark target as Partially Complete, accept it, continue workflow
```

---

## One Example: Full Extract Decision

**Situation:**
- Target 2: TTAP rejection statement — still ⚠️ Partial
- Geo TV snippet: "TTAP officials said the examination findings were..." (cut off)
- Dawn snippet: completely off-topic
- Extract calls used so far: 0

**Decision (from think_tool):**
> "geo.tv URL is on-topic for Target 2. Dawn off-topic. Extract geo.tv URL only."

**Call:**
```python
tavily_extract(
    urls=["https://geo.tv/latest/123456-ttap-rejects-naqvi"],
    query="TTAP rejection Naqvi Imran Khan medical exam 2026"
)
```
