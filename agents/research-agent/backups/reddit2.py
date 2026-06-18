#!/usr/bin/env python3
"""
Reddit Collector
No OAuth required.

Features:
- RSS search
- HTML cleanup
- Full post extraction via .json
- Score/comments/author extraction
- Research-agent compatible
"""

import sys
import html
import logging
import requests
import feedparser

from bs4 import BeautifulSoup
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RedditCollector:

    def __init__(self):

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        })

    # ---------------------------------------------------------
    # HTML Cleanup
    # ---------------------------------------------------------

    def clean_html(self, text: str) -> str:

        if not text:
            return ""

        text = html.unescape(text)

        soup = BeautifulSoup(text, "html.parser")

        text = soup.get_text(" ", strip=True)

        return " ".join(text.split())

    # ---------------------------------------------------------
    # Subreddit Extraction
    # ---------------------------------------------------------

    def extract_subreddit(self, url: str) -> str:

        try:

            parts = url.split("/")

            if "r" in parts:

                idx = parts.index("r")

                if idx + 1 < len(parts):
                    return parts[idx + 1]

        except Exception:
            pass

        return "unknown"

    # ---------------------------------------------------------
    # Full Post JSON
    # ---------------------------------------------------------

    def get_post_details(self, url: str) -> Dict[str, Any]:

        try:

            json_url = url.rstrip("/") + ".json"

            response = self.session.get(
                json_url,
                timeout=15
            )

            if response.status_code != 200:
                return {}

            data = response.json()

            if not isinstance(data, list):
                return {}

            post_data = (
                data[0]
                ["data"]
                ["children"][0]
                ["data"]
            )

            return {
                "content": post_data.get("selftext", ""),
                "author": post_data.get("author", ""),
                "score": post_data.get("score", 0),
                "comments": post_data.get(
                    "num_comments",
                    0
                ),
                "upvote_ratio": post_data.get(
                    "upvote_ratio",
                    None
                )
            }

        except Exception:
            return {}

    # ---------------------------------------------------------
    # RSS Search
    # ---------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:

        logger.info(
            f"Searching Reddit RSS for: {query}"
        )

        results = []

        try:

            url = "https://www.reddit.com/search.rss"

            params = {
                "q": query,
                "sort": "relevance",
                "limit": max_results,
                "t": "all"
            }

            response = self.session.get(
                url,
                params=params,
                timeout=15
            )

            if response.status_code != 200:

                logger.warning(
                    f"Reddit returned status "
                    f"{response.status_code}"
                )

                return []

            feed = feedparser.parse(
                response.content
            )

            if not feed.entries:

                logger.warning(
                    f"No results found for '{query}'"
                )

                return []

            for entry in feed.entries:

                link = getattr(
                    entry,
                    "link",
                    ""
                )

                # Ignore subreddit pages
                if "/comments/" not in link:
                    continue

                title = getattr(
                    entry,
                    "title",
                    ""
                )

                summary = self.clean_html(
                    getattr(
                        entry,
                        "summary",
                        ""
                    )
                )

                subreddit = self.extract_subreddit(
                    link
                )

                details = self.get_post_details(
                    link
                )

                content = (
                    details.get("content")
                    or summary
                )

                post = {

                    "title": title,

                    "content": content[:10000],

                    "url": link,

                    "source": f"r/{subreddit}",

                    "subreddit": subreddit,

                    "published": getattr(
                        entry,
                        "published",
                        ""
                    ),

                    "author": details.get(
                        "author",
                        ""
                    ),

                    "score": details.get(
                        "score",
                        0
                    ),

                    "comments": details.get(
                        "comments",
                        0
                    ),

                    "upvote_ratio": details.get(
                        "upvote_ratio"
                    ),

                    "query": query,

                    "collector": "reddit"
                }

                results.append(post)

                if len(results) >= max_results:
                    break

            logger.info(
                f"Found {len(results)} Reddit posts"
            )

            return results

        except Exception as e:

            logger.exception(
                f"Reddit search failed: {e}"
            )

            return []


# ---------------------------------------------------------
# Research-Agent Compatibility
# ---------------------------------------------------------

def search(
    query: str,
    max_results: int = 10
):

    collector = RedditCollector()

    return collector.search(
        query=query,
        max_results=max_results
    )


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

if __name__ == "__main__":

    query = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "termux"
    )

    max_results = (
        int(sys.argv[2])
        if len(sys.argv) > 2
        else 10
    )

    collector = RedditCollector()

    results = collector.search(
        query=query,
        max_results=max_results
    )

    print(
        f"\nFound {len(results)} posts\n"
    )

    for i, post in enumerate(
        results,
        start=1
    ):

        print(f"[{i}] {post['title']}")

        print(
            f"Subreddit : "
            f"{post['subreddit']}"
        )

        print(
            f"Author    : "
            f"{post['author']}"
        )

        print(
            f"Score     : "
            f"{post['score']}"
        )

        print(
            f"Comments  : "
            f"{post['comments']}"
        )

        print(
            f"Published : "
            f"{post['published']}"
        )

        print(
            f"URL       : "
            f"{post['url']}"
        )

        snippet = (
            post["content"]
            .replace("\n", " ")
            .replace("\r", " ")
        )

        print(
            f"Content   : "
            f"{snippet[:300]}"
        )

        print("-" * 80)
