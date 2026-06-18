#!/usr/bin/env python3

import sys
import re
import html
import time
import logging
import requests
from pathlib import Path
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RedditCollector:

    def __init__(self):
        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.google.com/",
            "DNT": "1",
        })

    def fetch(self, url, filename):
        logger.info(f"Fetching: {url}")

        try:
            r = self.session.get(
                url,
                timeout=30,
                allow_redirects=True
            )

            logger.info(f"Status: {r.status_code}")

            Path(filename).write_text(
                r.text,
                encoding="utf-8"
            )

            logger.info(
                f"Saved: {filename} "
                f"({len(r.text):,} bytes)"
            )

            return r.text

        except Exception as e:
            logger.error(e)
            return None

    def analyze_html(self, html_text):

        print("\n" + "=" * 80)
        print("HTML ANALYSIS")
        print("=" * 80)

        print(f"Length: {len(html_text):,} bytes")

        markers = {
            "shreddit-post":
                html_text.count("shreddit-post"),

            "/comments/":
                html_text.count("/comments/"),

            "whoa there, pardner":
                html_text.lower().count(
                    "whoa there, pardner"
                ),

            "blocked":
                html_text.lower().count("blocked"),

            "reddit":
                html_text.lower().count("reddit"),
        }

        for k, v in markers.items():
            print(f"{k:25} {v}")

        print()

        comment_links = re.findall(
            r'/r/[^"\']+/comments/[^"\']+',
            html_text
        )

        comment_links = list(dict.fromkeys(comment_links))

        print(
            f"Unique comment URLs found: "
            f"{len(comment_links)}"
        )

        for link in comment_links[:20]:
            print(link)

        print()

        return comment_links

    def extract_posts(self, html_text, max_posts=10):

        soup = BeautifulSoup(
            html.unescape(html_text),
            "html.parser"
        )

        posts = []

        # Method 1
        for tag in soup.find_all("shreddit-post"):

            title = (
                tag.get("post-title")
                or tag.get("title")
                or ""
            )

            url = tag.get("permalink", "")

            if title:

                posts.append({
                    "title": title,
                    "url": url
                })

        # Method 2
        if not posts:

            for a in soup.find_all("a", href=True):

                href = a["href"]

                if "/comments/" not in href:
                    continue

                title = (
                    a.get_text(" ", strip=True)
                    .replace("\n", " ")
                )

                if len(title) < 10:
                    continue

                posts.append({
                    "title": title,
                    "url": href
                })

        return posts[:max_posts]

    def run(self, query, max_posts=5):

        urls = [
            (
                f"https://www.reddit.com/r/{query}/",
                "reddit_subreddit.html"
            ),
            (
                f"https://www.reddit.com/search/?q={query}",
                "reddit_search.html"
            ),
        ]

        all_posts = []

        for url, filename in urls:

            html_text = self.fetch(url, filename)

            if not html_text:
                continue

            links = self.analyze_html(html_text)

            posts = self.extract_posts(
                html_text,
                max_posts
            )

            if posts:
                all_posts.extend(posts)

            time.sleep(2)

        return all_posts


def main():

    query = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "termux"
    )

    max_posts = (
        int(sys.argv[2])
        if len(sys.argv) > 2
        else 5
    )

    print(f"\n🔍 Query: {query}")
    print(f"📊 Max posts: {max_posts}")

    collector = RedditCollector()

    posts = collector.run(
        query=query,
        max_posts=max_posts
    )

    print("\n" + "=" * 80)
    print("POSTS FOUND")
    print("=" * 80)

    if not posts:
        print("No posts extracted.")
        print("\nCheck:")
        print("reddit_subreddit.html")
        print("reddit_search.html")
        return

    for i, post in enumerate(posts, 1):

        print(f"\n[{i}] {post['title']}")
        print(post['url'])

    print(
        f"\nTotal extracted: "
        f"{len(posts)}"
    )


if __name__ == "__main__":
    main()
