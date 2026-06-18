# semanticscholar_scraper.py
"""
Semantic Scholar Scraper with Pagination, PDF Download, and Figure Extraction
A headless Chrome-based scraper for academic papers with rate limiting and cooldown management
"""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich import box
import subprocess
import os
import time
import json
import requests
import websocket
from urllib.parse import quote
import signal
import atexit
import shutil
from datetime import datetime
import sys
import re
import random

console = Console()

# ============ CONFIGURATION ============
CHROME_PORT = 9222
chrome_process = None

# Rate limiting settings
REQUEST_DELAY = 2.0          # Base delay between paper requests
MAX_RETRIES = 3              # Maximum retries for failed downloads
COOLDOWN_BASE = 5            # Base cooldown between pages

# ============ CHROME MANAGEMENT ============
def cleanup():
    """Terminate Chrome process on exit."""
    global chrome_process
    if chrome_process:
        try:
            chrome_process.terminate()
        except Exception:
            pass

atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda sig, frame: (cleanup(), exit(0)))

def find_chrome():
    """Find Chrome/Chromium binary on the system."""
    candidates = [
        "chromium-browser", "chromium", "google-chrome",
        "google-chrome-stable", "brave-browser"
    ]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None

def is_cdp_alive():
    """Check if Chrome's debugging port is responding."""
    try:
        requests.get(f"http://127.0.0.1:{CHROME_PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False

def start_chrome_headless():
    """Launch Chrome in headless mode with CDP enabled."""
    global chrome_process
    
    # Clean up existing instances
    subprocess.run(["pkill", "-f", f"remote-debugging-port={CHROME_PORT}"], capture_output=True)
    time.sleep(1)
    
    chrome_cmd = find_chrome()
    if not chrome_cmd:
        console.print("[red]✗ No Chrome/Chromium found. Install: pkg install chromium[/red]")
        return False
    
    user_data_dir = os.path.expanduser('~/chrome-cdp-semantic')
    os.makedirs(user_data_dir, exist_ok=True)
    
    cmd = [
        chrome_cmd,
        f"--remote-debugging-port={CHROME_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--headless=new",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-blink-features=AutomationControlled",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    
    try:
        console.print("[cyan]Launching Chrome...[/cyan]")
        chrome_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task("[cyan]Starting Chrome", total=30)
            for i in range(30):
                time.sleep(1)
                progress.update(task, advance=1)
                if is_cdp_alive():
                    console.print(f"[green]✓ Chrome ready ({i+1}s)[/green]")
                    return True
                if chrome_process.poll() is not None:
                    console.print(f"[red]✗ Chrome crashed (exit code {chrome_process.returncode})[/red]")
                    break
                    
    except Exception as e:
        console.print(f"[red]✗ Chrome launch error: {e}[/red]")
    
    return False

# ============ CDP CONNECTION ============
def get_ws_url():
    """Get WebSocket URL from Chrome debugging port."""
    try:
        tabs = requests.get(f"http://127.0.0.1:{CHROME_PORT}/json/list", timeout=5).json()
        if tabs:
            return tabs[0].get("webSocketDebuggerUrl")
    except Exception:
        pass
    return None

def connect_cdp():
    """Establish WebSocket connection to Chrome CDP."""
    ws_url = get_ws_url()
    if not ws_url:
        return None
    
    ws = websocket.create_connection(ws_url, timeout=30)
    
    for method in ["Page.enable", "Runtime.enable", "Network.enable"]:
        ws.send(json.dumps({"id": 1, "method": method}))
        time.sleep(0.3)
    
    # Clear any pending messages
    ws.settimeout(0.1)
    while True:
        try:
            ws.recv()
        except:
            break
    ws.settimeout(None)
    
    return ws

def send_cdp(ws, _id, method, params=None):
    """Send a CDP command."""
    ws.send(json.dumps({"id": _id, "method": method, "params": params or {}}))

def recv_cdp(ws, expected_id=None):
    """Receive a CDP response."""
    while True:
        try:
            res = json.loads(ws.recv())
            if "id" in res and (expected_id is None or res["id"] == expected_id):
                return res
        except Exception:
            continue

def evaluate_cdp(ws, expression, _id=100):
    """Evaluate JavaScript in the browser context."""
    send_cdp(ws, _id, "Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": True
    })
    result = recv_cdp(ws, _id)
    if "result" in result and "result" in result["result"]:
        return result["result"]["result"].get("value")
    return None

def navigate_cdp(ws, url):
    """Navigate to a URL and wait for content."""
    send_cdp(ws, 1000, "Page.navigate", {"url": url})
    time.sleep(3)
    
    for attempt in range(20):
        status = evaluate_cdp(ws, """
        (function() {
            const results = document.querySelectorAll('.paper-card, .search-result, [data-test-id="paper-card"]');
            if (results.length > 0) return 'results';
            
            const loading = document.querySelector('.loading-controls, [data-test-id="icon-loading-serp"]');
            if (loading) return 'loading';
            
            const body = document.body.innerText;
            if (body && body.length > 100) return 'content';
            
            return 'empty';
        })()
        """)
        
        if status == 'results':
            return True
        elif status == 'loading':
            time.sleep(1)
        else:
            time.sleep(1)
    
    return True

def click_next_page(ws):
    """Click the next page button if available."""
    result = evaluate_cdp(ws, """
    (function() {
        // Try common next button selectors
        const selectors = [
            'a[rel="next"]',
            'button[aria-label="Next"]',
            '.pagination .next',
            '[data-test-id="next-page"]',
            '.pager .next',
            'a:contains("Next")'
        ];
        
        for (let i = 0; i < selectors.length; i++) {
            const btn = document.querySelector(selectors[i]);
            if (btn) {
                const disabled = btn.disabled || btn.classList.contains('disabled');
                if (!disabled) {
                    btn.click();
                    return 'clicked';
                }
                return 'disabled';
            }
        }
        
        // Look for text-based next links
        const links = document.querySelectorAll('a');
        for (let i = 0; i < links.length; i++) {
            const text = links[i].textContent.trim().toLowerCase();
            if (text === 'next' || text === '>' || text === '→' || text.includes('next')) {
                links[i].click();
                return 'clicked';
            }
        }
        
        return 'not_found';
    })()
    """)
    
    if result == 'clicked':
        time.sleep(3)
        return True
    return False

# ============ SEARCH AND EXTRACTION ============
def get_paper_urls_from_search(ws, max_pages=3):
    """Extract paper URLs from search results across multiple pages."""
    all_urls = []
    page_num = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Scraping pages", total=max_pages)
        
        while page_num < max_pages:
            page_num += 1
            
            urls = evaluate_cdp(ws, """
            (function() {
                const links = document.querySelectorAll('a[href^="/paper/"]');
                const unique = new Set();
                links.forEach(function(link) {
                    const href = link.href;
                    if (href && !href.includes('#citing-papers') && !href.includes('#references')) {
                        unique.add(href);
                    }
                });
                return Array.from(unique);
            })()
            """)
            
            if not urls:
                break
            
            all_urls.extend(urls)
            console.print(f"[green]Page {page_num}: {len(urls)} papers (total: {len(all_urls)})[/green]")
            progress.update(task, advance=1)
            
            if page_num < max_pages:
                # Cooldown before next page
                cooldown = COOLDOWN_BASE + random.uniform(0, 2)
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TimeRemainingColumn(),
                ) as cool:
                    cool_task = cool.add_task("[yellow]Cooldown", total=cooldown)
                    for _ in range(int(cooldown * 10)):
                        time.sleep(0.1)
                        cool.update(cool_task, advance=0.1)
                
                if not click_next_page(ws):
                    break
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    console.print(f"[bold green]Total: {len(unique_urls)} unique papers across {page_num} pages[/bold green]")
    return unique_urls

