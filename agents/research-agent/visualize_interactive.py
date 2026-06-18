import plotly.graph_objects as go
import networkx as nx
from database.db import ResearchDB
import re

def create_interactive_graph(query: str = None):
    """Create interactive knowledge graph"""
    
    db = ResearchDB()
    sources = db.get_sources(query=query) if query else db.get_sources()
    
    # Build graph
    G = nx.Graph()
    
    for source in sources[:50]:  # Limit for performance
        source_node = source['title'][:40]
        G.add_node(source_node, type='source', 
                  collector=source['collector'],
                  url=source['url'])
        
        keywords = extract_keywords_simple(source['content'], num_keywords=3)
        for keyword in keywords:
            G.add_node(keyword, type='keyword')
            G.add_edge(source_node, keyword)
    
    # Get positions
    pos = nx.spring_layout(G, k=2, iterations=50)
    
    # Create edge traces
    edge_x = []
    edge_y = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
    
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines'
    )
    
    # Create node traces
    node_x = []
    node_y = []
    node_text = []
    node_color = []
    
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
        
        # Color by type
        if G.nodes[node].get('type') == 'source':
            node_color.append('lightblue')
        else:
            node_color.append('lightgreen')
    
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=node_text,
        textposition="top center",
        hoverinfo='text',
        marker=dict(
            size=15,
            color=node_color,
            line=dict(width=2)
        )
    )
    
    # Create figure
    fig = go.Figure(data=[edge_trace, node_trace],
                   layout=go.Layout(
                       title=f'Knowledge Graph: {query if query else "All Data"}',
                       titlefont_size=16,
                       showlegend=False,
                       hovermode='closest',
                       margin=dict(b=20, l=5, r=5, t=40),
                       xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                       yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                   )
    
    # Save as HTML
    output_file = f"knowledge_graph_{query.replace(' ', '_') if query else 'all'}.html"
    fig.write_html(output_file)
    print(f"✅ Interactive graph saved to: {output_file}")
    print(f"Open this file in your browser to explore the graph interactively!")
    
    return fig

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
    fig = create_interactive_graph(query)
    fig.show()  # Opens in browser
