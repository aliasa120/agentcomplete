"""Linkup search tool."""

import os
from datetime import date, timedelta

from langchain_core.tools import InjectedToolArg, tool
from linkup import LinkupClient
from typing_extensions import Annotated

linkup_client = LinkupClient(api_key=os.environ.get("LINKUP_API_KEY", ""))


@tool(parse_docstring=True)
def linkup_search(
    query: str,
    depth: Annotated[str, InjectedToolArg] = "standard",
) -> str:
    """Search the web for current news and information on a given topic.

    Uses Linkup agentic search to retrieve sourced, factual answers with inline
    citations. Optimised for news research and current events.

    Query writing rules (CRITICAL):
    - Write as a short, specific keyword string (4-8 words). NO quotes around query.
    - Include the year (e.g. 2026) and/or month for recency on current events.
    - Use proper nouns, acronyms, and official names exactly as they appear in news.
    - Good: Pakistan IMF EFF statement Kozack February 2026
    - Bad:  "Find the IMF spokesperson's statement about Pakistan's Extended Fund Facility"

    Args:
        query: Keyword-dense search string (4-8 words). No quotes. Include year for recency.
        depth: Search depth - 'standard' (fast, single pass) or 'deep' (thorough). Default: standard.

    Returns:
        Sourced answer with inline citations and source URLs.
    """
    response = linkup_client.search(
        query=query,
        depth=depth,
        output_type="sourcedAnswer",
        include_images=True,
        include_inline_citations=False,
    )

    return str(response)
