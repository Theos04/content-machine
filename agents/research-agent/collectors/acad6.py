# semanticscholar_scraper.py  –  v2 with correct CSS selectors
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.progress import (Progress, SpinnerColumn, TextColumn,
                           BarColumn, TimeElapsedColumn, TimeRemainingColumn)
from rich import box
import subprocess, os, time, json, requests, websocket
from urllib.parse import quote
import signal, atexit, shutil
from datetime import datetime
import sys, re, random

console = Console()

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
CHROME_PORT     = 9240
CHROME_USER_DIR = os.path.expanduser("~/chrome-profile-semantic")
HEADLESS        = True    # ← flip to False for visible browser

REQUEST_DELAY = 2.0
MAX_RETRIES   = 3
COOLDOWN_BASE = 5

chrome_process = None

def cleanup():
    global chrome_process
    if chrome_process:
        try: chrome_process.terminate()
        except Exception: pass

atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda sig, frame: (cleanup(), exit(0)))


# ─────────────────────────────────────────────────────────────
# Chrome launch
# ─────────────────────────────────────────────────────────────

def find_chrome():
    for name in ["chromium-browser","chromium","google-chrome","google-chrome-stable","brave-browser"]:
        path = shutil.which(name)
        if path:
            console.print(f"[green]✓ Found browser: {path}[/green]")
            return path
    console.print("[red]No Chrome/Chromium binary found![/red]")
    return None

def is_cdp_alive(port=CHROME_PORT):
    try:
        requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
        return True
    except Exception:
        return False

def start_chrome():
    global chrome_process
    subprocess.run(["pkill","-f",f"remote-debugging-port={CHROME_PORT}"], capture_output=True)
    time.sleep(1)
    chrome_cmd = find_chrome()
    if not chrome_cmd: return False
    os.makedirs(CHROME_USER_DIR, exist_ok=True)
    cmd = [
        chrome_cmd,
        f"--remote-debugging-port={CHROME_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={CHROME_USER_DIR}",
        "--no-sandbox","--disable-gpu","--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--no-first-run","--no-default-browser-check",
        "--disable-extensions","--disable-background-networking",
        "--disable-blink-features=AutomationControlled",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    if HEADLESS:
        cmd.append("--headless=new")
        mode = "headless"
    else:
        mode = f"visible (DISPLAY={os.environ.get('DISPLAY','not set')})"
    console.print(f"[cyan]Launching Chrome [{mode}] on port {CHROME_PORT}…[/cyan]")
    console.print(f"[dim]User-data-dir: {CHROME_USER_DIR}[/dim]")
    try:
        chrome_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                      TextColumn("{task.percentage:>3.0f}%"), TimeElapsedColumn()) as p:
            t = p.add_task(f"[cyan]Starting Chrome [{mode}]…", total=30)
            for i in range(30):
                time.sleep(1); p.update(t, advance=1)
                if is_cdp_alive():
                    console.print(f"[green]✓ Chrome ready [{mode}] ({i+1}s)[/green]")
                    return True
                if chrome_process.poll() is not None:
                    console.print(f"[red]Chrome crashed (exit {chrome_process.returncode})[/red]")
                    break
    except Exception as e:
        console.print(f"[red]Launch error: {e}[/red]")
    return False

start_chrome_headless = start_chrome   # alias


# ─────────────────────────────────────────────────────────────
# CDP plumbing
# ─────────────────────────────────────────────────────────────

def get_ws_url():
    try:
        tabs = requests.get(f"http://127.0.0.1:{CHROME_PORT}/json/list", timeout=5).json()
        if tabs: return tabs[0].get("webSocketDebuggerUrl")
    except Exception as e:
        console.print(f"[yellow]WebSocket URL error: {e}[/yellow]")
    return None

def connect_cdp():
    ws_url = get_ws_url()
    if not ws_url: return None
    console.print("[cyan]Connecting CDP…[/cyan]")
    ws = websocket.create_connection(ws_url, timeout=30)
    for method in ["Page.enable","Runtime.enable","Network.enable"]:
        ws.send(json.dumps({"id":1,"method":method})); time.sleep(0.3)
    ws.settimeout(0.1)
    while True:
        try: ws.recv()
        except: break
    ws.settimeout(None)
    return ws

def send_cdp(ws, _id, method, params=None):
    ws.send(json.dumps({"id":_id,"method":method,"params":params or {}}))

def recv_cdp(ws, expected_id=None):
    while True:
        try:
            res = json.loads(ws.recv())
            if "id" in res and (expected_id is None or res["id"] == expected_id):
                return res
        except Exception: continue

