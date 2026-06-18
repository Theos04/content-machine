from typing import List, Dict, Any, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timezone
import logging
import time
import sqlite3
import json
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_REPO_URL = "https://api.github.com/repos"
CACHE_TTL_SECONDS = 86400  # 24 hours


class SortCriterion(Enum):
    STARS = "stars"
    FORKS = "forks"
    UPDATED = "updated"
    BEST_MATCH = "best_match"


class Order(Enum):
    ASC = "asc"
    DESC = "desc"


@dataclass
class GitHubRepo:
    """Strongly typed repository data"""
    full_name: str
    description: str
    url: str
    author: str
    avatar_url: Optional[str]
    stars: int
    forks: int
    watchers: int
    open_issues: int
    language: Optional[str]
    topics: List[str]
    homepage: Optional[str]
    default_branch: str
    size_kb: int
    archived: bool
    disabled: bool
    has_issues: bool
    has_wiki: bool
    has_discussions: bool
    license: Optional[str]
    created_at: str
    updated_at: str
    pushed_at: str
    score: float
    query: str
    source: str = "github"
    collector: str = "github_collector"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GitHubCache:
    """SQLite cache with TTL and pruning"""
    
    def __init__(self, db_path: str = "github_cache.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    full_name TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    etag TEXT,
                    last_modified TEXT,
                    cached_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cached_at ON repositories(cached_at)")
            conn.commit()
    
    def get(self, full_name: str) -> Optional[Dict]:
        """Get cached repo if fresh"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT data, cached_at FROM repositories WHERE full_name = ?",
                (full_name,)
            ).fetchone()
            
            if row:
                data, cached_at = row
                if time.time() - cached_at < CACHE_TTL_SECONDS:
                    return json.loads(data)
        return None
    
    def set(self, full_name: str, data: Dict, etag: str = "", last_modified: str = ""):
        """Cache repository data"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO repositories (full_name, data, etag, last_modified, cached_at)
                VALUES (?, ?, ?, ?, ?)
            """, (full_name, json.dumps(data), etag, last_modified, time.time()))
            conn.commit()
    
    def get_etag(self, full_name: str) -> Optional[str]:
        """Get stored ETag for conditional requests"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT etag FROM repositories WHERE full_name = ?",
                (full_name,)
            ).fetchone()
            return row[0] if row else None
    
    def prune(self, max_age_days: int = 7):
        """Remove old entries"""
        cutoff = time.time() - (max_age_days * 86400)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM repositories WHERE cached_at < ?", (cutoff,))
            conn.commit()


