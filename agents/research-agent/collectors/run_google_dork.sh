#!/data/data/com.termux/files/usr/bin/bash
# Google Dorking with Agents Framework

cd /data/data/com.termux/files/home/storage/downloads/content-machine/agents/research-agent

# Ensure the CDP is running
if ! curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
    echo "[!] Chrome CDP not running. Starting browser..."
    cd collectors/chromium_cdp
    ./start-browser.sh --force
    cd ..
    sleep 5
fi

# Run the research agent with Google dorking
python3 << 'PYTHON_SCRIPT'
import sys
import json
from datetime import datetime
from pathlib import Path

# Add collectors path
sys.path.insert(0, '/data/data/com.termux/files/home/storage/downloads/content-machine/agents/research-agent/collectors')

try:
    from google_dork import search as google_dork_search
    print("[+] Google Dorking module loaded")
except ImportError as e:
    print(f"[-] Failed to load Google Dorking module: {e}")
    sys.exit(1)

def main():
    print("\n" + "="*80)
    print("🔍 GOOGLE DORKING RESEARCH TOOL")
    print("="*80)
    print("\nAvailable dork types:")
    print("  1. vulnerability - Find vulnerable systems")
    print("  2. security - Find security-sensitive files")
    print("  3. data_leak - Find potential data leaks")
    print("  4. admin_panels - Find admin login pages")
    print("  5. custom - Custom dork query")
    print("\n" + "-"*80)
    
    choice = input("\nSelect dork type (1-5): ").strip()
    
    dork_map = {
        '1': 'vulnerability',
        '2': 'security', 
        '3': 'data_leak',
        '4': 'admin_panels',
        '5': 'custom'
    }
    
    dork_type = dork_map.get(choice, 'vulnerability')
    
    if dork_type == 'custom':
        query = input("Enter your custom dork query: ").strip()
    else:
        domain = input("Enter target domain (or press Enter for general search): ").strip()
        if domain:
            query = f"site:{domain}"
        else:
            query = dork_type
    
    max_results = input("Max results (default 30): ").strip()
    max_results = int(max_results) if max_results else 30
    
    print(f"\n[*] Starting {dork_type} dorking...")
    print(f"[*] Query: {query}")
    print(f"[*] Max results: {max_results}")
    print("\n" + "="*80 + "\n")
    
    # Perform the search
    results = google_dork_search(query, max_results=max_results, dork_type=dork_type)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    
    report_file = report_dir / f"google_dork_{timestamp}.txt"
    json_file = report_dir / f"google_dork_{timestamp}.json"
    
    # Save text report
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write(f"GOOGLE DORKING REPORT\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Dork Type: {dork_type}\n")
        f.write(f"Query: {query}\n")
        f.write(f"Total Results: {len(results)}\n")
        f.write("="*80 + "\n\n")
        
        for i, result in enumerate(results, 1):
            f.write(f"\n[{i}] {result.get('title', 'No title')}\n")
            f.write(f"URL: {result.get('url', 'No URL')}\n")
            f.write(f"Source: {result.get('source', 'google.com')}\n")
            f.write(f"Dork: {result.get('dork_query', query)}\n")
            f.write("-"*60 + "\n")
    
    # Save JSON report
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Display results
    print(f"\n✅ Found {len(results)} unique results")
    print(f"📄 Report saved: {report_file}")
    print(f"📊 JSON saved: {json_file}")
    
    if results:
        print("\n" + "="*80)
        print("TOP RESULTS:")
        print("="*80)
        for i, result in enumerate(results[:10], 1):
            title = result.get('title', 'No title')[:70]
            url = result.get('url', 'No URL')[:80]
            print(f"\n{i}. {title}")
            print(f"   📎 {url}")
    
    # Option to save to database
    save_to_db = input("\n\nSave results to database? (y/n): ").strip().lower()
    if save_to_db == 'y':
        try:
            from database.db import ResearchDB
            db = ResearchDB()
            
            for result in results:
                db.add_source(
                    collector='google_dork',
                    title=result.get('title', ''),
                    content=result.get('content', ''),
                    url=result.get('url', ''),
                    source=result.get('source', 'google.com'),
                    published=result.get('published', ''),
                    query=f"{dork_type}:{query}"
                )
            print(f"[+] Saved {len(results)} results to database")
        except Exception as e:
            print(f"[-] Failed to save to database: {e}")
    
    print("\n✅ Google dorking complete!")

if __name__ == "__main__":
    main()
PYTHON_SCRIPT
