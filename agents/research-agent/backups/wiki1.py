import wikipediaapi

wiki = wikipediaapi.Wikipedia(
    user_agent="ResearchAgent/1.0",
    language="en"
)

def get_wikipedia(topic):
    page = wiki.page(topic)

    if not page.exists():
        return None

    return {
        "title": page.title,
        "summary": page.summary,
        "text": page.text
    }