def clean_author_text(text):
    """Clean author text by removing cookie consent and other noise."""
    if not text:
        return ""
    
    # Remove common cookie/text fragments
    noise_patterns = [
        r'Opens in a new window',
        r'Close this dialog',
        r'This website utilizes technologies such as cookies',
        r'enable essential site functionality',
        r'analytics, personalization',
        r'accept',
        r'reject',
        r'cookie',
        r'consent',
        r'Privacy Policy',
        r'privacy policy',
        r'et al\.?',
        r'[Cc]lose',
        r'[Ww]indow',
        r'[Dd]ialog',
        r'[Ss]ettings',
        r'[Pp]references',
    ]
    
    cleaned = text
    for pattern in noise_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # If it's a single word or less than 2 chars, might be invalid
    if len(cleaned) < 2:
        return ""
    
    # Check if it looks like actual names (has spaces or commas)
    if not re.search(r'[A-Za-z]+\s+[A-Za-z]+', cleaned) and ',' not in cleaned:
        # Try to extract names with common patterns
        name_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', cleaned)
        if name_match:
            return name_match.group(1)
        return ""
    
    return cleaned

def download_pdf(pdf_url, output_dir, paper_title):
    """Download PDF with retry logic and better error handling."""
    if not pdf_url:
        return None
    
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', paper_title[:50])
    filename = f"{safe_title}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        return filepath
    
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    ]
    
    for attempt in range(MAX_RETRIES):
        try:
            headers = {
                'User-Agent': user_agents[attempt % len(user_agents)],
                'Accept': 'application/pdf,application/octet-stream,*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.semanticscholar.org/',
                'Cache-Control': 'no-cache',
            }
            
            response = requests.get(pdf_url, headers=headers, timeout=60, stream=True)
            
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return filepath
            elif response.status_code in [403, 404]:
                # Don't retry on auth errors
                return None
            else:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    
    return None