def evaluate_cdp(ws, expression, _id=100):
    send_cdp(ws, _id, "Runtime.evaluate",
             {"expression":expression,"returnByValue":True,"awaitPromise":True})
    result = recv_cdp(ws, _id)
    if "result" in result and "result" in result["result"]:
        return result["result"]["result"].get("value")
    return None

def wait_for_page(ws, timeout=20):
    """Wait until the page has meaningful content."""
    for attempt in range(timeout):
        state = evaluate_cdp(ws, """
        (function(){
            const cards = document.querySelectorAll('[data-paper-id]');
            if (cards.length > 0) return 'ready';
            const loading = document.querySelector('[data-test-id="icon-loading-serp"],.loading-controls');
            if (loading) return 'loading';
            if (document.body && document.body.innerText.length > 200) return 'content';
            return 'empty';
        })()
        """)
        if state == 'ready':
            console.print(f"[green]✓ Page ready ({attempt+1}s)[/green]")
            return True
        if state == 'loading':
            console.print(f"[dim]Loading… ({attempt+1})[/dim]")
        else:
            console.print(f"[dim]Waiting ({attempt+1})…[/dim]")
        time.sleep(1)
    console.print("[yellow]Page load timeout – continuing anyway[/yellow]")
    return True

def navigate_cdp(ws, url):
    console.print(f"[cyan]→ {url[:90]}[/cyan]")
    send_cdp(ws, 1000, "Page.navigate", {"url":url})
    time.sleep(2)
    return wait_for_page(ws)


# ─────────────────────────────────────────────────────────────
# Pagination – uses data-test-id selectors found in the HTML
# ─────────────────────────────────────────────────────────────

def get_pagination_info(ws):
    """Return (current_page, total_pages) from the pager widget."""
    info = evaluate_cdp(ws, """
    (function(){
        const pager = document.querySelector('.cl-pager');
        if (!pager) return {curr:1, total:1};
        const curr  = parseInt(pager.dataset.currPageNum  || '1');
        const total = parseInt(pager.dataset.totalPages   || '1');
        return {curr, total};
    })()
    """)
    if isinstance(info, dict):
        return info.get('curr', 1), info.get('total', 1)
    return 1, 1

def click_next_page(ws):
    """Click the next-page button (data-test-id='next-page')."""
    result = evaluate_cdp(ws, """
    (function(){
        const btn = document.querySelector('button[data-test-id="next-page"]');
        if (!btn) return 'not_found';
        if (btn.disabled) return 'disabled';
        btn.click(); return 'clicked';
    })()
    """)
    if result == 'clicked':
        console.print("[green]✓ Next page clicked[/green]")
        time.sleep(3)
        wait_for_page(ws, timeout=10)
        return True
    console.print(f"[yellow]Next page: {result}[/yellow]")
    return False

def click_page_number(ws, page_num):
    """Click a specific page-number button."""
    result = evaluate_cdp(ws, f"""
    (function(){{
        const btn = document.querySelector('button[data-test-id="inactive-page"][data-page-num="{page_num}"]');
        if (!btn) return 'not_found';
        btn.click(); return 'clicked';
    }})()
    """)
    if result == 'clicked':
        console.print(f"[green]✓ Jumped to page {page_num}[/green]")
        time.sleep(3)
        wait_for_page(ws, timeout=10)
        return True
    return False


# ─────────────────────────────────────────────────────────────
# Extract paper cards from any listing page (search / citations)
# Uses data-paper-id and data-test-id selectors from the real HTML
# ─────────────────────────────────────────────────────────────

