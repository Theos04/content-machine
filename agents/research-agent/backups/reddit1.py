#!/usr/bin/env python3
"""
Reddit Collector
No OAuth required.
Uses Reddit RSS search feeds.
"""

import sys
import logging
import requests
import feedparser
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

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search Reddit using RSS feeds.
        """

        try:
            logger.info(f"Searching Reddit RSS for: {query}")

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
                    f"Reddit returned status {response.status_code}"
                )
                return []

            feed = feedparser.parse(response.content)

            if not feed.entries:
                logger.warning(f"No Reddit results found for '{query}'")
                return []

            posts = []

            for entry in feed.entries:

                # Keep only actual posts
                if "/comments/" not in entry.link:
                    continue

                subreddit = self._extract_subreddit(entry.link)

                posts.append({
                    "title": getattr(entry, "title", ""),
                    "content": getattr(entry, "summary", "")[:2000],
                    "url": entry.link,
                    "source": f"r/{subreddit}",
                    "published": getattr(entry, "published", ""),
                    "query": query,
                    "collector": "reddit"
                })

                if len(posts) >= max_results:
                    break

            logger.info(f"Found {len(posts)} Reddit posts")

            return posts

        except Exception as e:
            logger.exception(f"Reddit search failed: {e}")
            return []

    def get_post_text(self, reddit_url: str) -> str:
        """
        Fetch full selftext using Reddit JSON endpoint.
        """

        try:

            json_url = reddit_url.rstrip("/") + ".json"

            response = self.session.get(
                json_url,
                timeout=15
            )

            if response.status_code != 200:
                return ""

            data = response.json()

            if not isinstance(data, list):
                return ""

            return (
                data[0]["data"]["children"][0]["data"]
                .get("selftext", "")
            )

        except Exception:
            return ""

    @staticmethod
    def _extract_subreddit(url: str) -> str:
        """
        Extract subreddit name from URL.
        """

        try:
            parts = url.split("/")

            if "r" in parts:
                idx = parts.index("r")

                if idx + 1 < len(parts):
                    return parts[idx + 1]

        except Exception:
            pass

        return "unknown"


def search(query: str, max_results: int = 10):
    """
    Compatibility wrapper for existing research-agent.
    """

    collector = RedditCollector()

    return collector.search(
        query=query,
        max_results=max_results
    )


if __name__ == "__main__":

    query = sys.argv[1] if len(sys.argv) > 1 else "termux"

    max_results = (
        int(sys.argv[2])
        if len(sys.argv) > 2
        else 10
    )

    results = search(
        query=query,
        max_results=max_results
    )

    print(f"\nFound {len(results)} posts\n")

    for i, post in enumerate(results, 1):

        print(f"[{i}] {post['title']}")
        print(f"Subreddit : {post['source']}")
        print(f"Published : {post['published']}")
        print(f"URL       : {post['url']}")

        if post["content"]:
            snippet = (
                post["content"]
                .replace("\n", " ")
                .replace("\r", " ")
            )

            print(f"Snippet   : {snippet[:200]}")

        print("-" * 80)