def extract_paper_details(ws, paper_url_or_id, output_dir, paper_num=0, total_papers=0):
    """Extract detailed paper information and download resources."""
    if not paper_url_or_id.startswith('http'):
        paper_url = f"https://www.semanticscholar.org/paper/{paper_url_or_id}"
    else:
        paper_url = paper_url_or_id
    
    if total_papers > 0:
        console.print(f"[cyan][{paper_num}/{total_papers}] {paper_url[:70]}...[/cyan]")
    
    # Navigate and wait for load
    send_cdp(ws, 2000, "Page.navigate", {"url": paper_url})
    time.sleep(1)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Loading paper", total=15)
        
        for attempt in range(15):
            progress.update(task, advance=1)
            
            status = evaluate_cdp(ws, """
            (function() {
                const loading = document.querySelector('.loading, .spinner, .skeleton');
                if (loading) return 'loading';
                
                const content = document.querySelector('.paper-detail, .paper-content, article');
                if (content && content.textContent.length > 100) return 'loaded';
                
                return 'waiting';
            })()
            """)
            
            if status == 'loaded':
                break
            time.sleep(0.5)
    
    # Get full HTML
    full_html = evaluate_cdp(ws, "document.documentElement.outerHTML")
    
    # Extract paper info with clean author extraction
    paper_info = evaluate_cdp(ws, """
    (function() {
        const info = {
            title: '',
            authors: [],
            abstract: '',
            year: '',
            venue: '',
            citationCount: '',
            doi: '',
            arxivId: '',
            pdfUrl: '',
            referencesCount: '',
            codeRepos: [],
            figures: []
        };
        
        // Title
        const titleEl = document.querySelector('h1, .paper-title, [data-test-id="paper-title"]');
        if (titleEl) info.title = titleEl.textContent.trim();
        
        // Authors - clean extraction with multiple methods
        let authors = [];
        const authorSelectors = [
            '.author-list .author',
            '[data-test-id="authors"] a',
            '.authors .author',
            '.author-name',
            '.authors-list .author',
            '.paper-authors .author',
            '.author-badge'
        ];
        
        for (let i = 0; i < authorSelectors.length; i++) {
            const els = document.querySelectorAll(authorSelectors[i]);
            if (els.length > 0) {
                els.forEach(function(el) {
                    const name = el.textContent.trim();
                    // Filter out non-author text
                    if (name && name.length > 1 && 
                        !name.includes('window') && 
                        !name.includes('Close') &&
                        !name.includes('cookie') &&
                        !name.includes('consent') &&
                        !name.includes('Privacy') &&
                        !name.includes('privacy') &&
                        !name.includes('Policy') &&
                        !name.includes('policy') &&
                        !name.includes('et al') &&
                        !name.includes('Settings') &&
                        !name.includes('Preferences')) {
                        authors.push(name);
                    }
                });
                if (authors.length > 0) break;
            }
        }
        
        // Fallback: extract from text with better pattern matching
        if (authors.length === 0) {
            const text = document.body.textContent || '';
            // Look for author patterns
            const patterns = [
                /([A-Z][a-z]+ [A-Z][a-z]+(?:, [A-Z][a-z]+ [A-Z][a-z]+)*)/,
                /([A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+(?:, [A-Z][a-z]+ [A-Z]\. [A-Z][a-z]+)*)/,
                /([A-Z][a-z]+ [A-Z][a-z]+ and [A-Z][a-z]+ [A-Z][a-z]+)/
            ];
            for (let p = 0; p < patterns.length; p++) {
                const match = text.match(patterns[p]);
                if (match) {
                    const names = match[0].split(',').map(function(s) { return s.trim(); });
                    names.forEach(function(name) {
                        const trimmed = name.replace(/^and\s+/, '').trim();
                        if (trimmed && trimmed.length > 2 && 
                            !trimmed.includes('window') && 
                            !trimmed.includes('Close') &&
                            !trimmed.includes('Policy') &&
                            !trimmed.includes('Settings')) {
                            authors.push(trimmed);
                        }
                    });
                    if (authors.length > 0) break;
                }
            }
        }
        
        info.authors = authors;
        
        // Abstract
        const abstractEl = document.querySelector('.abstract, .paper-abstract, [data-test-id="abstract"], .description');
        if (abstractEl) {
            let abstractText = abstractEl.textContent.trim();
            abstractText = abstractText.replace(/^Abstract\\s*/i, '').trim();
            info.abstract = abstractText;
        }
        
        // Year
        const yearMatch = document.body.textContent.match(/\\b(19|20)\\d{2}\\b/);
        if (yearMatch) info.year = yearMatch[0];
        
        // Venue
        const venueEl = document.querySelector('.venue, .journal, .publication-venue, [data-test-id="venue"]');
        if (venueEl) info.venue = venueEl.textContent.trim();
        
        // Citation count
        const citEl = document.querySelector('.citation-count, [data-test-id="citation-count"]');
        if (citEl) {
            const match = citEl.textContent.trim().match(/\\d+/);
            if (match) info.citationCount = match[0];
        }
        
        // DOI
        const doiEl = document.querySelector('a[href*="doi.org"]');
        if (doiEl) {
            const match = doiEl.href.match(/10\\.\\d+\\/.+/);
            if (match) info.doi = match[0];
        }
        
        // arXiv
        const arxivEl = document.querySelector('a[href*="arxiv.org"]');
        if (arxivEl) {
            const match = arxivEl.href.match(/\\d{4}\\.\\d{4,5}/);
            if (match) info.arxivId = match[0];
        }
        
        // PDF URL
        const pdfEl = document.querySelector('a[href*=".pdf"], a[href*="pdf"], [data-test-id="pdf-link"]');
        if (pdfEl) info.pdfUrl = pdfEl.href;
        
        // References count
        const refEl = document.querySelector('.references .count, [data-test-id="references-count"]');
        if (refEl) {
            const match = refEl.textContent.trim().match(/\\d+/);
            if (match) info.referencesCount = match[0];
        }
        
        // Code repositories (GitHub)
        const githubLinks = document.querySelectorAll('a[href*="github.com"]');
        githubLinks.forEach(function(link) {
            info.codeRepos.push(link.href);
        });
        
        // Figures - better extraction
        const figures = document.querySelectorAll('img, figure img');
        figures.forEach(function(img) {
            const src = img.src || img.getAttribute('data-src');
            if (src && (src.includes('.png') || src.includes('.jpg') || 
                        src.includes('.jpeg') || src.includes('.gif') || 
                        src.includes('.webp')) && 
                !src.includes('logo') && 
                !src.includes('icon') &&
                !src.includes('avatar')) {
                info.figures.push(src);
            }
        });
        
        return info;
    })()
    """)
    
    # Extract paper ID
    paper_id = ''
    if '/paper/' in paper_url:
        parts = paper_url.split('/paper/')
        if len(parts) > 1:
            paper_id = parts[1].split('?')[0] or ''
    paper_info['paperId'] = paper_id
    paper_info['url'] = paper_url
    
    # Clean author text
    if paper_info.get('authors'):
        cleaned_authors = []
        for author in paper_info['authors']:
            cleaned = clean_author_text(author)
            if cleaned:
                cleaned_authors.append(cleaned)
        paper_info['authors'] = cleaned_authors
    
    # Save HTML
    os.makedirs(output_dir, exist_ok=True)
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', paper_info.get('title', 'untitled')[:50])
    html_file = os.path.join(output_dir, f"{safe_title}_page.html")
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(full_html)
    paper_info['htmlFile'] = html_file
    
    # Download PDF
    if paper_info.get('pdfUrl'):
        pdf_file = download_pdf(paper_info['pdfUrl'], output_dir, paper_info.get('title', 'untitled'))
        paper_info['pdfFile'] = pdf_file
    
    # Download figures
    if paper_info.get('figures'):
        figures_dir = os.path.join(output_dir, 'figures')
        os.makedirs(figures_dir, exist_ok=True)
        downloaded_figures = []
        
        for i, fig_url in enumerate(paper_info['figures'][:8]):  # Limit to 8 figures
            try:
                if fig_url.startswith('//'):
                    fig_url = 'https:' + fig_url
                elif fig_url.startswith('/'):
                    fig_url = 'https://www.semanticscholar.org' + fig_url
                
                if fig_url.startswith('http'):
                    time.sleep(0.2)  # Rate limit figure downloads
                    response = requests.get(fig_url, timeout=30, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    if response.status_code == 200:
                        # Get extension from URL or content-type
                        ext = fig_url.split('.')[-1].split('?')[0][:5]
                        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                            # Try to get from content-type
                            content_type = response.headers.get('content-type', '')
                            if 'png' in content_type:
                                ext = 'png'
                            elif 'jpeg' in content_type or 'jpg' in content_type:
                                ext = 'jpg'
                            elif 'gif' in content_type:
                                ext = 'gif'
                            else:
                                ext = 'jpg'
                        fig_file = os.path.join(figures_dir, f"figure_{i+1}.{ext}")
                        with open(fig_file, 'wb') as f:
                            f.write(response.content)
                        downloaded_figures.append(fig_file)
            except Exception:
                pass
        paper_info['downloadedFigures'] = downloaded_figures
    
    return paper_info

# ============ MAIN SCRAPING FUNCTIONS ============
def scrape_papers(query, max_pages=3, papers_per_page=10):
    """Main scraping function: search and extract paper details."""
    ws = None
    all_results = []
    
    try:
        if not is_cdp_alive():
            if not start_chrome_headless():
                return []
        
        ws = connect_cdp()
        if not ws:
            console.print("[red]✗ Failed to connect to Chrome[/red]")
            return []
        
        # Search
        search_url = f"https://www.semanticscholar.org/search?q={quote(query)}"
        if not navigate_cdp(ws, search_url):
            console.print("[red]✗ Navigation failed[/red]")
            return []
        
        time.sleep(2)
        
        # Get paper URLs
        all_urls = get_paper_urls_from_search(ws, max_pages)
        if not all_urls:
            console.print("[yellow]No papers found[/yellow]")
            return []
        
        # Limit to requested amount
        total_to_process = min(len(all_urls), max_pages * papers_per_page)
        paper_urls = all_urls[:total_to_process]
        
        console.print(f"[bold cyan]Processing {len(paper_urls)} papers...[/bold cyan]")
        
        # Create output directory
        safe_query = re.sub(r'[<>:"/\\|?*]', '_', query)
        query_dir = os.path.join("semantic_results", safe_query)
        os.makedirs(query_dir, exist_ok=True)
        
        # Process each paper
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task(f"[cyan]Processing {len(paper_urls)} papers", total=len(paper_urls))
            
            for i, url in enumerate(paper_urls, 1):
                # Dynamic cooldown
                if i > 1:
                    cooldown = REQUEST_DELAY + random.uniform(0, 1)
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                        TimeRemainingColumn(),
                    ) as cool:
                        cool_task = cool.add_task("[yellow]Cooldown", total=cooldown)
                        for _ in range(int(cooldown * 10)):
                            time.sleep(0.1)
                            cool.update(cool_task, advance=0.1)
                
                paper_dir = os.path.join(query_dir, f"paper_{i}")
                paper_info = extract_paper_details(ws, url, paper_dir, i, len(paper_urls))
                
                if paper_info and paper_info.get('title'):
                    all_results.append(paper_info)
                    
                    # Display preview
                    title = paper_info.get('title', 'Unknown')[:60]
                    console.print(f"[green]✓ {title}[/green]")
                    
                    if paper_info.get('authors'):
                        authors = ', '.join(paper_info['authors'][:3])
                        if len(paper_info['authors']) > 3:
                            authors += f" +{len(paper_info['authors']) - 3} more"
                        console.print(f"[dim]  Authors: {authors}[/dim]")
                    else:
                        console.print(f"[dim]  Authors: Not available[/dim]")
                    
                    if paper_info.get('year'):
                        console.print(f"[dim]  Year: {paper_info['year']}[/dim]")
                    
                    if paper_info.get('pdfFile'):
                        console.print(f"[dim]  📄 PDF: {os.path.basename(paper_info['pdfFile'])}[/dim]")
                    
                    if paper_info.get('codeRepos'):
                        console.print(f"[dim]  💻 Repos: {len(paper_info['codeRepos'])}[/dim]")
                    
                    if paper_info.get('downloadedFigures'):
                        console.print(f"[dim]  🖼️ Figures: {len(paper_info['downloadedFigures'])}[/dim]")
                
                progress.update(task, advance=1)
        
        return all_results
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        return []
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass

