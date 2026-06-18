#!/usr/bin/env python3
"""
Reddit Collector - Hybrid Version
- RSS for fast search (works!)
- Selective JSON enrichment for author/score/comments
"""

import sys
import html
import time
import logging
import requests
import feedparser
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RedditCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def clean_html(self, text: str) -> str:
        if not text:
            return ""
        soup = BeautifulSoup(html.unescape(text), "html.parser")
        return " ".join(soup.get_text().split())

    def enrich_post(self, url: str) -> Dict[str, Any]:
        """Get author/score/comments from JSON endpoint"""
        try:
            # Try different URL patterns
            json_urls = [
                url.rstrip('/') + '.json',
                url.replace('old.reddit.com', 'www.reddit.com').rstrip('/') + '.json',
                url.replace('old.reddit.com', 'reddit.com').rstrip('/') + '.json'
            ]
            
            for json_url in json_urls:
                try:
                    response = self.session.get(json_url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        if data and isinstance(data, list) and data[0].get('data', {}).get('children'):
                            post_data = data[0]['data']['children'][0]['data']
                            return {
                                "author": post_data.get('author', ''),
                                "score": post_data.get('score', 0),
                                "comments": post_data.get('num_comments', 0),
                                "content": self.clean_html(post_data.get('selftext', '')[:2000])
                            }
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"Enrich failed: {e}")
        
        return {"author": "", "score": 0, "comments": 0, "content": ""}

    def search(self, query: str, max_results: int = 10, enrich_top_n: int = 3) -> List[Dict]:
        """Search using old Reddit RSS + selective enrichment"""
        
        url = "https://old.reddit.com/search.rss"
        params = {"q": query, "sort": "relevance", "limit": max_results}
        
        try:
            response = self.session.get(url, params=params, timeout=15)
            if response.status_code != 200:
                logger.error(f"RSS failed: {response.status_code}")
                return []
            
            feed = feedparser.parse(response.content)
            results = []
            
            for idx, entry in enumerate(feed.entries):
                link = getattr(entry, "link", "")
                if "/comments/" not in link:
                    continue
                
                # Extract subreddit
                subreddit = "unknown"
                try:
                    parts = link.split("/")
                    if "r" in parts:
                        subreddit = parts[parts.index("r") + 1]
                except:
                    pass
                
                # Basic post from RSS
                post = {
                    "title": getattr(entry, "title", ""),
                    "url": link,
                    "subreddit": subreddit,
                    "published": getattr(entry, "published", ""),
                    "summary": self.clean_html(getattr(entry, "summary", "")[:500]),
                    "author": "",
                    "score": 0,
                    "comments": 0,
                    "content": ""
                }
                
                # Enrich top N posts
                if idx < enrich_top_n:
                    enriched = self.enrich_post(link)
                    post.update(enriched)
                    logger.info(f"Enriched post {idx+1}: author={enriched.get('author')}, score={enriched.get('score')}")
                    time.sleep(1)  # Rate limit
                else:
                    post["content"] = post["summary"]
                
                results.append(post)
                
                if len(results) >= max_results:
                    break
            
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "termux"
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    enrich = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    
    collector = RedditCollector()
    results = collector.search(query, max_results, enrich_top_n=enrich)
    
    print(f"\n🔍 Found {len(results)} posts for '{query}'\n")
    print("=" * 80)
    
    for i, post in enumerate(results, 1):
        print(f"\n[{i}] {post['title'][:70]}")
        print(f"    Subreddit: r/{post['subreddit']}")
        print(f"    Author   : {post['author'] or '(not enriched)'}")
        print(f"    Score    : {post['score']}")
        print(f"    Comments : {post['comments']}")
        print(f"    URL      : {post['url']}")
        
        content = post.get('content', post.get('summary', ''))[:200]
        if content:
            print(f"    Content  : {content}...")
        print("-" * 80)
