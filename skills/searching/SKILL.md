---
name: searching
description: Use when calling linkup_search to find news information. Covers query writing rules, topic routing (news/general/finance), per-round procedure, and budget management. Trigger keywords: web search, linkup, search query, news research, keyword search, find information.
---

# Searching Skill

## Critical Constraints (Read First)

- **Maximum 3 `linkup_search` calls total per article** — budget is hard
- **Never pre-plan all 3 queries upfront** — write each query only after seeing previous results
- **Always use `think_tool` before AND after each search** — see thinking skill
- **Never use quotes, question marks, or full sentences in queries** — keyword strings only

---

## Query Writing Rules

Think like a news search power user. Linkup works best with short, noun-dense keyword strings.

| Rule | Good | Bad |
|---|---|---|
| Length | 4–8 keywords | 10+ keywords dilute relevance |
| Format | raw keyword string | quoted phrase or question |
| Recency | include year `2026` or month | no time signal |
| Names | exact proper nouns as in news | abbreviations or nicknames |
| Separators | spaces only | AND / OR / + / commas |

**GOOD queries:**
```
Pakistan IMF EFF policy stabilize economy 2026
TTAP rejection Naqvi Imran Khan medical exam 2026
Imran Khan eye surgery Adiala Jail update March 2026
```

**BAD queries:**
```
"What did TTAP say about the medical examination?"
IMF spokesperson Pakistan Extended Fund Facility EFF statement stabilize
find Aleema Khan reaction to the medical exam controversy
```

---

## Topic Routing

Choose the correct `topic` parameter before calling:

| Target type | Topic |
|---|---|
| Breaking event, statement, reaction, press conference | `"news"` |
| Background, history, concept, location explained | `"general"` |
| Financial figures, economic data, fund amounts, markets | `"finance"` |

**Default:** use `"news"` for Pakistani political/social stories if in doubt.

If one search must cover multiple target types, use the topic of the **highest-priority remaining target**.

---

## Per-Round Procedure

```
Round N:
1. [think_tool] → plan query (see thinking skill)
2. linkup_search(query="[4-8 keywords]", topic="[news/general/finance]")
3. [think_tool] → evaluate, update statuses, pick extraction URLs
4. tavily_extract(...) if needed (see link-extracting skill)
5. [think_tool] → final status update, decide next action
```

---

## Budget Table

| Action | Limit | Notes |
|---|---|---|
| `linkup_search` | max 3 | Hard limit — stop at 3 regardless |
| `tavily_extract` | max 3 (1/round) | Max 2 URLs per call |
| Exit early | anytime | Stop the moment all targets are ✅ |

---

## One Example: Full Round

**Targets:** Find Naqvi's press conference quote, TTAP rejection statement

**Round 1 pre-search think_tool:**
> "No queries run yet. Both targets unsatisfied. Query: `Naqvi TTAP Imran Khan medical exam statement 2026` covers both in one search. Topic: news."

**Round 1 search:**
```python
linkup_search(query="Naqvi TTAP Imran Khan medical exam statement 2026", topic="news")
```

**Round 1 post-search think_tool:**
> "Found Naqvi's quote from Dawn. Target 1 ✅. TTAP rejection mentioned but no direct quote. Geo TV snippet hints at statement. Extract geo.tv URL. Target 2 ⚠️."
