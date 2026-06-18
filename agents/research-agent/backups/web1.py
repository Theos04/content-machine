import requests
import trafilatura

def extract_article(url):

    html = requests.get(url, timeout=20).text

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True
    )

    return text
