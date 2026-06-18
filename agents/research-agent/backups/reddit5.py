#!/usr/bin/env python3
"""
Reddit Collector 2026 - Hybrid (RSS + HTML Fallback)
"""
import sys
import html
import time
import logging
import requests
from typing import List, Dict
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RedditCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def clean_html(self, text: str, max_length: int = 2000) -> str:
        if not text:
            return ""
        soup = BeautifulSoup(html.unescape(text), "html.parser")
        text = " ".join(soup.get_text().split())
        return text[:max_length]

    def get_comments_rss(self, post_url: str, max_comments: int = 20) -> List[Dict]:
        """Try RSS first, fallback to HTML"""
        try:
            # RSS attempt
            rss_url = post_url.replace('www.reddit.com', 'old.reddit.com').rstrip('/') + '/.rss'
            resp = self.session.get(rss_url, timeout=15)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.content)
                # ... (keep your previous RSS parsing if you want)
                if feed.entries:
                    logger.info("Comments via RSS succeeded")
                    # add parsing logic here if needed
        except:
            pass

        # HTML fallback (more reliable)
        try:
            comments_url = post_url.replace('www.reddit.com', 'old.reddit.com').rstrip('/') 
            resp = self.session.get(comments_url, timeout=20)
            if resp.status_code != 200:
                logger.warning(f"HTML comments failed: {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.text, 'html.parser')
            comments = []
            
            for comment in soup.select('div.comment')[:max_comments]:
                author = comment.select_one('.author')
                body = comment.select_one('.md')
                
                if author and body:
                    comments.append({
                        'author': author.get_text(strip=True),
                        'body': self.clean_html(body.get_text(), 800),
                        'published': '',
                        'link': '',
                    })
            
            logger.info(f" → Got {len(comments)} comments via HTML scrape")
            return comments
        except Exception as e:
            logger.error(f"Comment extraction failed: {e}")
            return []

    def search_with_comments(self, query: str, max_posts: int = 5, comments_per_post: int = 15) -> List[Dict]:
        results = []
        
        # Try subreddit first (more reliable)
        urls = [
            f"https://old.reddit.com/r/{query}/new/",
            f"https://old.reddit.com/search/?q={query}&sort=relevance",
        ]
        
        for base_url in urls:
            try:
                logger.info(f"Trying: {base_url}")
                resp = self.session.get(base_url, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"Status {resp.status_code}")
                    continue

                soup = BeautifulSoup(resp.text, 'html.parser')
                posts = soup.select('div.thing')[:max_posts]

                for post_elem in posts:
                    title_tag = post_elem.select_one('p.title a')
                    if not title_tag:
                        continue
                    
                    title = title_tag.get_text(strip=True)
                    link = title_tag['href']
                    if not link.startswith('http'):
                        link = 'https://old.reddit.com' + link
                    
                    subreddit = post_elem.select_one('.subreddit')
                    subreddit = subreddit.get_text(strip=True).replace('r/', '') if subreddit else "unknown"

                    logger.info(f"📄 Post: {title[:70]}...")
                    comments = self.get_comments_rss(link, comments_per_post)

                    post = {
                        'title': title,
                        'content': self.clean_html(post_elem.select_one('.md') or ""),
                        'url': link,
                        'subreddit': subreddit,
                        'comments': comments,
                        'comment_count': len(comments),
                    }
                    results.append(post)
                    time.sleep(2)  # Be gentle

                if results:
                    break
            except Exception as e:
                logger.error(f"Search failed: {e}")
                continue

        return results

if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "termux"
    max_posts = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    comments_per_post = int(sys.argv[3]) if len(sys.argv) > 3 else 10

    print(f"\n🔍 Researching: {query}")
    print(f"📊 Max posts: {max_posts}, Comments per post: {comments_per_post}")
    print("📡 Hybrid (HTML fallback)\n" + "="*80)

    collector = RedditCollector()
    results = collector.search_with_comments(query, max_posts, comments_per_post)

    total_comments = sum(p['comment_count'] for p in results)
    for i, post in enumerate(results, 1):
        print(f"\n📌 POST {i}: {post['title'][:80]}")
        print(f"   Subreddit: r/{post['subreddit']}")
        print(f"   URL: {post['url']}")
        print(f"   Comments: {post['comment_count']}")
        
        if post['comments']:
            print(f"\n   💬 First {min(3, len(post['comments']))} comments:")
            for j, c in enumerate(post['comments'][:3], 1):
                preview = c['body'][:180].replace('\n', ' ')
                print(f"   [{j}] u/{c['author']}: {preview}...")
        else:
            print("   💬 No comments (may be rate-limited)")
        print("-" * 80)

    print(f"\n📊 SUMMARY: {len(results)} posts • {total_comments} comments")
