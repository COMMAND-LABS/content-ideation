"""Keywords with exactly the same search history are variants Google counts together ("ai agent", "ai agents").

The LLM steps show the LLM one line per group, and put the variants back afterwards.
"""


def variant_groups(keywords: list[dict]) -> dict[str, list[str]]:
    """First keyword -> every keyword of its group, the most searched group first."""
    groups = {}
    for row in sorted(keywords, key=lambda row: row["avg_monthly_searches"], reverse=True):
        same_searches = tuple(sorted(row["monthly_searches"].items())) if row["avg_monthly_searches"] else row["keyword"]  # no searches: nothing to compare
        groups.setdefault(same_searches, []).append(row["keyword"])
    return {group[0]: group for group in groups.values()}


def keyword_lines(groups: dict[str, list[str]], keywords: list[dict]) -> str:
    """The keywords as the LLM reads them: one line per variant group."""
    searches = {row["keyword"]: row["avg_monthly_searches"] for row in keywords}
    return "\n".join(
        f"- {first} | {searches[first]:,} a month" + (f" | also searched as: {', '.join(group[1:])}" if len(group) > 1 else "")
        for first, group in groups.items()
    )


def with_variants(picked: list[str], groups: dict[str, list[str]], taken: set[str]) -> list[str]:
    """The LLM's picks plus their variants: no invented keywords, and no keyword in two topics."""
    keywords = []
    for keyword in picked:
        if keyword in groups and keyword not in taken:
            taken.add(keyword)
            keywords += groups[keyword]
    return keywords
