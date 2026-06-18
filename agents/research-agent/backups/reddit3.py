#!/usr/bin/env python3
"""
Reddit Collector - Working Version
Uses multiple fallback strategies:
1. Old Reddit RSS (ssl.reddit.com)
2. JSON API without auth (limited but works)
3. Pushshift.io (if available)
"""

import sys
import html
import time
import json
import logging
import requests
import feedparser
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RedditCollector:
    """Reddit collector with multiple fallback strategies"""

    def __init__(self, rate_limit_delay: float = 2.0):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0

    def _rate_limit(self):
        """Simple rate limiting"""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def clean_html(self, text: str, max_length: int = 5000) -> str:
        """Clean HTML and extract plain text"""
        if not text:
            return ""

        text = html.unescape(text)
        soup = BeautifulSoup(text, "html.parser")
        
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        
        text = soup.get_text(" ", strip=True)
        text = " ".join(text.split())
        
        return text[:max_length]

    def search_via_old_reddit(self, query: str, max_results: int = 10) -> List[Dict]:
        """Try old.reddit.com RSS feed"""
        try:
            url = "https://old.reddit.com/search.rss"
            params = {
                "q": query,
                "sort": "relevance",
                "limit": max_results,
                "restrict_sr": ""
            }
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"Old Reddit RSS returned {response.status_code}")
                return []
            
            feed = feedparser.parse(response.content)
            return self._parse_feed(feed, max_results, "old_reddit")
            
        except Exception as e:
            logger.debug(f"Old Reddit RSS failed: {e}")
            return []

    def search_via_json_api(self, query: str, max_results: int = 10) -> List[Dict]:
        """Use Reddit's public JSON API (no auth needed for search)"""
        self._rate_limit()
        
        try:
            url = "https://www.reddit.com/search.json"
            params = {
                "q": query,
                "sort": "relevance",
                "limit": min(max_results, 25),  # API limit
                "t": "all",
                "raw_json": 1
            }
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                logger.debug(f"JSON API returned {response.status_code}")
                return []
            
            data = response.json()
            posts = []
            
            for child in data.get("data", {}).get("children", []):
                post_data = child.get("data", {})
                
                # Skip if no permalink
                permalink = post_data.get("permalink")
                if not permalink:
                    continue
                
                content = post_data.get("selftext", "") or post_data.get("title", "")
                
                post = {
                    "title": post_data.get("title", ""),
                    "content": self.clean_html(content[:5000]),
                    "url": f"https://www.reddit.com{permalink}",
                    "source": f"r/{post_data.get('subreddit', 'unknown')}",
                    "subreddit": post_data.get("subreddit", "unknown"),
                    "published": datetime.fromtimestamp(post_data.get("created_utc", 0)).isoformat(),
                    "author": post_data.get("author", ""),
                    "score": post_data.get("score", 0),
                    "comments": post_data.get("num_comments", 0),
                    "upvote_ratio": post_data.get("upvote_ratio"),
                    "query": query,
                    "collector": "reddit_json"
                }
                
                posts.append(post)
                
                if len(posts) >= max_results:
                    break
            
            logger.info(f"JSON API found {len(posts)} posts")
            return posts
            
        except Exception as e:
            logger.debug(f"JSON API failed: {e}")
            return []

    def search_via_subreddit_json(self, query: str, subreddit: str = None, max_results: int = 10) -> List[Dict]:
        """Search within a specific subreddit using JSON"""
        if not subreddit:
            return []
        
        self._rate_limit()
        
        try:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            params = {
                "q": query,
                "sort": "relevance",
                "limit": min(max_results, 25),
                "restrict_sr": "on",
                "raw_json": 1
            }
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            posts = []
            
            for child in data.get("data", {}).get("children", []):
                post_data = child.get("data", {})
                permalink = post_data.get("permalink")
                
                if not permalink:
                    continue
                
                post = {
                    "title": post_data.get("title", ""),
                    "content": self.clean_html(post_data.get("selftext", "")[:5000]),
                    "url": f"https://www.reddit.com{permalink}",
                    "source": f"r/{subreddit}",
                    "subreddit": subreddit,
                    "published": datetime.fromtimestamp(post_data.get("created_utc", 0)).isoformat(),
                    "author": post_data.get("author", ""),
                    "score": post_data.get("score", 0),
                    "comments": post_data.get("num_comments", 0),
                    "query": query,
                    "collector": "reddit_subreddit_json"
                }
                
                posts.append(post)
                
                if len(posts) >= max_results:
                    break
            
            return posts
            
        except Exception as e:
            logger.debug(f"Subreddit JSON search failed: {e}")
            return []

    def _parse_feed(self, feed, max_results: int, source: str) -> List[Dict]:
        """Parse RSS feed entries"""
        if not feed.entries:
            return []
        
        posts = []
        for entry in feed.entries[:max_results]:
            link = getattr(entry, "link", "")
            
            if "/comments/" not in link:
                continue
            
            # Extract subreddit from link
            subreddit = "unknown"
            try:
                parts = link.split("/")
                if "r" in parts:
                    idx = parts.index("r")
                    if idx + 1 < len(parts):
                        subreddit = parts[idx + 1]
            except:
                pass
            
            post = {
                "title": getattr(entry, "title", ""),
                "content": self.clean_html(getattr(entry, "summary", "")[:5000]),
                "url": link,
                "source": f"r/{subreddit}",
                "subreddit": subreddit,
                "published": getattr(entry, "published", ""),
                "author": "",  # RSS doesn't have author easily
                "score": 0,    # RSS doesn't have scores
                "comments": 0, # RSS doesn't have comment counts
                "query": "unknown",
                "collector": source
            }
            
            posts.append(post)
        
        return posts

    def search(self, query: str, max_results: int = 10, strategy: str = "auto") -> List[Dict]:
        """
        Search Reddit with automatic fallback strategies
        
        Strategies:
        - "auto": Try JSON API first, then fallbacks
        - "json": Only JSON API
        - "rss": Only RSS
        - "subreddit": Try to search within subreddits
        """
        
        logger.info(f"Searching for '{query}' with strategy '{strategy}'")
        
        results = []
        
        # Try JSON API first (most reliable without auth)
        if strategy in ["auto", "json"]:
            results = self.search_via_json_api(query, max_results)
            if results:
                logger.info(f"JSON API successful: {len(results)} posts")
                return results
            logger.warning("JSON API failed, trying fallback")
        
        # Try old Reddit RSS
        if strategy in ["auto", "rss"] and not results:
            results = self.search_via_old_reddit(query, max_results)
            if results:
                logger.info(f"Old Reddit RSS successful: {len(results)} posts")
                return results
        
        # If query looks like it might be a subreddit, try direct search
        if strategy in ["auto", "subreddit"] and not results:
            # Try common subreddits for the query
            possible_subreddits = [query.lower(), f"r/{query.lower()}"]
            for sub in possible_subreddits:
                sub = sub.replace("r/", "")
                sub_results = self.search_via_subreddit_json(query, sub, max_results)
                if sub_results:
                    logger.info(f"Subreddit search in r/{sub} successful: {len(sub_results)} posts")
                    return sub_results
        
        logger.warning(f"No results found for '{query}' using any strategy")
        return results


