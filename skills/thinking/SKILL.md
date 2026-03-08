---
name: thinking
description: Use think_tool for strategic reflection. Mandatory after every linkup_search and tavily_extract — no exceptions. Use before each new search to plan the next query. Trigger keywords: reflect, think, evaluate results, plan query, research progress, analyze findings.
---

# Thinking Skill

## Critical Constraints (Read First)

- **`think_tool` is mandatory after EVERY `linkup_search`** — no exceptions
- **`think_tool` is mandatory after EVERY `tavily_extract`** — no exceptions
- **`think_tool` is mandatory BEFORE each new search round** — to plan the query
- **Never skip** even if results are clearly complete — still confirm with think_tool

---

## When to Call `think_tool`

| Moment | Purpose |
|---|---|
| Before Round 1, 2, 3 | Plan which query to run next |
| After each `linkup_search` | Evaluate results, update target statuses |
| After each `tavily_extract` | Update targets with extracted content |
| Before stopping | Confirm ALL targets are truly Complete |

---

## Pre-Search Reflection Template

```
QUERY PLANNING
==============
Queries already executed:
  Round 1: [exact query string] → topic=[news/general/finance]
  Round 2: [exact query string or "none yet"]
  Round 3: [exact query string or "none yet"]

Targets still incomplete:
  Target 2: [description] — missing: [specific quote/date/location]
  Target 4: [description] — status: Partially Complete

Next query:
  [4-8 keyword string, no quotes, no question mark]
  Reasoning: [why this query covers the remaining gaps]
  NOT a duplicate of: [confirm differs from previous queries]
```

---

## Post-Search Reflection Template

```
SEARCH RESULTS EVALUATION
=========================
Query run: "[exact query string]"
Results quality: [strong / mixed / weak]

Target updates:
  Target 1 → ✅ Complete: [specific fact found + source URL]
  Target 2 → ⚠️ Partial: [what was found, what's still missing]
  Target 3 → ❌ Not Found: [why — no results, wrong angle, etc.]

URL extraction candidates:
  [outlet name]: [URL] — snippet hints at [target X missing detail]
  [outlet name]: [URL] — snippet hints at [target Y]

Decision:
  → Extract [URL1, URL2] to get detail for Target 2
  OR → All complete, early exit now
  OR → Run Round N next, targeting [what's still missing]
```

---

## Post-Extract Reflection Template

```
EXTRACTION RESULTS EVALUATION
==============================
URLs extracted: [url1], [url2]
URL1 result: [rich / thin / failed]
URL2 result: [rich / thin / failed]

Target updates:
  Target 2 → ✅ Complete: [quote found: "exact words" — source: outlet]
  Target 3 → still ⚠️ Partial: [what's still missing]

Decision:
  → [X] of [Y] targets complete
  → [Continue to Round N / Early exit / Accept partial]
```

---

## Query Uniqueness Rule

Before writing the next query, read through all previous queries. The new query MUST differ in at least 2 keywords. If the obvious query is too similar:
- Use a different person's name from the same story
- Target a different angle (timeline vs. quote vs. reaction)
- Shift from an actor to the event, or vice versa

**Example:**
- Round 1: `TTAP rejection Naqvi Imran Khan medical exam 2026`
- Round 2 (if still incomplete): `Aleema Khan statement Adiala medical access latest` ← different person, different angle
