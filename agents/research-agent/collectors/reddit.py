# collectors/reddit_simple.py - No authentication required!
import requests
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def search(query: str, max_results: int = 10):
    """
    Use Reddit's public RSS feeds (no API key needed)
    """
    try:
        # Reddit's public RSS endpoint
        url = f"https://www.reddit.com/search.rss"
        params = {
            'q': query,
            'limit': max_results,
            'sort': 'relevance',
            't': 'all'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ResearchBot/1.0)'
        }
        
        logger.info(f"Searching Reddit RSS for: {query}")
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.warning(f"Reddit RSS returned {response.status_code}")
            return []
        
        # Parse RSS XML
        import feedparser
        feed = feedparser.parse(response.content)
        
        posts = []
        for entry in feed.entries[:max_results]:
            # Extract subreddit from link
            link_parts = entry.link.split('/')
            subreddit = link_parts[4] if len(link_parts) > 4 else 'unknown'
            
            posts.append({
                'title': entry.title,
                'content': entry.summary[:1000] if hasattr(entry, 'summary') else entry.title,
                'url': entry.link,
                'source': f"r/{subreddit}",
                'published': entry.published if hasattr(entry, 'published') else '',
                'query': query,
                'collector': 'reddit'
            })
        
        logger.info(f"Found {len(posts)} Reddit posts via RSS")
        return posts
        
    except Exception as e:
        logger.error(f"Reddit RSS error: {e}")
        return []

if __name__ == "__main__":
    results = search("termux", max_results=5)
    for i, post in enumerate(results, 1):
        print(f"\n[{i}] {post['title']}")
        print(f"    Subreddit: {post['source']}")
        print(f"    URL: {post['url']}")
