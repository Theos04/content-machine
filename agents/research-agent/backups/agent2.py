import sys
from typing import List, Dict, Any
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import collectors with error handling
collectors = {}

try:
    from collectors import wikipedia
    collectors['wikipedia'] = wikipedia
except ImportError as e:
    logger.warning(f"Could not import wikipedia: {e}")

try:
    from collectors import web
    collectors['web'] = web
except ImportError as e:
    logger.warning(f"Could not import web: {e}")

try:
    from collectors import reddit
    collectors['reddit'] = reddit
except ImportError as e:
    logger.warning(f"Could not import reddit: {e}")

try:
    from collectors import news
    collectors['news'] = news
except ImportError as e:
    logger.warning(f"Could not import news: {e}")

try:
    from collectors import arxiv
    collectors['arxiv'] = arxiv
except ImportError as e:
    logger.warning(f"Could not import arxiv: {e}")

try: 
    from collectors import youtube
    collectors['youtube'] = youtube
except ImportError as e:
    logger.warning(f"Cpuld not import youtube: {e}")

try: 
    from collectors import google 
    collectors['google'] = google 
except ImportError as e:
    logger.warning(f"Could not import google: {e}")

from database.db import ResearchDB

# Try to import processors, but don't fail if not available
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

def collect_all(query: str, max_per_source: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    """
    Collect data from all sources with a unified interface.
    """
    results = {}
    
    for source_name, collector_module in collectors.items():
        try:
            print(f"[+] Collecting from {source_name}...")
            
            # Check if the collector has a search function
            if hasattr(collector_module, 'search'):
                data = collector_module.search(query, max_results=max_per_source)
            else:
                print(f"    [!] Collector {source_name} has no search() function")
                data = []
            
            results[source_name] = data
            print(f"    Found {len(data)} items")
            
        except Exception as e:
            print(f"    [!] Error from {source_name}: {e}")
            logger.error(f"Error in {source_name}: {e}", exc_info=True)
            results[source_name] = []
    
    return results

def main(query: str):
    db = ResearchDB()
    
    print(f"\n🔍 Researching: {query}")
    print("=" * 60)
    
    # 1. Collect from all sources
    all_data = collect_all(query, max_per_source=10)
    
    # 2. Store in database
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
                    
                    # Extract and store keywords if processors available
                    if PROCESSORS_AVAILABLE and item.get('content'):
                        try:
                            keywords = extract_keywords(item['content'], num_keywords=5)
                            for keyword in keywords:
                                db.add_keyword(keyword, source_id)
                        except Exception as e:
                            logger.debug(f"Error extracting keywords: {e}")
                else:
                    failed_items += 1
                    
            except Exception as e:
                logger.error(f"Error storing item from {source}: {e}")
                failed_items += 1
    
    print(f"\n📊 Total items collected: {total_items}")
    if failed_items > 0:
        print(f"   Failed to store: {failed_items}")
    
    # 3. Generate summary if we have content
    if total_items > 0 and PROCESSORS_AVAILABLE:
        print("\n📝 Generating summary...")
        all_content = "\n\n".join([
            item.get('content', '') 
            for source in all_data.values() 
            for item in source 
            if item.get('content')
        ])
        
        if all_content.strip():
            try:
                summary = extractive_summary(all_content, num_sentences=5)
                print("\n" + "=" * 60)
                print("SUMMARY:")
                print(summary)
            except Exception as e:
                logger.error(f"Error generating summary: {e}")
                print("Could not generate summary")
    
    # 4. Display results by source
    print("\n" + "=" * 60)
    print("RESULTS BY SOURCE:")
    print("=" * 60)
    
    for source, items in all_data.items():
        if items:
            print(f"\n📰 {source.upper()} ({len(items)} items):")
            for i, item in enumerate(items[:3], 1):  # Show first 3
                title = item.get('title', 'No title')
                if len(title) > 80:
                    title = title[:77] + "..."
                print(f"  {i}. {title}")
                if item.get('source'):
                    print(f"     Source: {item['source']}")
                if item.get('published'):
                    pub_date = item['published'][:10] if len(item['published']) > 10 else item['published']
                    print(f"     Date: {pub_date}")
    
    # 5. Save report
    from pathlib import Path
    Path("reports").mkdir(exist_ok=True)
    
    report_file = f"reports/{query.replace(' ', '_')}_report.txt"
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"Research Report: {query}\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Total Items: {total_items}\n")
            f.write("=" * 60 + "\n\n")
            
            for source, items in all_data.items():
                if items:
                    f.write(f"\n## {source.upper()} ({len(items)} items)\n")
                    f.write("-" * 40 + "\n")
                    
                    for i, item in enumerate(items, 1):
                        f.write(f"\n[{i}] {item.get('title', 'No title')}\n")
                        f.write(f"Source: {item.get('source', 'Unknown')}\n")
                        f.write(f"URL: {item.get('url', 'No URL')}\n")
                        if item.get('published'):
                            f.write(f"Published: {item['published']}\n")
                        f.write(f"\nContent Preview:\n{item.get('content', 'No content')[:500]}\n")
                        f.write("-" * 40 + "\n")
        
        print(f"\n✅ Report saved to: {report_file}")
    except Exception as e:
        logger.error(f"Error saving report: {e}")
        print(f"❌ Could not save report: {e}")
    
    # 6. Build knowledge graph if available
    if GRAPH_AVAILABLE and total_items > 0:
        print("\n🔗 Building knowledge graph...")
        try:
            for source, items in all_data.items():
                for item in items:
                    if item.get('content') and PROCESSORS_AVAILABLE:
                        keywords = extract_keywords(item['content'], num_keywords=5)
                        for kw in keywords:
                            graph.add_node(kw)
                            graph.add_edge(item.get('title', kw), kw)
            
            print(f"Graph has {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges")
        except Exception as e:
            logger.error(f"Error building graph: {e}")
    
    # 7. Display database stats
    stats = db.get_stats()
    print("\n📊 Database Statistics:")
    print(f"   Total sources: {stats.get('total_sources', 0)}")
    print(f"   Total keywords: {stats.get('total_keywords', 0)}")
    if stats.get('by_collector'):
        print("   By collector:")
        for collector, count in stats['by_collector'].items():
            print(f"     - {collector}: {count}")

if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "artificial intelligence"
    main(topic)