def save_results(query, results, output_dir="semantic_results"):
    """Save results to JSON, TSV, and ID files."""
    os.makedirs(output_dir, exist_ok=True)
    safe_query = re.sub(r'[<>:"/\\|?*]', '_', query)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON
    json_file = os.path.join(output_dir, f"{safe_query}_{timestamp}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            "query": query,
            "timestamp": timestamp,
            "total": len(results),
            "results": results
        }, f, indent=2, ensure_ascii=False)
    console.print(f"[green]✓ Saved JSON: {json_file}[/green]")
    
    # TSV
    tsv_file = os.path.join(output_dir, f"{safe_query}_{timestamp}.tsv")
    with open(tsv_file, 'w', encoding='utf-8') as f:
        f.write("Title\tPaperID\tURL\tAuthors\tYear\tCitations\tVenue\tDOI\tarXiv\tPDF\tAbstract\n")
        for r in results:
            title = r.get('title', '').replace('\t', ' ').replace('\n', ' ')
            paper_id = r.get('paperId', '')
            url = r.get('url', '')
            authors = ', '.join(r.get('authors', [])).replace('\t', ' ')
            year = r.get('year', '').replace('\t', ' ')
            citations = r.get('citationCount', '').replace('\t', ' ')
            venue = r.get('venue', '').replace('\t', ' ')
            doi = r.get('doi', '').replace('\t', ' ')
            arxiv = r.get('arxivId', '').replace('\t', ' ')
            pdf = r.get('pdfUrl', '').replace('\t', ' ')
            abstract = r.get('abstract', '').replace('\t', ' ').replace('\n', ' ')[:500]
            f.write(f"{title}\t{paper_id}\t{url}\t{authors}\t{year}\t{citations}\t{venue}\t{doi}\t{arxiv}\t{pdf}\t{abstract}\n")
    console.print(f"[green]✓ Saved TSV: {tsv_file}[/green]")
    
    # Paper IDs
    ids_file = os.path.join(output_dir, f"{safe_query}_{timestamp}_ids.txt")
    with open(ids_file, 'w') as f:
        for r in results:
            if r.get('paperId'):
                f.write(f"{r['paperId']}\n")
    console.print(f"[green]✓ Saved paper IDs: {ids_file}[/green]")
    
    return json_file, tsv_file

