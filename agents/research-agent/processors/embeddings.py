import requests
import json

class HFEmbedder:
    def __init__(self, api_token):
        self.api_url = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"
        self.headers = {"Authorization": f"Bearer {api_token}"}

    def embed(self, text):
        response = requests.post(self.api_url, headers=self.headers, json={"inputs": text})
        return response.json()  # list of floats
