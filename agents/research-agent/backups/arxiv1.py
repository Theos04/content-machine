import arxiv

def search_arxiv(topic, max_results=10):
    search = arxiv.Search(query=topic, max_results=max_results)
    results = []
    for paper in search.results():
        results.append({
            "title": paper.title,
            "summary": paper.summary,
            "url": paper.entry_id,
            "authors": [a.name for a in paper.authors]
        })
    return results
