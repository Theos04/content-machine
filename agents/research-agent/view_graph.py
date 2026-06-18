from database.db import ResearchDB
import json
import re
from collections import Counter

def create_graph_html(query: str = None):
    """Create a working HTML graph viewer"""
    
    db = ResearchDB()
    sources = db.get_sources(query=query) if query else db.get_sources()
    
    # Build graph data
    nodes = []
    edges = []
    node_ids = set()
    node_map = {}
    
    # Add source nodes
    for source in sources[:40]:  # Limit for performance
        source_id = source['title'][:40].replace('"', '&quot;')
        if source_id not in node_ids:
            node_ids.add(source_id)
            node_map[source_id] = len(nodes)
            nodes.append({
                'id': source_id,
                'label': source_id[:30],
                'type': 'source',
                'collector': source['collector'],
                'url': source['url']
            })
        
        # Extract keywords
        words = re.findall(r'\b[A-Z][a-z]{4,}\b', source['content'])
        keywords = list(set([w.lower() for w in words[:5]]))
        
        for kw in keywords:
            if kw not in node_ids and len(kw) > 3:
                node_ids.add(kw)
                node_map[kw] = len(nodes)
                nodes.append({
                    'id': kw,
                    'label': kw,
                    'type': 'keyword'
                })
            
            if kw in node_map:
                edges.append({
                    'from': source_id,
                    'to': kw,
                    'id': f"{source_id}_{kw}"
                })
    
    # Count connections for sizing
    edge_count = {}
    for edge in edges:
        edge_count[edge['from']] = edge_count.get(edge['from'], 0) + 1
        edge_count[edge['to']] = edge_count.get(edge['to'], 0) + 1
    
    # Add sizes based on connections
    for node in nodes:
        node['size'] = min(15 + edge_count.get(node['id'], 0) * 2, 50)
    
    # Create HTML (fixing the string formatting)
    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <title>Knowledge Graph - {query if query else 'Research'}</title>
    <meta charset="UTF-8">
    <style>
        body {{
            margin: 0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f5f5;
        }}
        #header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        #header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        #header p {{
            margin: 5px 0 0;
            opacity: 0.9;
            font-size: 14px;
        }}
        #controls {{
            padding: 10px 20px;
            background: white;
            border-bottom: 1px solid #ddd;
        }}
        button {{
            background: #667eea;
            color: white;
            border: none;
            padding: 8px 16px;
            margin: 0 5px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }}
        button:hover {{
            background: #5a67d8;
        }}
        #container {{
            display: flex;
            height: calc(100vh - 130px);
        }}
        #graph {{
            flex: 3;
            background: white;
            margin: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        #sidebar {{
            flex: 1;
            background: white;
            margin: 10px 10px 10px 0;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow-y: auto;
        }}
        .stat-box {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .stat-box h3 {{
            margin: 0 0 10px 0;
            color: #333;
            font-size: 16px;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: bold;
            color: #667eea;
        }}
        .keyword-cloud {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}
        .keyword {{
            background: #e9ecef;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .keyword:hover {{
            background: #667eea;
            color: white;
            transform: scale(1.05);
        }}
        .legend {{
            display: flex;
            gap: 20px;
            margin-top: 10px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 4px;
        }}
        .instructions {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px;
            margin-top: 15px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>📊 Knowledge Graph Explorer</h1>
        <p>Query: "{query if query else 'All Research'}" | {len(sources)} Sources | {len(nodes)} Nodes | {len(edges)} Edges</p>
    </div>
    <div id="controls">
        <button onclick="togglePhysics()">⚡ Toggle Physics</button>
        <button onclick="resetView()">🔄 Reset View</button>
        <button onclick="exportPNG()">📸 Export as PNG</button>
        <span style="margin-left: 20px; font-size: 12px; color: #666;">
            💡 Click on nodes to open URLs | Drag to pan | Scroll to zoom
        </span>
    </div>
    <div id="container">
        <div id="graph"></div>
        <div id="sidebar">
            <div class="stat-box">
                <h3>📈 Graph Statistics</h3>
                <div class="stat-value">{len(sources)}</div>
                <div>Sources (Articles/Posts)</div>
                <div class="stat-value">{len(nodes)}</div>
                <div>Total Nodes</div>
                <div class="stat-value">{len(edges)}</div>
                <div>Connections (Edges)</div>
            </div>
            
            <div class="stat-box">
                <h3>📚 Sources by Type</h3>
                {''.join([f'<div>• {coll}: {count}</div>' for coll, count in Counter([s['collector'] for s in sources]).most_common()])}
            </div>
            
            <div class="stat-box">
                <h3>🏷️ Legend</h3>
                <div class="legend">
                    <div class="legend-item">
                        <div class="legend-color" style="background: #667eea;"></div>
                        <span>Sources</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #48bb78;"></div>
                        <span>Keywords</span>
                    </div>
                </div>
            </div>
            
            <div class="stat-box">
                <h3>🔑 Top Keywords</h3>
                <div class="keyword-cloud">
                    {''.join([f'<span class="keyword" onclick="highlightKeyword(\'{kw}\')">{kw}</span>' for kw, count in Counter([kw for edge in edges for kw in [edge['to']] if isinstance(kw, str)]).most_common(20)])}
                </div>
            </div>
            
            <div class="instructions">
                <strong>💡 Instructions:</strong><br>
                • <strong>Click</strong> on blue nodes to open the source article<br>
                • <strong>Drag</strong> nodes to rearrange the graph<br>
                • <strong>Scroll</strong> to zoom in/out<br>
                • <strong>Click keywords</strong> to highlight related nodes<br>
                • Use the <strong>Export PNG</strong> button to save the graph
            </div>
        </div>
    </div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/vis-network.min.js"></script>
    <script>
        // Graph data
        var nodesData = {json.dumps(nodes)};
        var edgesData = {json.dumps(edges)};
        
        // Configure nodes with colors and sizes
        nodesData.forEach(function(node) {{
            if (node.type === 'source') {{
                node.color = {{ background: '#667eea', border: '#4c51bf', highlight: {{ background: '#5a67d8', border: '#434190' }} }};
                node.shape = 'box';
                node.font = {{ color: 'white', size: 12, background: 'none' }};
            }} else {{
                node.color = {{ background: '#48bb78', border: '#2f855a', highlight: {{ background: '#38a169', border: '#276749' }} }};
                node.shape = 'dot';
                node.font = {{ color: '#333', size: 11 }};
            }}
            node.size = node.size || 20;
            node.borderWidth = 2;
            node.shadow = {{ enabled: true, size: 5 }};
        }});
        
        // Create datasets
        var nodes = new vis.DataSet(nodesData);
        var edges = new vis.DataSet(edgesData);
        
        var container = document.getElementById('graph');
        var data = {{ nodes: nodes, edges: edges }};
        
        var options = {{
            nodes: {{
                font: {{ size: 12, face: 'Arial' }},
                borderWidth: 2,
                shadow: true
            }},
            edges: {{
                width: 1.5,
                color: {{ color: '#999', opacity: 0.4 }},
                smooth: {{ type: 'continuous', roundness: 0.5 }},
                arrows: {{ to: false }}
            }},
            physics: {{
                enabled: true,
                stabilization: {{ iterations: 100 }},
                barnesHut: {{
                    gravitationalConstant: -40000,
                    centralGravity: 0.3,
                    springLength: 100,
                    springConstant: 0.04,
                    damping: 0.09
                }}
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 100,
                zoomView: true,
                dragView: true,
                navigationButtons: true,
                keyboard: true
            }}
        }};
        
        var network = new vis.Network(container, data, options);
        var physicsEnabled = true;
        
        // Toggle physics
        function togglePhysics() {{
            physicsEnabled = !physicsEnabled;
            network.setOptions({{ physics: {{ enabled: physicsEnabled }} }});
            document.querySelector('button:first-child').style.opacity = physicsEnabled ? '1' : '0.6';
        }}
        
        // Reset view
        function resetView() {{
            network.fit({{
                animation: {{
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                }}
            }});
        }}
        
        // Export as PNG
        function exportPNG() {{
            var canvas = document.querySelector('canvas');
            if (canvas) {{
                var link = document.createElement('a');
                link.download = 'knowledge_graph.png';
                link.href = canvas.toDataURL();
                link.click();
            }}
        }}
        
        // Highlight keyword
        function highlightKeyword(keyword) {{
            var nodeIds = nodes.getIds().filter(function(id) {{
                return id.toLowerCase().includes(keyword.toLowerCase());
            }});
            if (nodeIds.length > 0) {{
                network.selectNodes(nodeIds);
                network.fit({{
                    nodes: nodeIds,
                    animation: {{ duration: 500 }}
                }});
            }}
        }}
        
        // Click handler for opening URLs
        network.on("click", function(params) {{
            if (params.nodes.length > 0) {{
                var nodeId = params.nodes[0];
                var node = nodes.get(nodeId);
                if (node && node.url) {{
                    window.open(node.url, '_blank');
                }}
            }}
        }});
        
        // Auto-fit after stabilization
        network.once("stabilizationIterationsDone", function() {{
            network.fit();
            console.log('Graph stabilized and fitted');
        }});
        
        console.log('Graph loaded with ' + nodesData.length + ' nodes and ' + edgesData.length + ' edges');
    </script>
</body>
</html>"""
    
    filename = f"knowledge_graph_{query.replace(' ', '_') if query else 'all'}.html"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_template)
    
    print(f"\n✅ Graph viewer created: {filename}")
    print(f"📊 Statistics: {len(sources)} sources, {len(nodes)} nodes, {len(edges)} edges")
    print(f"\n🌐 To open in Chrome:")
    print(f"   1. File location: {filename}")
    print(f"   2. Open Chrome and navigate to: file://{os.path.abspath(filename)}")
    print(f"   3. Or run: termux-open {filename}")
    
    return filename

if __name__ == "__main__":
    import sys
    import os
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "BJP - bhartiya janta party"
    create_graph_html(query)
