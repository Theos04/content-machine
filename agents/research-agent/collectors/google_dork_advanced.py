#!/data/data/com.termux/files/usr/bin/python3
"""
Advanced Google Dorking Tool with Chrome CDP
"""

import sys
import json
import time
import requests
from urllib.parse import quote_plus
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/data/data/com.termux/files/home/storage/downloads/content-machine/agents/research-agent/collectors')

from google_dork import GoogleDorkCollector

class AdvancedGoogleDorking:
    def __init__(self):
        self.collector = GoogleDorkCollector()
        
    def run(self):
        print("""
╔══════════════════════════════════════════════════════════════╗
║                    ADVANCED GOOGLE DORKING                   ║
║                      Chrome CDP Powered                      ║
╚══════════════════════════════════════════════════════════════╝
        """)
        
        print("\n[1] Vulnerability Discovery")
        print("[2] Sensitive File Discovery")
        print("[3] Admin Panel Discovery")
        print("[4] Database & Backup Discovery")
        print("[5] Credential & API Key Discovery")
        print("[6] Custom Dork Search")
        print("[7] Targeted Domain Scan")
        print("[8] Load Dork Database")
        
        choice = input("\nSelect option (1-8): ").strip()
        
        if choice == '1':
            self.vulnerability_discovery()
        elif choice == '2':
            self.sensitive_files_discovery()
        elif choice == '3':
            self.admin_panel_discovery()
        elif choice == '4':
            self.database_discovery()
        elif choice == '5':
            self.credentials_discovery()
        elif choice == '6':
            self.custom_dork()
        elif choice == '7':
            self.targeted_scan()
        elif choice == '8':
            self.load_dork_database()
        else:
            print("Invalid choice")
    
    def vulnerability_discovery(self):
        dorks = [
            'intitle:"index of" "config"',
            'intitle:"index of" "wp-config.php"',
            'inurl:admin "login"',
            'inurl:phpinfo.php',
            'intitle:"SQL Manager"',
            'inurl:".env" filetype:env',
            'intitle:"Dashboard" "admin"',
            'inurl:backup filetype:sql',
            'inurl:api "key"',
            'filetype:log "error"',
        ]
        self.run_dork_scan(dorks, "vulnerability")
    
    def sensitive_files_discovery(self):
        dorks = [
            'intitle:"index of" ".git"',
            'inurl:".git/config"',
            'filetype:conf "mysql"',
            'intitle:"index of" "password"',
            'inurl:".aws/credentials"',
            'filetype:pem "BEGIN RSA PRIVATE KEY"',
            'inurl:".ssh/id_rsa"',
            'intitle:"MongoDB Express"',
        ]
        self.run_dork_scan(dorks, "sensitive_files")
    
    def admin_panel_discovery(self):
        dorks = [
            'intitle:"Admin Login"',
            'inurl:admin/login',
            'inurl:wp-admin',
            'inurl:administrator',
            'intitle:"Control Panel" login',
            'inurl:cpanel',
            'inurl:webmail',
            'inurl:login "admin"',
        ]
        self.run_dork_scan(dorks, "admin_panels")
    
    def database_discovery(self):
        dorks = [
            'intitle:"index of" "database"',
            'inurl:"/backup/"',
            'filetype:sql "INSERT INTO" "VALUES"',
            'intitle:"Index of" "logs"',
            'filetype:csv "credit card"',
            'filetype:sql "password"',
            'inurl:dump.sql',
            'filetype:db "password"',
        ]
        self.run_dork_scan(dorks, "databases")
    
    def credentials_discovery(self):
        dorks = [
            'filetype:xls "email" "password"',
            'filetype:pdf "confidential"',
            'intitle:"index of" "password"',
            'filetype:txt "password"',
            'filetype:env "DB_PASSWORD"',
            'filetype:xml "password"',
            'inurl:api "api_key"',
        ]
        self.run_dork_scan(dorks, "credentials")
    
    def custom_dork(self):
        dork = input("Enter your custom dork: ").strip()
        if dork:
            self.run_dork_scan([dork], "custom")
    
    def targeted_scan(self):
        domain = input("Enter target domain (e.g., example.com): ").strip()
        if domain:
            dorks = [
                f'site:{domain} intitle:"index of"',
                f'site:{domain} inurl:admin',
                f'site:{domain} filetype:log',
                f'site:{domain} filetype:sql',
                f'site:{domain} inurl:backup',
                f'site:{domain} "config" filetype:php',
                f'site:{domain} "password" filetype:txt',
            ]
            self.run_dork_scan(dorks, f"targeted_{domain}")
    
    def load_dork_database(self):
        """Load dorks from a file"""
        dork_file = input("Enter dork database file path: ").strip()
        try:
            with open(dork_file, 'r') as f:
                dorks = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            self.run_dork_scan(dorks, "custom_db")
        except Exception as e:
            print(f"Error loading dorks: {e}")
    
    def run_dork_scan(self, dorks, scan_name):
        print(f"\n[*] Starting {scan_name} scan with {len(dorks)} dorks")
        print("[*] Results will be deduplicated automatically\n")
        
        all_results = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for i, dork in enumerate(dorks, 1):
            print(f"\n[{i}/{len(dorks)}] Testing: {dork}")
            results = self.collector.search(dork, max_results=20)
            
            if results:
                print(f"    Found {len(results)} results")
                all_results.extend(results)
                
                # Display quick preview
                for j, result in enumerate(results[:3], 1):
                    print(f"      {j}. {result.get('title', 'No title')[:60]}")
                    print(f"         {result.get('url', 'No URL')[:70]}")
            
            time.sleep(2)  # Rate limiting
        
        # Deduplicate results
        unique_results = []
        seen_urls = set()
        for result in all_results:
            url = result.get('url')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        # Save results
        report_dir = Path("google_dork_reports")
        report_dir.mkdir(exist_ok=True)
        
        report_file = report_dir / f"{scan_name}_{timestamp}.txt"
        json_file = report_dir / f"{scan_name}_{timestamp}.json"
        
        # Save text report
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write(f"GOOGLE DORK SCAN REPORT\n")
            f.write(f"Scan: {scan_name}\n")
            f.write(f"Date: {datetime.now().isoformat()}\n")
            f.write(f"Dorks used: {len(dorks)}\n")
            f.write(f"Total results: {len(unique_results)}\n")
            f.write("="*80 + "\n\n")
            
            for i, result in enumerate(unique_results, 1):
                f.write(f"\n[{i}] {result.get('title', 'No title')}\n")
                f.write(f"URL: {result.get('url', 'No URL')}\n")
                f.write(f"Dork: {result.get('dork_query', 'N/A')}\n")
                f.write("-"*60 + "\n")
        
        # Save JSON
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(unique_results, f, indent=2, ensure_ascii=False)
        
        print("\n" + "="*80)
        print(f"✅ SCAN COMPLETE")
        print(f"📊 Total unique results: {len(unique_results)}")
        print(f"📄 Text report: {report_file}")
        print(f"📊 JSON report: {json_file}")
        print("="*80)

if __name__ == "__main__":
    dorking = AdvancedGoogleDorking()
    dorking.run()
