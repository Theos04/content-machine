import sys
from collectors.wikipedia import get_wikipedia
from collectors.web import extract_article
from collectors.reddit import search_reddit
from collectors.news import fetch_news_rss
from collectors.arxiv import search_arxiv
from database.db import ResearchDB
from processors.text_utils import extract_keywords, extractive_summary
from processors.graphs import graph  # your networkx graph

def main(query):
    db = ResearchDB()
    print(f"Researching: {query}")

    # 1. Wikipedia
    wiki_data = get_wikipedia(query)
    if wiki_data:
        db.add_source("Wikipedia", query)
        # store article
        print("[+] Wikipedia article found")

    # 2. Reddit
    reddit_posts = search_reddit(query)
    print(f"[+] Found {len(reddit_posts)} Reddit posts")

    # 3. News
    news = fetch_news_rss(query)
    print(f"[+] Found {len(news)} news articles")

    # 4. arXiv (if academic topic)
    if any(term in query.lower() for term in ["paper", "research", "model", "algorithm"]):
        papers = search_arxiv(query)
        print(f"[+] Found {len(papers)} arXiv papers")

    # For each article, extract full text, summarize, store
    # ... (implement loop over URLs, call extract_article, store in DB)

    # Build knowledge graph: add edges from keywords
    # For example, connect entities that co-occur

    # Finally, generate report (print or save to file)

if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]) or "artificial intelligence"
    main(topic)
