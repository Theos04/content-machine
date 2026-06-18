import networkx as nx
from database.db import ResearchDB
import re

def export_to_gephi(query: str = None):
    """Export graph to Gephi format"""
    
    db = ResearchDB()
    sources = db.get_sources(query=query) if query else db.get_sources()
    
    # Build graph
    G = nx.Graph()
    
    for source in sources:
        source_node = source['title'][:50]
        G.add_node(source_node, 
                  type='source',
                  collector=source['collector'],
                  url=source['url'])
        
        keywords = extract_keywords_simple(source['content'], num_keywords=5)
        for keyword in keywords:
            G.add_node(keyword, type='keyword')
            G.add_edge(source_node, keyword, weight=1)
    
    # Export in GEXF format (for Gephi)
    output_file = f"graph_{query.replace(' ', '_') if query else 'all'}.gexf"
    nx.write_gexf(G, output_file)
    print(f"✅ Graph exported to: {output_file}")
    print("You can open this file with Gephi (https://gephi.org/)")
    
    # Also export basic stats
    print(f"\n📊 Graph Statistics:")
    print(f"   Nodes: {G.number_of_nodes()}")
    print(f"   Edges: {G.number_of_edges()}")
    print(f"   Density: {nx.density(G):.3f}")
    
    # Find important nodes (high degree)
    degrees = dict(G.degree())
    top_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:10]
    print(f"\n🔝 Top 10 connected nodes:")
    for node, degree in top_nodes:
        print(f"   {node[:40]}: {degree} connections")

def extract_keywords_simple(text: str, num_keywords: int = 5):
    if not text:
        return []
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                  'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been'}
    words = re.findall(r'\b[A-Za-z][a-z]{3,}\b', text)
    keywords = [w.lower() for w in words if w.lower() not in stop_words]
    return list(set(keywords))[:num_keywords]

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    export_to_gephi(query)
