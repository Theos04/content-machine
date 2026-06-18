import networkx as nx

graph = nx.Graph()

graph.add_edge(
    "OpenAI",
    "GPT-5"
)

graph.add_edge(
    "GPT-5",
    "Research Agent"
)
