#!/usr/bin/env python3
"""
Quick debug to test comment extraction
"""

import requests
import json

def test_reddit_comments():
    # Use a known post with many comments
    test_url = "https://old.reddit.com/r/termux/comments/1rlouej/which_cool_things_you_can_do_with_termux/"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # Try www.reddit.com JSON endpoint
    json_url = test_url.replace('old.reddit.com', 'www.reddit.com').rstrip('/') + '.json'
    
    print(f"Testing: {json_url}\n")
    
    try:
        response = requests.get(json_url, headers=headers, timeout=15)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response type: {type(data)}")
            print(f"Length: {len(data) if isinstance(data, list) else 'N/A'}")
            
            if isinstance(data, list) and len(data) >= 2:
                print(f"\nPost data keys: {data[0].get('data', {}).get('children', [{}])[0].get('data', {}).keys()}")
                
                comments_data = data[1].get('data', {}).get('children', [])
                print(f"\nNumber of top-level comments: {len(comments_data)}")
                
                if comments_data:
                    # Show first comment
                    first_comment = comments_data[0].get('data', {})
                    print(f"\nFirst comment author: {first_comment.get('author', 'N/A')}")
                    print(f"First comment body: {first_comment.get('body', 'N/A')[:100]}")
                else:
                    print("\nNo comments found in the response")
                    print(f"Response structure: {json.dumps(data[1].keys(), indent=2)}")
            else:
                print(f"Unexpected response structure: {type(data)}")
        else:
            print(f"Failed with status {response.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_reddit_comments()