EXTRACT_CARDS_JS = """
(function(){
    const rows = document.querySelectorAll('[data-paper-id]');
    const papers = [];
    rows.forEach(function(row){
        const paperId = row.dataset.paperId || '';

        // Title & URL
        const titleEl = row.querySelector(
            'a[data-test-id="title-link"] h2, ' +
            'a[data-test-id="citation-paper-title"] h3'
        );
        const linkEl = row.querySelector(
            'a[data-test-id="title-link"], ' +
            'a[data-test-id="citation-paper-title"]'
        );
        const title = titleEl ? titleEl.innerText.trim() : '';
        const href  = linkEl  ? linkEl.href : '';

        // TLDR (first non-button span inside tldr container)
        let tldr = '';
        const tldrWrap = row.querySelector('.tldr-abstract-replacement');
        if (tldrWrap) {
            const spans = tldrWrap.querySelectorAll('span > span');
            spans.forEach(function(s){
                if (!tldr && s.innerText.trim().length > 20) tldr = s.innerText.trim();
            });
        }

        // Authors (name + author-id)
        const authors = [];
        row.querySelectorAll('span[data-test-id="author-list"]').forEach(function(a){
            const nameEl = a.querySelector('a.cl-paper-authors__author-box');
            const name   = nameEl ? nameEl.innerText.trim() : '';
            const aid    = a.dataset.heapAuthorId || '';
            if (name) authors.push({name, authorId: aid});
        });

        // Venue
        const venueEl = row.querySelector(
            'a.cl-paper-venue[data-test-id="normalized-venue-link"], ' +
            'a.cl-paper-venue[data-heap-id="paper-meta-venue"]'
        );
        const venue = venueEl ? venueEl.innerText.trim() : '';

        // Field of study
        const fosEl = row.querySelector('span.cl-paper-fos');
        const fos   = fosEl ? fosEl.innerText.trim() : '';

        // Pub date
        const dateEl = row.querySelector('span.cl-paper-pubdates');
        const pubDate = dateEl ? dateEl.innerText.trim() : '';

        // Citation count (search page uses v2-citations; citation page uses plain text)
        let citations = '';
        const citV2 = row.querySelector('span.cl-paper-stats__v2-citations');
        if (citV2) {
            citations = citV2.innerText.trim();
        } else {
            const citStat = row.querySelector('[data-test-id="total-citations-stat"] .cl-paper-stat');
            if (citStat) {
                const m = citStat.innerText.match(/\\d[\\d,]*/);
                if (m) citations = m[0].replace(/,/g,'');
            }
        }

        // arXiv PDF link
        const arxivEl = row.querySelector('a[data-heap-link-type="arxiv"]');
        const arxivUrl = arxivEl ? arxivEl.href : '';

        // Open-access PDF badge
        const oaBadge = row.querySelector('[data-test-id="paper-badge-open_access"]');
        const hasOpenPDF = !!oaBadge;

        // Highly Influenced flag (citation pages)
        const highlyInfluenced = !!row.querySelector('[data-test-id="highlyInfluenced"]');

        // Excerpt count (citation pages)
        const excerptBtn = row.querySelector('button[data-test-id="excerpt"] .cl-button__label');
        const excerpts   = excerptBtn ? excerptBtn.innerText.trim() : '';

        // Semantic Reader link  /reader/{paper_id}
        const readerEl = row.querySelector('a[href*="/reader/"]');
        const readerUrl = readerEl ? readerEl.href : '';

        if (paperId || title) {
            papers.push({
                paperId, title, href, tldr,
                authors, venue, fos, pubDate,
                citations, arxivUrl, hasOpenPDF,
                highlyInfluenced, excerpts, readerUrl
            });
        }
    });
    return papers;
})()
"""

def extract_cards_from_page(ws):
    """Run EXTRACT_CARDS_JS and return list of paper dicts."""
    result = evaluate_cdp(ws, EXTRACT_CARDS_JS)
    if isinstance(result, list):
        return result
    return []


# ─────────────────────────────────────────────────────────────
# Extract rich detail from a single paper's detail page
# ─────────────────────────────────────────────────────────────

