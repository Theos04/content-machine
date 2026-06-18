import networkx as nx
import matplotlib.pyplot as plt
from database.db import ResearchDB
import re

def visualize_knowledge_graph(query: str = None):
    """Create and display the knowledge graph"""
    
    # Create a new graph
    G = nx.Graph()
    
    # Get data from database
    db = ResearchDB()
    
    if query:
        sources = db.get_sources(query=query)
    else:
        sources = db.get_sources()
    
    # Build graph from database
    for source in sources:
        # Add source as node
        source_node = source['title'][:50]  # Limit title length
        G.add_node(source_node, type='source', collector=source['collector'])
        
        # Get keywords for this source
        # Since we don't have direct keyword-source mapping in DB, extract from content
        keywords = extract_keywords_simple(source['content'], num_keywords=3)
        
        for keyword in keywords:
            G.add_node(keyword, type='keyword')
            G.add_edge(source_node, keyword, weight=1)
    
    # Visualization settings
    plt.figure(figsize=(16, 12))
    
    # Position nodes using spring layout
    pos = nx.spring_layout(G, k=1, iterations=50)
    
    # Separate nodes by type
    source_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'source']
    keyword_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'keyword']
    
    # Draw nodes
    nx.draw_networkx_nodes(G, pos, nodelist=source_nodes, node_color='lightblue', 
                          node_size=2000, alpha=0.8, label='Sources')
    nx.draw_networkx_nodes(G, pos, nodelist=keyword_nodes, node_color='lightgreen', 
                          node_size=1000, alpha=0.6, label='Keywords')
    
    # Draw edges
    nx.draw_networkx_edges(G, pos, alpha=0.3, width=1)
    
    # Draw labels
    nx.draw_networkx_labels(G, pos, font_size=8, font_weight='bold')
    
    plt.title(f"Knowledge Graph for: {query if query else 'All Research'}", fontsize=16, fontweight='bold')
    plt.axis('off')
    plt.legend(loc='upper left')
    plt.tight_layout()
    
    # Save the graph
    output_file = f"knowledge_graph_{query.replace(' ', '_') if query else 'all'}.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✅ Graph saved to: {output_file}")
    
    # Show the graph
    plt.show()

def extract_keywords_simple(text: str, num_keywords: int = 5):
    """Simple keyword extraction for graph visualization"""
    if not text:
        return []
    
    # Common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                  'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                  'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing'}
    
    # Extract words (min 4 chars)
    words = re.findall(r'\b[A-Za-z][a-z]{3,}\b', text)
    
    # Filter stop words
    keywords = [w.lower() for w in words if w.lower() not in stop_words]
    
    # Get unique keywords
    unique_keywords = list(set(keywords))[:num_keywords]
    
    return unique_keywords

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    visualize_knowledge_graph(query)
