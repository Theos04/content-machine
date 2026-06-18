import sys
from typing import List, Dict, Any
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import collectors
collectors = {}
collector_names = ['wikipedia', 'web', 'reddit', 'news', 'arxiv', 'youtube', 'google']

for name in collector_names:
    try:
        module = __import__(f"collectors.{name}", fromlist=[''])
        collectors[name] = module
    except ImportError as e:
        logger.warning(f"Could not import {name}: {e}")

from database.db import ResearchDB

# Processors
try:
    from processors.text_utils import extract_keywords, extractive_summary
    PROCESSORS_AVAILABLE = True
except ImportError:
    PROCESSORS_AVAILABLE = False
    logger.warning("Processors not available")

try:
    from processors.graphs import graph
    GRAPH_AVAILABLE = True
except ImportError:
    GRAPH_AVAILABLE = False
    logger.warning("Graph module not available")


def parse_args():
    """Simple argument parser for --max and query."""
    max_results = 10
    query_parts = []

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--max' and i + 1 < len(sys.argv):
            try:
                max_results = int(sys.argv[i + 1])
            except ValueError:
                logger.warning("Invalid --max value, using default 10")
            i += 2
        else:
            query_parts.append(arg)
            i += 1

    query = " ".join(query_parts).strip()
    if not query:
        query = "artificial intelligence"

    return query, max_results


def collect_all(query: str, max_per_source: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    """Parallel collection with global deduplication."""
    print(f"\n🔍 Starting parallel research for: {query}")
    print("=" * 80)

    results = {}
    seen_urls = set()

    with ThreadPoolExecutor(max_workers=7) as executor:
        future_to_source = {
            executor.submit(
                lambda c=collector, q=query, m=max_per_source: 
                c.search(q, max_results=m) if hasattr(c, 'search') else []
            ): name 
            for name, collector in collectors.items()
        }

        for future in as_completed(future_to_source):
            source_name = future_to_source[future]
            try:
                data = future.result()
                
                # Global deduplication
                filtered = []
                for item in data:
                    url = item.get('url')
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    filtered.append(item)
                
                results[source_name] = filtered[:max_per_source]
                print(f"[+] {source_name.upper():<12} → {len(results[source_name])} items")

            except Exception as e:
                print(f" [!] {source_name} failed: {e}")
                logger.error(f"{source_name} error", exc_info=True)
                results[source_name] = []

    total = sum(len(items) for items in results.values())
    print(f"\n📊 Total unique items collected: {total}")
    return results


def main(query: str, max_per_source: int = 10):
    db = ResearchDB()
    print(f"\n🔍 Researching: {query} (max {max_per_source} per source)")
    print("=" * 80)

    # 1. Collect
    all_data = collect_all(query, max_per_source=max_per_source)

    # 2. Store in DB
    total_items = 0
    failed_items = 0
    for source, items in all_data.items():
        for item in items:
            try:
                source_id = db.add_source(
                    collector=item.get('collector', source),
                    title=item.get('title', 'No title'),
                    content=item.get('content', ''),
                    url=item.get('url', ''),
                    source=item.get('source', source),
                    published=item.get('published', ''),
                    query=query
                )
                if source_id:
                    total_items += 1
                    if PROCESSORS_AVAILABLE and item.get('content'):
                        try:
                            keywords = extract_keywords(item['content'], num_keywords=5)
                            for kw in keywords:
                                db.add_keyword(kw, source_id)
                        except Exception:
                            pass
            except Exception as e:
                failed_items += 1
                logger.error(f"Store error: {e}")

    print(f"\n📊 Total items stored: {total_items}")

    # 3. Summary
    if total_items > 0 and PROCESSORS_AVAILABLE:
        print("\n📝 Generating summary...")
        all_content = "\n\n".join([
            item.get('content', '') 
            for items in all_data.values() 
            for item in items 
            if item.get('content')
        ])
        if all_content.strip():
            try:
                summary = extractive_summary(all_content, num_sentences=6)
                print("\n" + "="*80)
                print("SUMMARY:")
                print(summary)
                print("="*80)
            except Exception as e:
                logger.error(f"Summary error: {e}")

    # 4. Display results
    print("\n" + "="*80)
    print("RESULTS BY SOURCE:")
    print("="*80)
    for source, items in all_data.items():
        if items:
            print(f"\n📰 {source.upper()} ({len(items)} items):")
            for i, item in enumerate(items[:3], 1):
                title = item.get('title', 'No title')
                if len(title) > 85:
                    title = title[:82] + "..."
                print(f" {i}. {title}")
                if item.get('source'):
                    print(f"    Source: {item['source']}")
                if item.get('url'):
                    print(f"    URL: {item['url']}")

    # 5. Save report
    from pathlib import Path
    Path("reports").mkdir(exist_ok=True)
    safe_query = query.replace(' ', '_')[:50]
    report_file = f"reports/{safe_query}_report.txt"
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"Research Report: {query}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Max per source: {max_per_source}\n")
            f.write(f"Total Items: {total_items}\n")
            f.write("=" * 70 + "\n\n")
            for source, items in all_data.items():
                if items:
                    f.write(f"\n## {source.upper()} ({len(items)} items)\n")
                    for i, item in enumerate(items, 1):
                        f.write(f"\n[{i}] {item.get('title')}\n")
                        f.write(f"URL: {item.get('url')}\n")
                        f.write(f"Source: {item.get('source')}\n")
                        f.write(f"Preview: {item.get('content', '')[:500]}...\n")
                        f.write("-" * 60 + "\n")
        print(f"\n✅ Report saved: {report_file}")
    except Exception as e:
        logger.error(f"Report save failed: {e}")

    # 6. Stats
    stats = db.get_stats()
    print(f"\n📊 Database: {stats.get('total_sources', 0)} sources | {stats.get('total_keywords', 0)} keywords")


if __name__ == "__main__":
    query, max_per_source = parse_args()
    main(query, max_per_source)