PAPER_DETAIL_JS = """
(function(){
    const d = {
        title:'', authors:[], abstract:'', year:'', venue:'',
        doi:'', arxivId:'', pdfUrl:'', readerUrl:'',
        citationCount:'', referenceCount:'',
        externalLinks:[], codeRepos:[], figures:[],
        tldr:'', fos:'', openAccess: false
    };

    // Title
    const h1 = document.querySelector('h1,[data-test-id="paper-title"]');
    if (h1) d.title = h1.innerText.trim();

    // Authors with IDs
    const authors = [];
    document.querySelectorAll('span[data-test-id="author-list"]').forEach(function(a){
        const nameEl = a.querySelector('a.cl-paper-authors__author-box');
        const name   = nameEl ? nameEl.innerText.trim() : '';
        const aid    = a.dataset.heapAuthorId || '';
        if (name) authors.push({name, authorId: aid});
    });
    d.authors = authors;

    // Abstract
    const absEl = document.querySelector(
        '.abstract, .paper-abstract, [data-test-id="abstract"], .description'
    );
    if (absEl) d.abstract = absEl.innerText.trim().replace(/^Abstract\\s*/i,'').trim();

    // Year from pubdates or body text
    const dateEl = document.querySelector('span.cl-paper-pubdates');
    const yearSrc = dateEl ? dateEl.innerText : document.body.innerText;
    const ym = yearSrc.match(/\\b(19|20)\\d{2}\\b/);
    if (ym) d.year = ym[0];

    // Venue
    const venueEl = document.querySelector(
        'a.cl-paper-venue[data-test-id="normalized-venue-link"],' +
        '.venue,.journal,[data-test-id="venue"]'
    );
    if (venueEl) d.venue = venueEl.innerText.trim();

    // Field of study
    const fosEl = document.querySelector('span.cl-paper-fos');
    if (fosEl) d.fos = fosEl.innerText.trim();

    // DOI
    const doiEl = document.querySelector('a[href*="doi.org"]');
    if (doiEl) { const m=doiEl.href.match(/10\\.\\d+\\/.+/); if(m) d.doi=m[0]; }

    // arXiv
    const arxivEl = document.querySelector('a[href*="arxiv.org"], a[data-heap-link-type="arxiv"]');
    if (arxivEl) {
        d.pdfUrl = arxivEl.href;
        const m = arxivEl.href.match(/\\d{4}\\.\\d{4,5}/);
        if (m) d.arxivId = m[0];
    }

    // Semantic Reader  /reader/{id}
    const readerEl = document.querySelector('a[data-test-id="reader-button"], a[href*="/reader/"]');
    if (readerEl) d.readerUrl = readerEl.href;

    // Open-access badge
    d.openAccess = !!document.querySelector('[data-test-id="paper-badge-open_access"]');

    // Citation & reference counts
    const citStat = document.querySelector(
        '[data-test-id="total-citations-stat"] span.cl-paper-stats__v2-citations,' +
        '.citation-count,[data-test-id="citation-count"]'
    );
    if (citStat) { const m=citStat.innerText.match(/[\\d,]+/); if(m) d.citationCount=m[0].replace(/,/g,''); }

    const refEl = document.querySelector(
        'h2.dropdown-filters__result-count__citations,' +
        '.references .count,[data-test-id="references-count"]'
    );
    if (refEl) { const m=refEl.innerText.match(/[\\d,]+/); if(m) d.referenceCount=m[0].replace(/,/g,''); }

    // TLDR
    const tldrWrap = document.querySelector('.tldr-abstract-replacement');
    if (tldrWrap) {
        const spans = tldrWrap.querySelectorAll('span > span');
        spans.forEach(function(s){
            if (!d.tldr && s.innerText.trim().length > 20) d.tldr = s.innerText.trim();
        });
    }

    // GitHub / code repos
    document.querySelectorAll('a[href*="github.com"]').forEach(function(l){
        d.codeRepos.push(l.href);
    });

    // External resource links (data, supplementary, code, dataset)
    document.querySelectorAll('a[href^="http"]').forEach(function(l){
        const t = l.innerText.trim().toLowerCase();
        if (l.href.includes('doi.org')||l.href.includes('arxiv.org')) return;
        if (['code','github','data','dataset','supplementary','additional','appendix'].some(k=>t.includes(k))) {
            d.externalLinks.push({url:l.href, text:l.innerText.trim()||'Link'});
        }
    });

    // Figures
    document.querySelectorAll('img,[data-src]').forEach(function(el){
        const src = el.src || el.getAttribute('data-src') || '';
        if (src && /\\.(png|jpg|jpeg|gif|webp)/i.test(src)) d.figures.push(src);
    });

    return d;
})()
"""


# ─────────────────────────────────────────────────────────────
# Multi-page search scraper (uses real pagination selectors)
# ─────────────────────────────────────────────────────────────

def get_all_paper_entries_from_search(ws, max_pages=5):
    """Collect paper card data across multiple search-result pages."""
    all_papers = []
    page = 0

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                  TextColumn("{task.percentage:>3.0f}%"), TimeElapsedColumn()) as prog:
        task = prog.add_task("[cyan]Scraping search pages…", total=max_pages)

        while page < max_pages:
            page += 1
            console.print(f"[cyan]📄 Page {page}/{max_pages}[/cyan]")

            cards = extract_cards_from_page(ws)
            if not cards:
                console.print("[yellow]No cards found on this page[/yellow]")
                break

            all_papers.extend(cards)
            curr_pg, total_pg = get_pagination_info(ws)
            console.print(
                f"[green]  +{len(cards)} cards  (total so far: {len(all_papers)}, "
                f"site pages: {curr_pg}/{total_pg})[/green]"
            )
            prog.update(task, advance=1)

            if page < max_pages:
                _cooldown(COOLDOWN_BASE + random.uniform(0, 2), "page cooldown")
                if not click_next_page(ws):
                    console.print("[yellow]No more pages[/yellow]")
                    break

    # Deduplicate by paperId (keep first occurrence)
    seen = set()
    unique = []
    for p in all_papers:
        key = p.get('paperId') or p.get('href')
        if key and key not in seen:
            seen.add(key); unique.append(p)
    console.print(f"[bold green]Unique papers collected: {len(unique)}[/bold green]")
    return unique


