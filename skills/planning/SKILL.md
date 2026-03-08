---
name: planning
description: Use when starting a new news article. Analyse information gaps (WHO WHAT WHEN WHERE WHY), score snippet density to set target count, create specific research targets, save /news_input.md. Trigger keywords: gap analysis, research plan, targets, news input, planning.
---

# Planning Skill

## Critical Constraints (Read First)

- **Always run before any `linkup_search` call** — never search without a plan
- **Minimum 2 targets, maximum 6 targets** — never create 1 or more than 6
- **Never create a target for information already in the snippet** — wastes search budget
- **Each target must be one specific, answerable question** — not a vague theme

---

## Step 1 — 8-Category Gap Analysis

For the given title + snippet, check each category:

| # | Category | Question to answer |
|---|---|---|
| 1 | WHO | Who are the main and secondary actors? What are their roles/titles? |
| 2 | WHAT | What is the core event? What specific claims or actions occurred? |
| 3 | WHEN | Exact date or timeframe? Sequence of events? |
| 4 | WHERE | Location (if relevant)? |
| 5 | WHY | Context, background, why this matters? |
| 6 | OFFICIAL SOURCES | What did officials/government actually say? Press conference? |
| 7 | REACTIONS | Opposition, affected parties, expert opinions, statements? |
| 8 | FACTS | Evidence, statistics, data, documents referenced? |

Mark each category: ✅ Already answered by snippet | ❌ Missing (needs research)

---

## Step 2 — Score Snippet Density → Set Target Count

Count how many of the 8 categories are already answered by the title + snippet:

| Already answered | Target count |
|---|---|
| 5 or more | 2–3 targets |
| 3–4 | 4 targets |
| 1–2 | 5–6 targets |
| 0 | 6 targets (maximum) |

---

## Step 3 — Write Research Targets

Convert each ❌ gap into one specific, numbered target.

**Good target format:**
```
1. Find [specific minister's name]'s exact quote about [specific topic] from [specific event/date]
2. Find [party/group]'s official response to [specific claim]
3. Find exact date and location of [specific event]
```

**Bad target format (never do this):**
```
1. Research this story more
2. Find out what happened
3. Look for reactions
```

**Example transformation:**
- Gap: "Missing TTAP's rejection statement" →
- Target: `"Find TTAP's official rejection statement with specific quotes criticising Naqvi's press conference account"`

---

## Step 4 — Save to `/news_input.md`

```python
overwrite_file("/news_input.md", """# Original News Input

**Date:** [today's date]
**Title:** [exact title — copy-paste]
**Snippet:** [exact snippet — copy-paste]

## Gap Analysis
[list categories: ✅ already known / ❌ missing]

## Research Targets
1. [exact target description]
2. [exact target description]
...
""")
```