class GitHubCollector:
    """Production-grade GitHub repository collector"""
    
    def __init__(
        self,
        token: Optional[str] = None,
        rate_limit: float = 1.0,
        timeout: int = 30,
        cache_enabled: bool = True,
        cache_db: str = "github_cache.db"
    ):
        """
        Args:
            token: GitHub Personal Access Token (increases rate limit to 5000/hr)
            rate_limit: Requests per second (default 1.0 for 5000/hr)
            timeout: Request timeout in seconds
            cache_enabled: Enable SQLite caching
            cache_db: SQLite database path
        """
        self.token = token
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.cache_enabled = cache_enabled
        self.last_request_time: Optional[float] = None
        self.cache = GitHubCache(cache_db) if cache_enabled else None
        
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Configure session with retries and headers"""
        session = requests.Session()
        
        # Retry strategy
        retries = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=20)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        # Headers
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Collector/2.0 (https://github.com/yourname/research-collectors)"
        }
        
        if self.token:
            headers["Authorization"] = f"token {self.token}"
            logger.info("Using authenticated GitHub API (higher rate limit)")
        
        session.headers.update(headers)
        
        return session
    
    def _throttle(self):
        """Rate limiting with precision"""
        if self.last_request_time is None:
            self.last_request_time = time.time()
            return
        
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        
        self.last_request_time = time.time()
    
    def _make_request(self, url: str, params: Dict = None, conditional: bool = False, full_name: str = None) -> Optional[Dict]:
        """Make rate-limited request with conditional GET support"""
        self._throttle()
        
        headers = {}
        
        # Conditional GET for repo details (not search)
        if conditional and full_name and self.cache_enabled:
            etag = self.cache.get_etag(full_name)
            if etag:
                headers["If-None-Match"] = etag
        
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            
            # Handle rate limiting
            if response.status_code == 403:
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                if reset_time:
                    wait_time = reset_time - time.time()
                    if wait_time > 0:
                        logger.warning(f"Rate limit exceeded. Waiting {wait_time:.0f}s")
                        time.sleep(wait_time + 1)
                        return self._make_request(url, params, conditional, full_name)
            
            # Conditional GET hit (not modified)
            if response.status_code == 304:
                logger.debug(f"Cache hit (304): {full_name}")
                cached = self.cache.get(full_name) if self.cache_enabled else None
                if cached:
                    return cached
            
            response.raise_for_status()
            
            # Log rate limit status
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining and int(remaining) < 100:
                logger.warning(f"Low rate limit: {remaining} remaining")
            
            return response.json()
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout for {url}")
            return None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Resource not found: {url}")
            else:
                logger.error(f"HTTP {e.response.status_code}: {url}")
            return None
        except Exception as e:
            logger.error(f"Request failed: {e}", exc_info=True)
            return None
    
    def _calculate_score(self, repo: Dict[str, Any]) -> float:
        """
        Advanced scoring: popularity + recency + engagement
        
        Factors:
        - Stars, forks, watchers (weighted)
        - Recency decay (logarithmic)
        - Issue engagement ratio
        """
        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)
        watchers = repo.get("watchers_count", 0)
        open_issues = repo.get("open_issues_count", 0)
        
        # Engagement score (closed issues ratio would be better but not available in search)
        engagement_bonus = 1.0
        if open_issues > 0:
            # Lower open issues relative to stars = better maintained
            engagement_bonus = 1 + (stars / (open_issues + 1)) * 0.01
        
        try:
            updated = datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00"))
            days_old = max((datetime.now(timezone.utc) - updated).days, 1)
            
            # Logarithmic decay (recent updates matter less after first few days)
            recency_factor = 1 / (days_old ** 0.15)
            
            raw_score = (stars * 2 + forks * 3 + watchers * 1) * recency_factor * engagement_bonus
            return round(raw_score, 2)
            
        except Exception as e:
            logger.debug(f"Score calculation failed: {e}")
            return float(stars + forks * 3 + watchers * 2)
    
    def _fetch_additional_details(self, full_name: str) -> Dict[str, Any]:
        """Fetch detailed repo info (topics, license, etc.)"""
        url = f"{GITHUB_REPO_URL}/{full_name}"
        
        # Check cache first
        if self.cache_enabled:
            cached = self.cache.get(full_name)
            if cached:
                return cached
        
        response = self._make_request(url, conditional=True, full_name=full_name)
        
        if not response:
            return {}
        
        # Cache the result
        if self.cache_enabled and response.get("full_name"):
            etag = self.session.headers.get("ETag", "")
            last_modified = self.session.headers.get("Last-Modified", "")
            self.cache.set(full_name, response, etag, last_modified)
        
        return response
    
    def search(
        self,
        query: str,
        max_results: int = 10,
        sort: SortCriterion = SortCriterion.STARS,
        order: Order = Order.DESC,
        language: Optional[str] = None,
        min_stars: Optional[int] = None,
        min_forks: Optional[int] = None,
        topic: Optional[str] = None,
        fetch_details: bool = True,
        parallel: bool = True,
        max_workers: int = 5
    ) -> List[GitHubRepo]:
        """
        Search GitHub repositories with advanced filtering.
        
        Args:
            query: GitHub search query
            max_results: Maximum number of results (capped at 1000 by GitHub)
            sort: Sort criterion
            order: Sort order
            language: Filter by programming language
            min_stars: Minimum stars filter
            min_forks: Minimum forks filter
            topic: Filter by topic
            fetch_details: Fetch additional details for each repo
            parallel: Fetch details in parallel
            max_workers: Parallel workers count
        
        Returns:
            List of GitHubRepo objects
        """
        # Build advanced query
        search_parts = [query]
        if language:
            search_parts.append(f"language:{language}")
        if min_stars:
            search_parts.append(f"stars:>={min_stars}")
        if min_forks:
            search_parts.append(f"forks:>={min_forks}")
        if topic:
            search_parts.append(f"topic:{topic}")
        
        full_query = " ".join(search_parts)
        
        logger.info(f"Searching GitHub: '{full_query}' (max={max_results})")
        
        results: List[GitHubRepo] = []
        page = 1
        remaining = None
        
        while len(results) < max_results:
            per_page = min(100, max_results - len(results))
            
            params = {
                "q": full_query,
                "sort": sort.value if sort != SortCriterion.BEST_MATCH else "",
                "order": order.value if sort != SortCriterion.BEST_MATCH else "",
                "page": page,
                "per_page": per_page,
            }
            
            # Remove empty params
            params = {k: v for k, v in params.items() if v}
            
            response = self._make_request(GITHUB_SEARCH_URL, params)
            
            if not response:
                break
            
            items = response.get("items", [])
            if not items:
                break
            
            remaining = response.get("total_count", 0)
            
            # Process results
            if fetch_details:
                if parallel and len(items) > 1:
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = {
                            executor.submit(self._fetch_and_parse, item): item 
                            for item in items
                        }
                        for future in as_completed(futures):
                            repo = future.result()
                            if repo:
                                results.append(repo)
                else:
                    for item in items:
                        repo = self._fetch_and_parse(item)
                        if repo:
                            results.append(repo)
            else:
                for item in items:
                    repo = self._parse_basic(item)
                    results.append(repo)
            
            page += 1
            
            # Respect rate limits
            self._throttle()
        
        logger.info(f"Found {len(results)} repositories")
        
        # Log rate limit status
        if remaining:
            logger.info(f"Total results available: {remaining}")
        
        return results[:max_results]
    
    def _fetch_and_parse(self, search_item: Dict) -> Optional[GitHubRepo]:
        """Fetch detailed info and parse into GitHubRepo"""
        full_name = search_item.get("full_name")
        
        # Get detailed info
        details = self._fetch_additional_details(full_name) if full_name else {}
        
        # Merge search result with details
        merged = {**search_item, **details}
        
        return self._parse_basic(search_item, merged)
    
    def _parse_basic(self, search_item: Dict, details: Dict = None) -> Optional[GitHubRepo]:
        """Parse repository data into GitHubRepo object"""
        try:
            owner = search_item.get("owner", {})
            
            # Use details if provided
            topics = details.get("topics", []) if details else search_item.get("topics", [])
            license_name = None
            if details and details.get("license"):
                license_name = details["license"].get("name")
            elif search_item.get("license"):
                license_name = search_item["license"].get("name")
            
            has_discussions = False
            if details:
                has_discussions = details.get("has_discussions", False)
            
            return GitHubRepo(
                full_name=search_item.get("full_name", ""),
                description=search_item.get("description") or "",
                url=search_item.get("html_url", ""),
                author=owner.get("login", ""),
                avatar_url=owner.get("avatar_url"),
                stars=search_item.get("stargazers_count", 0),
                forks=search_item.get("forks_count", 0),
                watchers=search_item.get("watchers_count", 0),
                open_issues=search_item.get("open_issues_count", 0),
                language=search_item.get("language"),
                topics=topics or [],
                homepage=search_item.get("homepage"),
                default_branch=search_item.get("default_branch", "main"),
                size_kb=search_item.get("size", 0),
                archived=search_item.get("archived", False),
                disabled=search_item.get("disabled", False),
                has_issues=search_item.get("has_issues", False),
                has_wiki=search_item.get("has_wiki", False),
                has_discussions=has_discussions,
                license=license_name,
                created_at=search_item.get("created_at", ""),
                updated_at=search_item.get("updated_at", ""),
                pushed_at=search_item.get("pushed_at", ""),
                score=self._calculate_score(search_item),
                query=""  # Will be set by caller
            )
        except Exception as e:
            logger.error(f"Failed to parse repo {search_item.get('full_name')}: {e}")
            return None
    
    def get_repo(self, full_name: str) -> Optional[GitHubRepo]:
        """Fetch single repository by name"""
        response = self._fetch_additional_details(full_name)
        if response:
            repo = self._parse_basic(response, response)
            return repo
        return None
    
    def close(self):
        """Clean up session"""
        self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


# ====================== COMPATIBILITY WRAPPER ======================

def search(
    query: str,
    max_results: int = 10,
    token: Optional[str] = None,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Compatibility wrapper for unified interface.
    """
    with GitHubCollector(token=token) as collector:
        results = collector.search(query, max_results=max_results, **kwargs)
        # Convert to dict format for compatibility
        return [repo.to_dict() for repo in results]


