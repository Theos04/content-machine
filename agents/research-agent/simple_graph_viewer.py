from database.db import ResearchDB
import json
import re
from collections import Counter

def create_simple_html(query: str = None):
    """Create a lightweight HTML graph viewer"""
    
    db = ResearchDB()
    sources = db.get_sources(query=query) if query else db.get_sources()
    
    # Build simple graph data
    nodes = {}
    edges = []
    
    for source in sources[:30]:  # Limit for performance
        source_id = source['title'][:40]
        nodes[source_id] = {
            'id': source_id,
            'label': source_id[:30],
            'type': 'source',
            'collector': source['collector']
        }
        
        # Extract keywords
        words = re.findall(r'\b[A-Z][a-z]{3,}\b', source['content'])
        keywords = [w.lower() for w in words[:3]]
        
        for kw in keywords:
            if kw not in nodes:
                nodes[kw] = {
                    'id': kw,
                    'label': kw,
                    'type': 'keyword'
                }
            edges.append({'from': source_id, 'to': kw})
    
    # Create HTML
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Knowledge Graph - {query if query else 'Research'}</title>
    <style>
        body {{
            margin: 0;
            font-family: Arial, sans-serif;
            background: #f0f2f5;
        }}
        #header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }}
        #container {{
            display: flex;
            height: calc(100vh - 120px);
        }}
        #graph {{
            flex: 3;
            border: 1px solid #ddd;
            background: white;
        }}
        #sidebar {{
            flex: 1;
            background: white;
            padding: 20px;
            overflow-y: auto;
            border-left: 1px solid #ddd;
        }}
        .stat {{
            padding: 10px;
            margin: 10px 0;
            background: #f5f5f5;
            border-radius: 5px;
        }}
        .keyword {{
            display: inline-block;
            background: #e0e0e0;
            padding: 5px 10px;
            margin: 5px;
            border-radius: 15px;
            font-size: 12px;
            cursor: pointer;
        }}
        .keyword:hover {{
            background: #667eea;
            color: white;
        }}
        button {{
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            margin: 5px;
            border-radius: 5px;
            cursor: pointer;
        }}
        button:hover {{
            background: #5a67d8;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>📊 Knowledge Graph Explorer</h1>
        <p>Query: {query if query else 'All Data'} | {len(sources)} Sources | {len(nodes)} Nodes | {len(edges)} Edges</p>
        <button onclick="toggleLayout()">Change Layout</button>
        <button onclick="resetView()">Reset View</button>
    </div>
    <div id="container">
        <div id="graph"></div>
        <div id="sidebar">
            <div class="stat">
                <h3>📈 Statistics</h3>
                <div>Sources: <b>{len(sources)}</b></div>
                <div>Nodes: <b>{len(nodes)}</b></div>
                <div>Edges: <b>{len(edges)}</b></div>
                <div>Density: <b>{(len(edges)/(len(nodes)*(len(nodes)-1)/2)):.3f}</b></div>
            </div>
            <div class="stat">
                <h3>📚 Source Types</h3>
                {''.join([f'<div>{coll}: {count}</div>' for coll, count in Counter([s['collector'] for s in sources]).most_common()])}
            </div>
            <div class="stat">
                <h3>🔑 Top Keywords</h3>
                <div id="keywords">
                    {''.join([f'<span class="keyword" onclick="highlightKeyword(\'{kw}\')">{kw}</span>' for kw, count in Counter([kw for edge in edges for kw in [edge['to']] if kw in nodes]).most_common(20)])}
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/vis-network.min.js"></script>
    <script>
        var nodes = new vis.DataSet({json.dumps(list(nodes.values()))});
        var edges = new vis.DataSet({json.dumps(edges)});
        
        var container = document.getElementById('graph');
        var data = {{ nodes: nodes, edges: edges }};
        
        // Color nodes by type
        nodes.forEach(node => {{
            if (node.type === 'source') {{
                node.color = {{ background: '#667eea', border: '#4c51bf' }};
                node.shape = 'box';
                node.size = 30;
            }} else {{
                node.color = {{ background: '#48bb78', border: '#2f855a' }};
                node.shape = 'dot';
                node.size = 20;
            }}
        }});
        
        var options = {{
            nodes: {{
                font: {{ size: 12, face: 'Arial' }},
                borderWidth: 2,
                shadow: true
            }},
            edges: {{
                width: 1,
                color: {{ color: '#999', opacity: 0.5 }},
                smooth: {{ type: 'continuous' }}
            }},
            physics: {{
                stabilization: {{ iterations: 100 }},
                barnesHut: {{
                    gravitationalConstant: -50000,
                    centralGravity: 0.3,
                    springLength: 95,
                    springConstant: 0.04,
                    damping: 0.09
                }}
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 100,
                zoomView: true,
                dragView: true,
                navigationButtons: true
            }}
        }};
        
        var network = new vis.Network(container, data, options);
        
        // Layout presets
        var layouts = ['barnesHut', 'forceAtlas2Based', 'repulsion'];
        var currentLayout = 0;
        
        function toggleLayout() {{
            currentLayout = (currentLayout + 1) % layouts.length;
            var layout = layouts[currentLayout];
            var physicsOptions = {{
                stabilization: {{ iterations: 50 }},
                solver: layout
            }};
            if (layout === 'forceAtlas2Based') {{
                physicsOptions.forceAtlas2Based = {{
                    gravitationalConstant: -50,
                    centralGravity: 0.01,
                    springLength: 100,
                    springConstant: 0.08,
                    damping: 0.4
                }};
            }} else if (layout === 'repulsion') {{
                physicsOptions.repulsion = {{
                    centralGravity: 0.2,
                    springLength: 200,
                    springConstant: 0.05,
                    nodeDistance: 150,
                    damping: 0.09
                }};
            }}
            network.setOptions({{ physics: physicsOptions }});
        }}
        
        function resetView() {{
            network.fit({{
                animation: {{
                    duration: 1000,
                    easingFunction: 'easeInOutQuad'
                }}
            }});
        }}
        
        function highlightKeyword(keyword) {{
            // Find node
            var nodeIds = nodes.getIds().filter(id => id.toLowerCase().includes(keyword.toLowerCase()));
            if (nodeIds.length > 0) {{
                network.selectNodes(nodeIds);
                network.fit({{
                    nodes: nodeIds,
                    animation: {{ duration: 500 }}
                }});
            }}
        }}
        
        // Click handler
        network.on("click", function(params) {{
            if (params.nodes.length > 0) {{
                var nodeId = params.nodes[0];
                var node = nodes.get(nodeId);
                if (node.url) {{
                    window.open(node.url, '_blank');
                }} else {{
                    console.log('Node:', node);
                }}
            }}
        }});
        
        // Auto-fit after stabilization
        network.once("stabilizationIterationsDone", function() {{
            network.fit();
        }});
        
        console.log('Graph loaded with {len(nodes)} nodes and {len(edges)} edges');
    </script>
</body>
</html>
    """
    
    filename = f"graph_viewer_{query.replace(' ', '_') if query else 'all'}.html"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ Graph viewer created: {filename}")
    print(f"   Open this file in your browser to explore the graph!")
    print(f"   File location: {filename}")
    
    # Also print file path for easy access
    import os
    print(f"   Full path: {os.path.abspath(filename)}")
    
    # Return file path for opening
    return filename

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "BJP - bhartiya janta party"
    create_simple_html(query)