def display_results(results):
    """Display results in a rich table."""
    if not results:
        console.print("[yellow]No results[/yellow]")
        return
    
    table = Table(title=f"Results ({len(results)} papers)", box=box.ROUNDED)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan", width=30)
    table.add_column("Authors", style="green", width=18)
    table.add_column("Year", style="yellow", width=8)
    table.add_column("Citations", style="magenta", width=10)
    table.add_column("PDF", style="blue", width=8)
    table.add_column("Figs", style="red", width=5)
    
    for i, paper in enumerate(results[:20], 1):
        title = paper.get('title', 'Unknown')[:28]
        authors_raw = paper.get('authors', [])
        if isinstance(authors_raw, list):
            authors = ', '.join(authors_raw[:2])[:16]
            if len(authors_raw) > 2:
                authors += ' et al.'
        else:
            authors = str(authors_raw)[:16]
        year = paper.get('year', '')[:8]
        citations = paper.get('citationCount', '')[:10]
        has_pdf = "✅" if paper.get('pdfFile') else "—"
        figs = f"{len(paper.get('downloadedFigures', []))}" if paper.get('downloadedFigures') else "—"
        table.add_row(str(i), title, authors, year, citations, has_pdf, figs)
    
    console.print(table)
    if len(results) > 20:
        console.print(f"[dim]... and {len(results)-20} more[/dim]")

