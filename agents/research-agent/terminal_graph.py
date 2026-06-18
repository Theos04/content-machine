from database.db import ResearchDB
from collections import Counter
import re

def print_terminal_graph(query: str = None):
    """Print a text-based knowledge graph in terminal"""
    
    db = ResearchDB()
    sources = db.get_sources(query=query) if query else db.get_sources()
    
    if not sources:
        print("❌ No data found. Run 'python agent.py \"your topic\"' first.")
        return
    
    print("\n" + "="*80)
    print(f"📊 KNOWLEDGE GRAPH: {query if query else 'ALL RESEARCH'}")
    print("="*80)
    
    # 1. Source Summary
    print("\n📚 SOURCES BY TYPE:")
    print("-"*40)
    source_counts = Counter([s['collector'] for s in sources])
    for collector, count in source_counts.most_common():
        bar = "█" * min(count, 30)
        print(f"  {collector:12} : {count:2} {bar}")
    
    # 2. Keyword Extraction
    print("\n🔑 TOP KEYWORDS & CONCEPTS:")
    print("-"*40)
    
    all_words = []
    for source in sources:
        # Extract meaningful words
        words = re.findall(r'\b[A-Za-z][a-z]{3,}\b', source['content'])
        words = [w.lower() for w in words if len(w) > 3 and w.lower() not in 
                ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'with', 'have', 'this', 'from']]
        all_words.extend(words)
    
    keyword_counts = Counter(all_words)
    for i, (word, count) in enumerate(keyword_counts.most_common(20), 1):
        bar = "█" * min(count, 20)
        print(f"  {i:2}. {word:15} ({count:2}) {bar}")
    
    # 3. Connection Map (ASCII Graph)
    print("\n🔗 CONNECTION MAP (Sources to Keywords):")
    print("-"*80)
    
    # Show top 10 sources with their keywords
    for i, source in enumerate(sources[:10], 1):
        title = source['title'][:50]
        collector = source['collector'][0].upper()
        
        # Extract keywords from this source
        words = re.findall(r'\b[A-Za-z][a-z]{4,}\b', source['content'])
        keywords = list(set([w.lower() for w in words[:5]]))
        
        print(f"\n  {i}. [{collector}] {title}")
        print(f"     └── Connected to: {', '.join(keywords[:5]) if keywords else 'general concepts'}")
    
    # 4. Network Statistics
    print("\n📈 NETWORK STATISTICS:")
    print("-"*40)
    total_keywords = len(set(all_words))
    total_connections = len(all_words)
    
    print(f"  Total Sources      : {len(sources)}")
    print(f"  Unique Keywords    : {total_keywords}")
    print(f"  Total Connections  : {total_connections}")
    print(f"  Avg. Keywords/Source: {total_connections/len(sources):.1f}")
    print(f"  Network Density    : {(total_connections/(len(sources)*total_keywords)):.3f}")
    
    # 5. Cluster Visualization
    print("\n🎯 TOPIC CLUSTERS:")
    print("-"*40)
    
    # Group related keywords
    clusters = {
        'Political': ['bjp', 'modi', 'india', 'party', 'government', 'political', 'election', 'minister'],
        'Technical': ['python', 'code', 'app', 'android', 'linux', 'terminal', 'software', 'development'],
        'Academic': ['research', 'paper', 'study', 'analysis', 'data', 'model', 'algorithm'],
        'News': ['news', 'article', 'report', 'said', 'today', 'latest', 'update']
    }
    
    for cluster_name, keywords in clusters.items():
        found = [kw for kw in keywords if kw in keyword_counts]
        if found:
            total = sum(keyword_counts[kw] for kw in found)
            print(f"  {cluster_name:12} : {total} mentions - {', '.join(found[:5])}")
    
    # 6. Source Graph (ASCII)
    print("\n🗺️  SOURCE CONNECTION GRAPH:")
    print("-"*80)
    
    # Create a simple ASCII graph showing connections
    for source in sources[:8]:
        title = source['title'][:35]
        collector = source['collector']
        
        # Count connections for this source
        words = re.findall(r'\b[A-Za-z][a-z]{4,}\b', source['content'])
        keywords = list(set([w.lower() for w in words[:8]]))
        conn_count = len(keywords)
        
        # Create a horizontal bar
        bar_length = min(conn_count, 40)
        bar = "█" * bar_length + "░" * (40 - bar_length)
        
        # Color code by source type
        color = ""
        reset = ""
        if collector == 'news':
            color = "\033[94m"  # Blue
        elif collector == 'wikipedia':
            color = "\033[92m"  # Green
        elif collector == 'reddit':
            color = "\033[91m"  # Red
        elif collector == 'arxiv':
            color = "\033[93m"  # Yellow
        else:
            color = "\033[95m"  # Purple
        
        print(f"  {color}{collector[:4]:4}{reset} {bar} {title}")
    
    # 7. Most Connected Sources
    print("\n⭐ MOST CONNECTED SOURCES:")
    print("-"*40)
    
    source_connections = []
    for source in sources:
        words = re.findall(r'\b[A-Za-z][a-z]{4,}\b', source['content'])
        keywords = list(set([w.lower() for w in words]))
        source_connections.append((source['title'], len(keywords), source['collector']))
    
    source_connections.sort(key=lambda x: x[1], reverse=True)
    for i, (title, count, collector) in enumerate(source_connections[:5], 1):
        emoji = "📰" if collector == "news" else "📚" if collector == "wikipedia" else "💬" if collector == "reddit" else "📄"
        print(f"  {i}. {emoji} {title[:45]} - {count} keywords")
    
    print("\n" + "="*80)
    print("💡 TIP: Run 'python agent.py \"your topic\"' to research new topics")
    print("="*80 + "\n")

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    print_terminal_graph(query)
