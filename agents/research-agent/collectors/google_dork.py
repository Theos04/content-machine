"""
Google Dorking Collector using Chrome CDP
Performs advanced Google searches with dork operators
"""

import json
import time
import asyncio
import websocket
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import re
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

class GoogleDorkCollector:
    """Collector for Google dorking via Chrome CDP"""
    
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        self.ws_url = None
        self.websocket = None
        
    def get_websocket_url(self) -> Optional[str]:
        """Get WebSocket URL from CDP endpoint"""
        try:
            response = requests.get(f"{self.cdp_url}/json/version", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('webSocketDebuggerUrl')
        except Exception as e:
            logger.error(f"Failed to get WebSocket URL: {e}")
        return None
    
    def connect(self) -> bool:
        """Connect to Chrome via CDP"""
        self.ws_url = self.get_websocket_url()
        if not self.ws_url:
            logger.error("Could not get WebSocket URL from CDP")
            return False
        
        try:
            self.websocket = websocket.create_connection(self.ws_url, timeout=10)
            logger.info(f"Connected to Chrome CDP at {self.ws_url}")
            return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False
    
    def send_command(self, method: str, params: Dict = None) -> Dict:
        """Send CDP command and wait for response"""
        if not self.websocket:
            raise Exception("Not connected to Chrome")
        
        cmd_id = int(time.time() * 1000)
        message = {
            "id": cmd_id,
            "method": method,
            "params": params or {}
        }
        
        self.websocket.send(json.dumps(message))
        
        # Wait for response
        while True:
            response = json.loads(self.websocket.recv())
            if response.get("id") == cmd_id:
                return response.get("result", {})
    
    def create_tab(self) -> str:
        """Create a new tab and return its target ID"""
        try:
            response = requests.put(f"{self.cdp_url}/json/new", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('id')
        except Exception as e:
            logger.error(f"Failed to create tab: {e}")
        return None
    
    def close_tab(self, tab_id: str):
        """Close a tab by its ID"""
        try:
            requests.post(f"{self.cdp_url}/json/close/{tab_id}", timeout=5)
        except Exception as e:
            logger.error(f"Failed to close tab: {e}")
    
    def navigate_to_url(self, url: str, wait_time: int = 3) -> Dict:
        """Navigate to a URL and return page content"""
        if not self.websocket:
            self.connect()
        
        # Create new tab
        tab_id = self.create_tab()
        if not tab_id:
            return {}
        
        # Switch to the new tab (simplified - just use requests for navigation)
        try:
            # Use the target ID to navigate via CDP
            target_url = f"{self.cdp_url}/json/target/{tab_id}"
            
            # Navigate using the existing connection
            response = requests.get(f"{self.cdp_url}/json", timeout=5)
            targets = response.json()
            
            # Find our target
            target = None
            for t in targets:
                if t.get('id') == tab_id:
                    target = t
                    break
            
            if target and target.get('webSocketDebuggerUrl'):
                # Connect to the specific target
                target_ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=10)
                
                # Navigate
                nav_cmd = {
                    "id": 1,
                    "method": "Page.navigate",
                    "params": {"url": url}
                }
                target_ws.send(json.dumps(nav_cmd))
                
                # Wait for navigation
                time.sleep(wait_time)
                
                # Get page content
                content_cmd = {
                    "id": 2,
                    "method": "Runtime.evaluate",
                    "params": {"expression": "document.body.innerText"}
                }
                target_ws.send(json.dumps(content_cmd))
                
                # Get response
                result = None
                for _ in range(5):
                    response = json.loads(target_ws.recv())
                    if response.get('id') == 2:
                        result = response.get('result', {}).get('result', {}).get('value', '')
                        break
                
                target_ws.close()
                return {"content": result, "tab_id": tab_id}
                
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return {}
        
        return {"content": "", "tab_id": tab_id}
    
    def search(self, query: str, max_results: int = 30, dork_type: str = "basic") -> List[Dict[str, Any]]:
        """
        Perform Google dorking search
        
        Args:
            query: Search query (can include dork operators)
            max_results: Maximum number of results to return
            dork_type: Type of dork ('basic', 'advanced', 'vulnerability')
        """
        results = []
        
        # Dork operator documentation
        dork_operators = {
            'intitle': 'intitle:"{query}"',
            'inurl': 'inurl:{query}',
            'filetype': 'filetype:{ext} {query}',
            'site': 'site:{domain} {query}',
            'cache': 'cache:{url}',
            'info': 'info:{url}',
            'related': 'related:{url}',
            'link': 'link:{url}',
            'inanchor': 'inanchor:{text}',
            'allintext': 'allintext:{query}',
            'allintitle': 'allintitle:{query}',
            'allinurl': 'allinurl:{query}',
        }
        
        # Pre-defined dork patterns for different purposes
        dork_patterns = {
            "vulnerability": [
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
            ],
            "security": [
                'intitle:"index of" ".git"',
                'inurl:".git/config"',
                'filetype:conf "mysql"',
                'intitle:"index of" "password"',
                'inurl:".aws/credentials"',
                'filetype:pem "BEGIN RSA PRIVATE KEY"',
                'inurl:".ssh/id_rsa"',
                'intitle:"MongoDB Express"',
            ],
            "data_leak": [
                'filetype:xls "email" "password"',
                'filetype:pdf "confidential"',
                'intitle:"index of" "database"',
                'inurl:"/backup/"',
                'filetype:sql "INSERT INTO" "VALUES"',
                'intitle:"Index of" "logs"',
                'filetype:csv "credit card"',
            ],
            "admin_panels": [
                'intitle:"Admin Login"',
                'inurl:admin/login',
                'inurl:wp-admin',
                'inurl:administrator',
                'intitle:"Control Panel" login',
                'inurl:cpanel',
                'inurl:webmail',
            ],
        }
        
        # Build search queries based on dork_type
        search_queries = []
        if dork_type in dork_patterns:
            search_queries = dork_patterns[dork_type][:max_results//3 + 1]
        elif dork_type == "custom":
            search_queries = [query]
        else:
            # Basic dork - enhance user query with operators
            if ':' not in query:  # No operators, add some basic ones
                search_queries = [
                    f'intitle:"{query}"',
                    f'inurl:{query}',
                    f'"{query}"',
                    f'allintext:{query}'
                ]
            else:
                search_queries = [query]
        
        logger.info(f"Performing {len(search_queries)} Google dork searches")
        
        # Connect to Chrome
        if not self.connect():
            return results
        
        try:
            for i, dork_query in enumerate(search_queries[:max_results]):
                if len(results) >= max_results:
                    break
                    
                logger.info(f"Searching [{i+1}/{len(search_queries)}]: {dork_query}")
                
                # Build Google search URL
                encoded_query = quote_plus(dork_query)
                google_url = f"https://www.google.com/search?q={encoded_query}&num=20"
                
                # Navigate and get results
                page_data = self.navigate_to_url(google_url, wait_time=5)
                content = page_data.get('content', '')
                
                if content:
                    # Parse Google search results
                    parsed_results = self.parse_google_results(content, dork_query)
                    
                    for result in parsed_results:
                        if len(results) >= max_results:
                            break
                        
                        # Add metadata
                        result['collector'] = 'google_dork'
                        result['dork_query'] = dork_query
                        result['dork_type'] = dork_type
                        result['search_timestamp'] = datetime.now().isoformat()
                        results.append(result)
                    
                    logger.info(f"  Found {len(parsed_results)} results")
                
                # Be nice to Google's servers
                time.sleep(2)
                
        except Exception as e:
            logger.error(f"Search error: {e}")
        finally:
            if self.websocket:
                self.websocket.close()
        
        # Deduplicate results by URL
        unique_results = []
        seen_urls = set()
        for result in results:
            url = result.get('url')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        logger.info(f"Google dorking complete: {len(unique_results)} unique results")
        return unique_results[:max_results]
    
    def parse_google_results(self, html_content: str, query: str) -> List[Dict[str, Any]]:
        """Parse Google search results from HTML"""
        results = []
        
        # Regex patterns for Google search results
        patterns = [
            # Standard Google result pattern
            r'<a href="([^"]+)"[^>]*>\s*<h3[^>]*>(.*?)</h3>',
            # Alternative pattern
            r'<div class="[^"]*r[^"]*"[^>]*><a href="([^"]+)".*?>(.*?)</a>',
            # Result with cite
            r'<cite[^>]*>(.*?)</cite>.*?<a href="([^"]+)"',
        ]
        
        # Try each pattern
        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
            if matches:
                for match in matches[:20]:  # Limit per page
                    try:
                        if len(match) >= 2:
                            url = match[0] if 'http' in match[0] else match[1] if len(match) > 1 and 'http' in match[1] else None
                            title = match[1] if len(match) > 1 and match[1] != url else match[0] if match[0] != url else "No title"
                            
                            if url and 'google.com' not in url and 'youtube.com' not in url:
                                # Clean URL
                                url = re.sub(r'&sa=.*$', '', url)
                                url = re.sub(r'/url\?q=', '', url)
                                
                                # Clean title
                                title = re.sub(r'<[^>]+>', '', title)
                                title = title.strip()
                                
                                results.append({
                                    'title': title[:200],
                                    'url': url,
                                    'content': f"Found via Google dork: {query}",
                                    'source': 'google.com',
                                    'published': '',
                                    'dork_query': query
                                })
                    except Exception as e:
                        logger.debug(f"Parse error: {e}")
                break
        
        # If no results found with regex, create basic results from the content
        if not results:
            # Extract any URLs from the page
            urls = re.findall(r'https?://[^\s<>"\'\)]+', html_content)
            unique_urls = list(set(urls))[:10]
            
            for url in unique_urls:
                if 'google.com' not in url:
                    results.append({
                        'title': f"Result from {url[:50]}",
                        'url': url,
                        'content': f"Found via Google dork: {query}",
                        'source': 'google.com',
                        'published': ''
                    })
        
        return results
    
    def vulnerability_scan(self, target_domain: str) -> List[Dict[str, Any]]:
        """Perform vulnerability-focused dorking on a specific domain"""
        results = []
        
        dorks = [
            f'site:{target_domain} intitle:"index of"',
            f'site:{target_domain} inurl:admin',
            f'site:{target_domain} filetype:log',
            f'site:{target_domain} filetype:sql',
            f'site:{target_domain} inurl:backup',
            f'site:{target_domain} "config" filetype:php',
            f'site:{target_domain} "password" filetype:txt',
            f'site:{target_domain} "api key"',
            f'site:{target_domain} "database" filetype:sql',
            f'site:{target_domain} "wp-config"',
            f'site:{target_domain} ".env"',
            f'site:{target_domain} "debug"',
        ]
        
        for dork in dorks:
            logger.info(f"Testing dork: {dork}")
            search_results = self.search(dork, max_results=10)
            results.extend(search_results)
            time.sleep(1)
        
        return results


def search(query: str, max_results: int = 30, dork_type: str = "basic") -> List[Dict[str, Any]]:
    """
    Wrapper function for the collector interface
    """
    collector = GoogleDorkCollector()
    return collector.search(query, max_results, dork_type)


if __name__ == "__main__":
    # Test the collector
    import sys
    
    if len(sys.argv) > 1:
        query = sys.argv[1]
        dork_type = sys.argv[2] if len(sys.argv) > 2 else "basic"
        
        collector = GoogleDorkCollector()
        results = collector.search(query, max_results=10, dork_type=dork_type)
        
        print(f"\n📊 Found {len(results)} results:")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result.get('title', 'No title')}")
            print(f"   URL: {result.get('url', 'No URL')}")
    else:
        print("Usage: python google_dork.py <query> [dork_type]")
        print("\nDork types: basic, vulnerability, security, data_leak, admin_panels, custom")