# ─────────────────────────────────────────────────────────────
# Deep detail scraper for individual paper pages
# ─────────────────────────────────────────────────────────────

def scrape_paper_detail(ws, paper_entry, output_dir, paper_num=0, total=0):
    """
    Navigate to a paper's detail page and extract everything.
    paper_entry is a dict from extract_cards_from_page().
    """
    url = paper_entry.get('href') or ''
    if not url:
        pid = paper_entry.get('paperId', '')
        url = f"https://www.semanticscholar.org/paper/{pid}" if pid else ''
    if not url:
        return None

    label = f"[{paper_num}/{total}] " if total else ''
    console.print(f"[cyan]📄 {label}{url[:80]}…[/cyan]")

    send_cdp(ws, 2000, "Page.navigate", {"url": url})
    time.sleep(1)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                  TextColumn("{task.percentage:>3.0f}%"), TimeElapsedColumn()) as p:
        t = p.add_task("[cyan]Loading paper…", total=15)
        for _ in range(15):
            p.update(t, advance=1)
            st = evaluate_cdp(ws, """
            (function(){
                if (document.querySelector('.loading,.spinner,.skeleton')) return 'loading';
                const c = document.querySelector('article,.paper-detail,.paper-content,h1');
                if (c && c.innerText && c.innerText.length > 50) return 'loaded';
                return 'waiting';
            })()""")
            if st == 'loaded': break
            time.sleep(0.5)

    # Run both extractions
    detail = evaluate_cdp(ws, PAPER_DETAIL_JS) or {}
    full_html = evaluate_cdp(ws, "document.documentElement.outerHTML") or ""

    # Merge search-card data with detail-page data (detail wins)
    merged = {**paper_entry, **{k:v for k,v in detail.items() if v}}
    merged['url'] = url

    # Extract paper ID from URL if missing
    if not merged.get('paperId') and '/paper/' in url:
        merged['paperId'] = url.split('/paper/')[-1].split('?')[0]

    os.makedirs(output_dir, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*]', '_', merged.get('title','untitled')[:50])

    # Save raw HTML
    html_path = os.path.join(output_dir, f"{safe}_page.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(full_html)
    merged['htmlFile'] = html_path

    # Download PDF
    pdf_url = merged.get('pdfUrl') or merged.get('arxivUrl', '')
    if pdf_url:
        pdf_path = download_pdf(pdf_url, output_dir, merged.get('title','untitled'))
        if pdf_path: merged['pdfFile'] = pdf_path

    # Download figures (up to 5)
    figs = merged.get('figures', [])
    if figs:
        fig_dir = os.path.join(output_dir, 'figures')
        os.makedirs(fig_dir, exist_ok=True)
        dl_figs = []
        for i, src in enumerate(figs[:5]):
            if src.startswith('//'): src = 'https:' + src
            elif src.startswith('/'): src = 'https://www.semanticscholar.org' + src
            if not src.startswith('http'): continue
            try:
                time.sleep(0.4)
                r = requests.get(src, timeout=20, headers={'User-Agent':'Mozilla/5.0'})
                if r.status_code == 200:
                    ext = re.search(r'\.(png|jpg|jpeg|gif|webp)', src, re.I)
                    ext = ext.group(1).lower() if ext else 'jpg'
                    fp = os.path.join(fig_dir, f"fig_{i+1}.{ext}")
                    with open(fp,'wb') as f: f.write(r.content)
                    dl_figs.append(fp)
                    console.print(f"[dim]  ✓ fig_{i+1}.{ext}[/dim]")
            except Exception as e:
                console.print(f"[dim]  fig error: {e}[/dim]")
        merged['downloadedFigures'] = dl_figs

    return merged


# ─────────────────────────────────────────────────────────────
# PDF download
# ─────────────────────────────────────────────────────────────

def download_pdf(pdf_url, output_dir, title, retries=3):
    safe = re.sub(r'[<>:"/\\|?*]', '_', title[:50])
    path = os.path.join(output_dir, f"{safe}.pdf")
    if os.path.exists(path):
        console.print(f"[dim]PDF already exists: {safe}.pdf[/dim]"); return path
    UAS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120',
    ]
    for attempt in range(retries):
        try:
            r = requests.get(pdf_url, timeout=60, stream=True, headers={
                'User-Agent': UAS[attempt % len(UAS)],
                'Accept': 'application/pdf,*/*',
                'Referer': 'https://www.semanticscholar.org/',
            })
            if r.status_code == 200:
                with open(path,'wb') as f:
                    for chunk in r.iter_content(8192):
                        if chunk: f.write(chunk)
                console.print(f"[green]  ✓ PDF: {safe}.pdf[/green]"); return path
            else:
                console.print(f"[yellow]  PDF {r.status_code}[/yellow]")
        except Exception as e:
            console.print(f"[red]  PDF error: {e}[/red]")
        if attempt < retries-1:
            time.sleep(2**attempt + random.uniform(0,1))
    return None