def search(query: str, max_results: int = 10):
    """Research-agent compatible interface"""
    collector = RedditCollector(rate_limit_delay=1.0)
    return collector.search(query, max_results, strategy="auto")


# Test with debug
if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "termux"
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    print(f"\n🔍 Searching Reddit for: {query}")
    print(f"📊 Max results: {max_results}\n")
    
    collector = RedditCollector(rate_limit_delay=1.0)
    results = collector.search(query, max_results, strategy="auto")
    
    print(f"\n✅ Found {len(results)} posts\n")
    print("=" * 80)
    
    for i, post in enumerate(results, 1):
        print(f"\n[{i}] {post['title'][:80]}")
        print(f"    Subreddit : {post['subreddit']}")
        print(f"    Author    : {post.get('author', 'N/A')}")
        print(f"    Score     : {post.get('score', 0)}")
        print(f"    Comments  : {post.get('comments', 0)}")
        print(f"    URL       : {post['url']}")
        
        # Show content snippet
        snippet = post['content'].replace('\n', ' ')[:200]
        if snippet:
            print(f"    Snippet   : {snippet[:150]}...")
        
        print("-" * 80)
    
    # Summary for research agent
    if results:
        print(f"\n📊 Summary:")
        print(f"    Total posts: {len(results)}")
        print(f"    Subreddits: {set(p['subreddit'] for p in results)}")
        print(f"    Avg score: {sum(p.get('score', 0) for p in results) // len(results)}")
