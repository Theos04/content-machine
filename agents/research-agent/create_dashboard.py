from database.db import ResearchDB
import json
import re
from collections import Counter

def create_html_dashboard(query: str = None):
    """Create an HTML dashboard with embedded graph"""
    
    db = ResearchDB()
    sources = db.get_sources(query=query) if query else db.get_sources()
    
    # Prepare data for JavaScript
    nodes = []
    edges = []
    keywords_count = Counter()
    
    for source in sources:
        source_id = len(nodes)
        nodes.append({
            'id': source_id,
            'label': source['title'][:40],
            'type': 'source',
            'collector': source['collector'],
            'url': source['url']
        })
        
        # Extract keywords
        words = re.findall(r'\b[A-Z][a-z]+\b', source['content'])
        keywords = [w.lower() for w in words if len(w) > 3][:5]
        
        for kw in keywords:
            keywords_count[kw] += 1
            # Find or create keyword node
            kw_id = None
            for node in nodes:
                if node.get('label') == kw and node.get('type') == 'keyword':
                    kw_id = node['id']
                    break
            
            if kw_id is None:
                kw_id = len(nodes)
                nodes.append({
                    'id': kw_id,
                    'label': kw,
                    'type': 'keyword',
                    'size': keywords_count[kw]
                })
            
            edges.append({'from': source_id, 'to': kw_id})
    
    # Generate HTML
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Knowledge Graph Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/vis-network.min.js"></script>
    <style>
        body {{
            margin: 0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        #header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }}
        #graph-container {{
            width: 100%;
            height: 600px;
            border: 1px solid #ddd;
        }}
        #stats {{
            padding: 20px;
            background: #f5f5f5;
            display: inline-block;
            width: 300px;
            vertical-align: top;
        }}
        #graph-wrapper {{
            display: inline-block;
            width: calc(100% - 340px);
        }}
        .stat-box {{
            background: white;
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }}
        .keyword-cloud {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }}
        .keyword {{
            background: #e0e0e0;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>📊 Knowledge Graph Dashboard</h1>
        <p>Query: {query if query else 'All Research'} | {len(sources)} Sources | {len(nodes)} Nodes | {len(edges)} Edges</p>
    </div>
    
    <div id="graph-wrapper">
        <div id="graph-container"></div>
    </div>
    
    <div id="stats">
        <div class="stat-box">
            <h3>📈 Statistics</h3>
            <div>Sources: <span class="stat-value">{len(sources)}</span></div>
            <div>Nodes: <span class="stat-value">{len(nodes)}</span></div>
            <div>Edges: <span class="stat-value">{len(edges)}</span></div>
            <div>Density: <span class="stat-value">{len(edges)/(len(nodes)*(len(nodes)-1)/2):.3f}</span></div>
        </div>
        
        <div class="stat-box">
            <h3>📚 Sources by Type</h3>
            {''.join([f'<div>{coll}: {count}</div>' for coll, count in Counter([s['collector'] for s in sources]).most_common()])}
        </div>
        
        <div class="stat-box">
            <h3>🔑 Top Keywords</h3>
            <div class="keyword-cloud">
                {''.join([f'<span class="keyword">{kw} ({count})</span>' for kw, count in keywords_count.most_common(15)])}
            </div>
        </div>
        
        <div class="stat-box">
            <h3>🎨 Legend</h3>
            <div style="color: #667eea">🔵 Sources (Articles/Posts)</div>
            <div style="color: #48bb78">🟢 Keywords/Concepts</div>
        </div>
    </div>
    
    <script>
        var nodes = new vis.DataSet({json.dumps(nodes)});
        var edges = new vis.DataSet({json.dumps(edges)});
        
        var container = document.getElementById('graph-container');
        var data = {{ nodes: nodes, edges: edges }};
        
        var options = {{
            nodes: {{
                shape: 'dot',
                size: 20,
                font: { size: 12 },
                borderWidth: 2,
                shadow: true
            }},
            edges: {{
                width: 1,
                arrows: { to: false },
                smooth: { type: 'continuous' }
            }},
            physics: {{
                stabilization: true,
                barnesHut: { gravitationalConstant: -80000 }
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 100,
                zoomView: true,
                dragView: true
            }}
        }};
        
        // Color nodes by type
        nodes.forEach(node => {{
            if (node.type === 'source') {{
                node.color = 'rgba(102, 126, 234, 0.8)';
                node.shape = 'box';
            }} else {{
                node.color = 'rgba(72, 187, 120, 0.8)';
                node.shape = 'dot';
            }}
            if (node.size) node.value = node.size;
        }});
        
        var network = new vis.Network(container, data, options);
        
        // Add click handler to open URLs
        network.on("click", function(params) {{
            if (params.nodes.length > 0) {{
                var nodeId = params.nodes[0];
                var node = nodes.get(nodeId);
                if (node.url) {{
                    window.open(node.url, '_blank');
                }}
            }}
        }});
    </script>
</body>
</html>
    """
    
    output_file = f"dashboard_{query.replace(' ', '_') if query else 'all'}.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ Dashboard created: {output_file}")
    print(f"Open this file in your browser to explore the interactive graph!")

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    create_html_dashboard(query)