# ====================== ADVANCED USAGE EXAMPLE ======================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="GitHub Repository Collector")
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument("--max", type=int, default=10, help="Max results")
    parser.add_argument("--language", "-l", help="Filter by language")
    parser.add_argument("--min-stars", type=int, help="Minimum stars")
    parser.add_argument("--min-forks", type=int, help="Minimum forks")
    parser.add_argument("--topic", "-t", help="Filter by topic")
    parser.add_argument("--token", help="GitHub token (or set GITHUB_TOKEN env var)")
    parser.add_argument("--no-details", action="store_true", help="Skip detailed fetch")
    parser.add_argument("--parallel", action="store_true", default=True, help="Parallel fetch")
    parser.add_argument("--sort", choices=["stars", "forks", "updated", "best_match"], default="stars")
    
    args = parser.parse_args()
    
    # Build query
    query = " ".join(args.query).strip() or "topic:web-scraping language:python"
    
    # Map sort string to enum
    sort_map = {
        "stars": SortCriterion.STARS,
        "forks": SortCriterion.FORKS,
        "updated": SortCriterion.UPDATED,
        "best_match": SortCriterion.BEST_MATCH
    }
    
    import os
    token = args.token or os.getenv("GITHUB_TOKEN")
    
    with GitHubCollector(token=token, cache_enabled=True) as collector:
        results = collector.search(
            query=query,
            max_results=args.max,
            language=args.language,
            min_stars=args.min_stars,
            min_forks=args.min_forks,
            topic=args.topic,
            sort=sort_map.get(args.sort, SortCriterion.STARS),
            fetch_details=not args.no_details,
            parallel=args.parallel
        )
        
        print(f"\n🔍 GitHub results for: '{query}' ({len(results)} repos)")
        print("=" * 100)
        
        for i, repo in enumerate(results, 1):
            print(f"\n[{i}] {repo.full_name}")
            print(f"⭐ Stars: {repo.stars:,}")
            print(f"🍴 Forks: {repo.forks:,}")
            print(f"👤 Author: {repo.author}")
            if repo.language:
                print(f"💻 Language: {repo.language}")
            print(f"🏆 Score: {repo.score}")
            print(f"📦 Size: {repo.size_kb:,} KB")
            print(f"🔗 {repo.url}")
            
            if repo.topics:
                print(f"🏷️ Topics: {', '.join(repo.topics[:8])}")
            
            if repo.description:
                print(f"📝 {repo.description[:200]}")
            
            if repo.license:
                print(f"📄 License: {repo.license}")
            
            print("-" * 90)