# ─────────────────────────────────────────────────────────────
# Cooldown helper
# ─────────────────────────────────────────────────────────────

def _cooldown(seconds, label="cooldown"):
    console.print(f"[yellow]⏳ {label}: {seconds:.1f}s[/yellow]")
    with Progress(SpinnerColumn(), TextColumn(f"[yellow]{label}"),
                  BarColumn(), TimeRemainingColumn()) as p:
        t = p.add_task("", total=seconds)
        for _ in range(int(seconds * 10)):
            time.sleep(0.1); p.update(t, advance=0.1)


# ─────────────────────────────────────────────────────────────
# Main scrape orchestrator
# ─────────────────────────────────────────────────────────────

def scrape_multiple_papers(query, max_pages=3, max_papers=30, deep=True):
    ws = None
    results = []
    try:
        if not is_cdp_alive():
            if not start_chrome(): return []
        ws = connect_cdp()
        if not ws: return []

        search_url = f"https://www.semanticscholar.org/search?q={quote(query)}"
        navigate_cdp(ws, search_url)
        time.sleep(2)

        # Collect card summaries from search pages
        entries = get_all_paper_entries_from_search(ws, max_pages)
        entries = entries[:max_papers]
        console.print(f"[bold cyan]Processing {len(entries)} papers…[/bold cyan]")

        safe_q = re.sub(r'[<>:"/\\|?*]', '_', query)
        base_dir = os.path.join("semantic_results", safe_q)
        os.makedirs(base_dir, exist_ok=True)

        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                      TextColumn("{task.percentage:>3.0f}%"), TimeElapsedColumn(),
                      TimeRemainingColumn()) as prog:
            pt = prog.add_task(f"[cyan]Papers", total=len(entries))

            for i, entry in enumerate(entries, 1):
                if i > 1:
                    cd = REQUEST_DELAY + random.uniform(0,1) + (1 if i > 3 else 0)
                    _cooldown(cd, f"paper {i}/{len(entries)} cooldown")

                paper_dir = os.path.join(base_dir, f"paper_{i:03d}")

                if deep:
                    info = scrape_paper_detail(ws, entry, paper_dir,
                                               paper_num=i, total=len(entries))
                else:
                    info = entry
                    info['url'] = entry.get('href', '')

                if info:
                    results.append(info)
                    title = info.get('title','?')[:60]
                    console.print(f"[green]  ✓ {title}[/green]")
                    auths = info.get('authors', [])
                    if auths:
                        names = ', '.join(a['name'] if isinstance(a,dict) else a for a in auths[:3])
                        console.print(f"[dim]    Authors: {names}[/dim]")
                    for field, label in [('year','Year'),('citations','Citations'),
                                         ('doi','DOI'),('arxivId','arXiv'),
                                         ('readerUrl','Reader'),('tldr','TLDR')]:
                        val = info.get(field,'')
                        if val: console.print(f"[dim]    {label}: {str(val)[:80]}[/dim]")
                    if info.get('codeRepos'):
                        console.print(f"[dim]    💻 {len(info['codeRepos'])} code repo(s)[/dim]")
                    if info.get('highlyInfluenced'):
                        console.print(f"[dim]    ⭐ Highly Influenced[/dim]")
                    if info.get('pdfFile'):
                        console.print(f"[dim]    📄 PDF saved[/dim]")

                prog.update(pt, advance=1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback; traceback.print_exc()
    finally:
        if ws:
            try: ws.close()
            except: pass
    return results


# ─────────────────────────────────────────────────────────────
# Save & display
# ─────────────────────────────────────────────────────────────

def save_results(query, results, output_dir="semantic_results"):
    os.makedirs(output_dir, exist_ok=True)
    safe_q = re.sub(r'[<>:"/\\|?*]', '_', query)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON
    json_path = os.path.join(output_dir, f"{safe_q}_{ts}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({"query":query,"timestamp":ts,"total":len(results),"results":results},
                  f, indent=2, ensure_ascii=False)
    console.print(f"[green]✓ JSON: {json_path}[/green]")

    # TSV – now includes TLDR, FOS, arXiv, reader URL, highly-influenced
    tsv_path = os.path.join(output_dir, f"{safe_q}_{ts}.tsv")
    with open(tsv_path, 'w', encoding='utf-8') as f:
        f.write("Title\tPaperID\tURL\tAuthors\tYear\tCitations\tVenue\tFOS\t"
                "DOI\tarXiv\tReaderURL\tOpenAccess\tHighlyInfluenced\tCodeRepos\t"
                "ExternalLinks\tPDFFile\tTLDR\n")
        for r in results:
            def c(v): return str(v or '').replace('\t',' ').replace('\n',' ')
            auths = r.get('authors', [])
            if isinstance(auths, list):
                auth_str = ', '.join(
                    a['name'] if isinstance(a, dict) else str(a) for a in auths
                )
            else:
                auth_str = str(auths)
            repos = ' | '.join(r.get('codeRepos', []))
            links = ' | '.join(
                (l['url'] if isinstance(l,dict) else str(l))
                for l in r.get('externalLinks', [])
            )
            f.write('\t'.join([
                c(r.get('title')), c(r.get('paperId')), c(r.get('url','') or r.get('href','')),
                c(auth_str), c(r.get('year')), c(r.get('citations') or r.get('citationCount','')),
                c(r.get('venue')), c(r.get('fos')),
                c(r.get('doi')), c(r.get('arxivId')),
                c(r.get('readerUrl')), c(r.get('openAccess','')), c(r.get('highlyInfluenced','')),
                c(repos), c(links), c(r.get('pdfFile','')),
                c(r.get('tldr',''))[:300],
            ]) + '\n')
    console.print(f"[green]✓ TSV: {tsv_path}[/green]")

    # Paper IDs list
    ids_path = os.path.join(output_dir, f"{safe_q}_{ts}_ids.txt")
    with open(ids_path, 'w') as f:
        for r in results:
            if r.get('paperId'): f.write(r['paperId'] + '\n')
    console.print(f"[green]✓ IDs: {ids_path}[/green]")

    return json_path, tsv_path

def display_results(results):
    if not results:
        console.print("[yellow]No results[/yellow]"); return
    tbl = Table(title=f"Results ({len(results)} papers)", box=box.SIMPLE)
    tbl.add_column("#", style="dim", width=4)
    tbl.add_column("Title", style="cyan", width=32)
    tbl.add_column("Authors", style="green", width=20)
    tbl.add_column("Year", style="yellow", width=6)
    tbl.add_column("Cit.", style="magenta", width=6)
    tbl.add_column("PDF", width=4)
    tbl.add_column("⭐", width=4)
    tbl.add_column("arXiv", style="blue", width=5)
    for i, p in enumerate(results[:25], 1):
        auths = p.get('authors', [])
        if isinstance(auths, list):
            names = ', '.join(
                (a['name'] if isinstance(a, dict) else str(a)) for a in auths[:2]
            )
            if len(auths) > 2: names += ' et al.'
        else:
            names = str(auths)
        tbl.add_row(
            str(i),
            (p.get('title') or '')[:32],
            names[:20],
            (p.get('year') or '')[:6],
            (p.get('citations') or p.get('citationCount',''))[:6],
            "✅" if p.get('pdfFile') else ("📖" if p.get('readerUrl') else "❌"),
            "⭐" if p.get('highlyInfluenced') else "",
            "✓" if p.get('arxivId') or p.get('arxivUrl') else "",
        )
    console.print(tbl)
    if len(results) > 25:
        console.print(f"[dim]… +{len(results)-25} more[/dim]")


# ─────────────────────────────────────────────────────────────
# CLI / interactive menu
# ─────────────────────────────────────────────────────────────

def main():
    global HEADLESS

    mode_str = "[bold green]HEADLESS[/bold green]" if HEADLESS else "[bold yellow]VISIBLE[/bold yellow]"
    console.print(Panel.fit(
        f"Chrome: {mode_str}  Port: [cyan]{CHROME_PORT}[/cyan]\n"
        f"User-data-dir: [dim]{CHROME_USER_DIR}[/dim]",
        title="Config", border_style="blue"
    ))

    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        console.print(f"[bold blue]🔍 {query}[/bold blue]")
        deep   = Prompt.ask("Deep scrape each paper?", choices=["y","n"], default="y") == "y"
        pages  = int(Prompt.ask("Search pages", default="3"))
        limit  = int(Prompt.ask("Max papers", default="30"))
        results = scrape_multiple_papers(query, max_pages=pages, max_papers=limit, deep=deep)
        if results:
            display_results(results)
            save_results(query, results)
            console.print(f"\n[bold green]✓ Done! {len(results)} papers[/bold green]")
            console.print(f"[dim]PDFs: {len([r for r in results if r.get('pdfFile')])}[/dim]")
            console.print(f"[dim]With arXiv: {len([r for r in results if r.get('arxivId') or r.get('arxivUrl')])}[/dim]")
            console.print(f"[dim]Highly Influenced: {len([r for r in results if r.get('highlyInfluenced')])}[/dim]")
        else:
            console.print("[red]No results[/red]")
        cleanup(); return

    # Interactive
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold blue]📚 SEMANTIC SCHOLAR SCRAPER v2[/bold blue]\n"
            "Real CSS selectors · TLDR · arXiv · Reader · Highly Influenced · FOS",
            border_style="blue"
        ))
        hl = "[green]ON[/green]" if HEADLESS else "[yellow]OFF[/yellow]"
        console.print(f"\n[cyan]1.[/cyan] 🔍 Quick collect (card data only, fast)")
        console.print(f"[cyan]2.[/cyan] 📄 Deep scrape (full detail + PDF download)")
        console.print(f"[cyan]3.[/cyan] 📊 View saved results")
        console.print(f"[cyan]4.[/cyan] 🖥️  Toggle headless (currently {hl})")
        console.print(f"[cyan]5.[/cyan] 🚪 Exit")

        choice = Prompt.ask("\nChoice", choices=["1","2","3","4","5"])

        if choice == "1":
            query  = Prompt.ask("Search query", default="graph neural networks")
            pages  = int(Prompt.ask("Pages", default="3"))
            limit  = int(Prompt.ask("Max papers", default="50"))
            results = scrape_multiple_papers(query, max_pages=pages, max_papers=limit, deep=False)
            if results: display_results(results); save_results(query, results)
            else: console.print("[red]No results[/red]")

        elif choice == "2":
            query  = Prompt.ask("Search query", default="graph neural networks")
            pages  = int(Prompt.ask("Pages", default="3"))
            limit  = int(Prompt.ask("Max papers", default="30"))
            results = scrape_multiple_papers(query, max_pages=pages, max_papers=limit, deep=True)
            if results:
                display_results(results); save_results(query, results)
                console.print(f"[green]PDFs: {len([r for r in results if r.get('pdfFile')])}[/green]")
            else: console.print("[red]No results[/red]")

        elif choice == "3":
            if os.path.exists("semantic_results"):
                jfiles = [f for f in os.listdir("semantic_results") if f.endswith('.json')]
                for f in sorted(jfiles)[-10:]:
                    sz = os.path.getsize(os.path.join("semantic_results",f))
                    console.print(f"  • {f} ({sz:,} bytes)")
                fc = Prompt.ask("Filename to view (or q)", default="q")
                if fc != 'q':
                    m = next((f for f in jfiles if f==fc or f.startswith(fc)), None)
                    if m:
                        with open(os.path.join("semantic_results",m),'r',encoding='utf-8') as f:
                            data = json.load(f)
                        display_results(data.get('results',[]))
                    else: console.print("[red]Not found[/red]")
            else: console.print("[yellow]No results dir[/yellow]")

        elif choice == "4":
            HEADLESS = not HEADLESS
            console.print(f"[bold green]→ {'HEADLESS' if HEADLESS else 'VISIBLE'} mode[/bold green]")
            if not HEADLESS: console.print("[yellow]Set: export DISPLAY=:1[/yellow]")

        elif choice == "5":
            cleanup(); console.print("[bold red]Goodbye![/bold red]"); break

        if choice != "5":
            Prompt.ask("\nEnter to continue…", default="")


if __name__ == "__main__":
    try:
        import websocket
    except ImportError:
        console.print("[yellow]Installing websocket-client…[/yellow]")
        subprocess.run([sys.executable,"-m","pip","install","websocket-client"], check=True)
        import websocket

    os.makedirs("semantic_results", exist_ok=True)
    main()
