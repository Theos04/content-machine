#!/data/data/com.termux/files/usr/bin/python3
"""
Google Search using Chrome CDP (Selenium)
This works reliably because it uses a real browser
"""

import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

class CDPGoogleSearch:
    def __init__(self, debugger_address="127.0.0.1:9222"):
        """Connect to existing Chrome instance via CDP"""
        self.options = webdriver.ChromeOptions()
        self.options.add_experimental_option("debuggerAddress", debugger_address)
        
        try:
            self.driver = webdriver.Chrome(options=self.options)
            print(f"✅ Connected to Chrome CDP at {debugger_address}")
        except Exception as e:
            print(f"❌ Failed to connect to Chrome: {e}")
            print("\nMake sure Chrome is running with CDP:")
            print("  ./start_chrome_with_cdp.sh")
            raise
    
    def search(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Search Google using the connected Chrome instance"""
        
        results = []
        
        try:
            # Navigate to Google
            self.driver.get("https://www.google.com")
            time.sleep(1)
            
            # Find search box and enter query
            search_box = self.driver.find_element(By.NAME, "q")
            search_box.clear()
            search_box.send_keys(query)
            search_box.submit()
            
            # Wait for results to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#search"))
            )
            
            time.sleep(2)  # Let results fully load
            
            # Extract search results
            result_blocks = self.driver.find_elements(By.CSS_SELECTOR, "div.g")
            
            for block in result_blocks[:max_results]:
                try:
                    # Extract title and link
                    title_elem = block.find_element(By.CSS_SELECTOR, "h3")
                    title = title_elem.text
                    
                    # Get link
                    link_elem = block.find_element(By.CSS_SELECTOR, "a")
                    url = link_elem.get_attribute("href")
                    
                    # Get snippet/description
                    try:
                        snippet_elem = block.find_element(By.CSS_SELECTOR, "div.VwiC3b")
                        snippet = snippet_elem.text
                    except:
                        snippet = ""
                    
                    if title and url and "google.com" not in url:
                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': snippet,
                            'query': query,
                            'timestamp': datetime.now().isoformat()
                        })
                except Exception as e:
                    continue
            
            return results
            
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def research_topic(self, topic: str, depth: str = "comprehensive") -> Dict[str, Any]:
        """Research a topic using multiple search strategies"""
        
        search_queries = {
            "basic": [
                topic,
                f"what is {topic}",
                f"{topic} definition"
            ],
            "comprehensive": [
                topic,
                f"what is {topic}",
                f"{topic} explained",
                f"{topic} guide",
                f"{topic} news",
                f"{topic} latest updates",
                f"{topic} facts",
                f"information about {topic}"
            ],
            "news": [
                f"{topic} latest news",
                f"{topic} updates",
                f"{topic} current events",
                f"{topic} today"
            ]
        }
        
        queries = search_queries.get(depth, search_queries["comprehensive"])
        all_results = []
        
        print(f"\n🔍 Researching: {topic}")
        print(f"📊 Depth: {depth}")
        print("="*80)
        
        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] Searching: {query}")
            results = self.search(query, max_results=10)
            
            if results:
                print(f"  ✓ Found {len(results)} results")
                for r in results[:3]:
                    print(f"    • {r['title'][:60]}")
                all_results.extend(results)
            else:
                print(f"  ✗ No results")
            
            time.sleep(1)  # Be respectful
        
        # Deduplicate by URL
        unique_results = []
        seen_urls = set()
        for result in all_results:
            if result['url'] not in seen_urls:
                seen_urls.add(result['url'])
                unique_results.append(result)
        
        print(f"\n📊 Total unique results: {len(unique_results)}")
        
        return {
            'topic': topic,
            'depth': depth,
            'timestamp': datetime.now().isoformat(),
            'total_results': len(unique_results),
            'results': unique_results
        }
    
    def save_report(self, data: Dict[str, Any]):
        """Save results to files"""
        
        topic = data['topic'].replace(' ', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        report_dir = Path("research_reports")
        report_dir.mkdir(exist_ok=True)
        
        # Text report
        txt_file = report_dir / f"{topic}_{timestamp}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write(f"RESEARCH REPORT: {data['topic']}\n")
            f.write(f"Generated: {data['timestamp']}\n")
            f.write(f"Depth: {data['depth']}\n")
            f.write(f"Total Sources: {data['total_results']}\n")
            f.write("="*80 + "\n\n")
            
            for i, result in enumerate(data['results'], 1):
                f.write(f"\n[{i}] {result['title']}\n")
                f.write(f"URL: {result['url']}\n")
                if result.get('snippet'):
                    f.write(f"Snippet: {result['snippet'][:300]}...\n")
                f.write("-"*60 + "\n")
        
        # JSON report
        json_file = report_dir / f"{topic}_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return txt_file, json_file
    
    def close(self):
        """Close the browser connection"""
        if self.driver:
            self.driver.quit()
    
    def __del__(self):
        self.close()


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║           GOOGLE RESEARCH TOOL (Chrome CDP)                  ║
║                    Using Real Browser                        ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Check if Chrome CDP is running
    import requests
    try:
        requests.get("http://127.0.0.1:9222/json/version", timeout=2)
        print("✅ Chrome CDP is running\n")
    except:
        print("❌ Chrome CDP not running!")
        print("\nPlease start Chrome first:")
        print("  cd /path/to/chromium_cdp")
        print("  ./start_chrome_with_cdp.sh")
        print("\nOr use the simple HTTP version if Chrome isn't available.")
        return
    
    topic = input("📝 Enter your research topic: ").strip()
    if not topic:
        print("No topic entered. Exiting.")
        return
    
    print("\nSelect research depth:")
    print("1. Basic - Quick overview")
    print("2. Comprehensive - Detailed information (default)")
    print("3. News - Latest updates")
    
    choice = input("\nChoice (1-3, default=2): ").strip()
    
    depth_map = {
        '1': 'basic',
        '2': 'comprehensive',
        '3': 'news'
    }
    
    depth = depth_map.get(choice, 'comprehensive')
    
    # Perform research
    researcher = CDPGoogleSearch()
    
    try:
        data = researcher.research_topic(topic, depth)
        
        if data['total_results'] == 0:
            print("\n❌ No results found. Try a different topic.")
            return
        
        # Display results
        print("\n" + "="*80)
        print(f"📊 RESULTS for '{topic}':")
        print("="*80)
        
        for i, result in enumerate(data['results'][:15], 1):
            print(f"\n{i}. {result['title'][:80]}")
            print(f"   🔗 {result['url'][:80]}")
            if result.get('snippet'):
                print(f"   📝 {result['snippet'][:100]}...")
        
        # Save report
        txt_file, json_file = researcher.save_report(data)
        
        print("\n" + "="*80)
        print(f"✅ RESEARCH COMPLETE")
        print(f"📄 Text report: {txt_file}")
        print(f"📊 JSON report: {json_file}")
        print("="*80)
        
        # Ask to open in browser
        open_browser = input("\n🌐 Open first result in browser? (y/n): ").strip().lower()
        if open_browser == 'y':
            import webbrowser
            webbrowser.open(data['results'][0]['url'])
            print(f"Opened: {data['results'][0]['url']}")
    
    finally:
        researcher.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