# ============ MAIN INTERFACE ============
def main():
    """Command line interface."""
    # Check dependencies
    try:
        import websocket
    except ImportError:
        console.print("[yellow]Installing websocket-client...[/yellow]")
        subprocess.run([sys.executable, "-m", "pip", "install", "websocket-client"], check=True)
        import websocket
    
    os.makedirs("semantic_results", exist_ok=True)
    
    # Command line mode
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        console.print(f"[bold blue]🔍 Searching: {query}[/bold blue]")
        
        deep_scrape = Prompt.ask("Deep scrape? (download PDFs/figures)", choices=["y", "n"], default="y")
        
        if deep_scrape == "y":
            max_pages = int(Prompt.ask("Pages to scrape", default="3"))
            papers_per_page = int(Prompt.ask("Papers per page", default="10"))
            results = scrape_papers(query, max_pages, papers_per_page)
        else:
            # Quick search would go here (simplified)
            console.print("[yellow]Quick search not implemented, using deep scrape[/yellow]")
            results = scrape_papers(query, 1, 10)
        
        if results:
            display_results(results)
            save_results(query, results)
            pdf_count = len([r for r in results if r.get('pdfFile')])
            fig_count = len([r for r in results if r.get('downloadedFigures')])
            total_figs = sum(len(r.get('downloadedFigures', [])) for r in results)
            console.print(f"\n[bold green]✓ Complete![/bold green]")
            console.print(f"[dim]Papers: {len(results)} | PDFs: {pdf_count} | Papers with figures: {fig_count} | Total figures: {total_figs}[/dim]")
        else:
            console.print("[red]No results[/red]")
        
        cleanup()
        return
    
    # Interactive mode
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold blue]📚 SEMANTIC SCHOLAR SCRAPER[/bold blue]\n"
            "Extract academic papers with PDFs and figures",
            border_style="blue"
        ))
        
        console.print("\n[cyan]1.[/cyan] 🔍 Search & Scrape")
        console.print("[cyan]2.[/cyan] 📊 View Saved Results")
        console.print("[cyan]3.[/cyan] 🚪 Exit")
        
        choice = Prompt.ask("Choice", choices=["1", "2", "3"])
        
        if choice == "1":
            query = Prompt.ask("Search query", default="embeddings")
            max_pages = int(Prompt.ask("Pages to scrape", default="3"))
            papers_per_page = int(Prompt.ask("Papers per page", default="10"))
            
            results = scrape_papers(query, max_pages, papers_per_page)
            
            if results:
                display_results(results)
                save_results(query, results)
                pdf_count = len([r for r in results if r.get('pdfFile')])
                fig_count = len([r for r in results if r.get('downloadedFigures')])
                total_figs = sum(len(r.get('downloadedFigures', [])) for r in results)
                console.print(f"\n[green]PDFs: {pdf_count} | Papers with figures: {fig_count} | Total figures: {total_figs}[/green]")
            else:
                console.print("[red]No results[/red]")
                
        elif choice == "2":
            if os.path.exists("semantic_results"):
                json_files = [f for f in os.listdir("semantic_results") if f.endswith('.json')]
                if json_files:
                    console.print("[cyan]Saved results:[/cyan]")
                    for f in sorted(json_files)[-10:]:
                        size = os.path.getsize(os.path.join("semantic_results", f))
                        console.print(f"  • {f} ({size:,} bytes)")
                    
                    file_choice = Prompt.ask("File to view (or q)", default="q")
                    if file_choice != 'q':
                        matched = next((f for f in json_files if f == file_choice or f.startswith(file_choice)), None)
                        if matched:
                            with open(os.path.join("semantic_results", matched), 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                console.print(Panel.fit(
                                    f"[bold]Query: {data.get('query', 'Unknown')}[/bold]\n"
                                    f"Papers: {data.get('total', 0)}\n"
                                    f"Date: {data.get('timestamp', 'Unknown')}",
                                    border_style="cyan"
                                ))
                                display_results(data.get('results', []))
                        else:
                            console.print("[red]File not found[/red]")
                else:
                    console.print("[yellow]No saved results[/yellow]")
            else:
                console.print("[yellow]No results directory[/yellow]")
                
        elif choice == "3":
            cleanup()
            console.print("[bold red]Goodbye![/bold red]")
            break
        
        if choice != "3":
            Prompt.ask("Press Enter to continue...", default="")

if __name__ == "__main__":
    main()
