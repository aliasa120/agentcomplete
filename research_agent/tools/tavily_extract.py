"""Tavily Extract tool — reads full content from chosen URLs."""

import os
from typing import List

from langchain_core.tools import tool
from tavily import TavilyClient

@tool(parse_docstring=True)
def tavily_extract(urls: List[str], query: str = "") -> str:
    """Extract full article content from up to 2 credible URLs.

    Use this tool AFTER a linkup_search when the search snippets are too short to
    fully answer one or more research targets.  Read the actual article and get
    richer, longer context that the snippet could not provide.

    When to use:
    - A search result snippet strongly hints the page has the answer, but the
      snippet is cut off and you need the complete quote, date, or detail.
    - One or more research targets are Partially Complete after think_tool analysis.
    - You have already identified 1-2 credible URLs (Dawn, Geo, Al Jazeera,
      Reuters, BBC, etc.) whose snippets are already on-topic.

    When NOT to use:
    - All targets are already Complete after the search + think_tool step.
    - You are guessing — only send URLs whose snippets already show relevance.
    - You already read 2 URLs in this research round (max 2 URLs per round).

    Args:
        urls: List of 1-2 URLs to extract.  Pick only credible news outlets whose
              snippets already show on-topic content.  Maximum 2 URLs per call.
        query: Optional keyword string matching your current search query.  When
               provided, Tavily reranks the extracted content chunks so the most
               relevant passages appear first.  Use the same keyword string you
               used for linkup_search.

    Returns:
        Extracted markdown content for each URL, separated by a divider.
        Failed URLs are reported with an error message.
    """
    _tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY", ""))
    # Enforce the 2-URL cap at the tool level so the agent cannot accidentally
    # exceed the budget even if the prompt guard fails.
    urls = urls[:2]

    params: dict = {
        "urls": urls,
        "extract_depth": "basic",
        "format": "markdown",
    }
    if query:
        params["query"] = query
        params["chunks_per_source"] = 5

    response = _tavily_client.extract(**params)

    sections: list[str] = []

    for result in response.get("results", []):
        url = result.get("url", "")
        content = result.get("raw_content", "").strip()
        sections.append(f"### Extracted: {url}\n\n{content}")

    for failure in response.get("failed_results", []):
        url = failure.get("url", "")
        error = failure.get("error", "unknown error")
        sections.append(f"### Failed: {url}\n\nError: {error}")

    return "\n\n---\n\n".join(sections) if sections else "No content extracted."
