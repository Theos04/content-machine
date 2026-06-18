#!/usr/bin/env python3
"""
YouTube Collector - Pure yt-dlp (Fast & Reliable)
No APIs, just fast extraction
"""

from typing import List, Dict, Any, Optional
import yt_dlp
import logging
from datetime import datetime
import time
import json
from pathlib import Path
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class YouTubeCollector:
    """Fast YouTube collector using yt-dlp with optimized settings"""
    
    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self.last_request = 0
        
        # Optimized yt-dlp options for SPEED
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',  # KEY: Don't fetch full metadata
            'ignoreerrors': True,
            'noplaylist': True,
            'skip_download': True,
            'format': 'best',  # Doesn't matter since we skip download
            'geo_bypass': True,
            'socket_timeout': 10,  # 10 second timeout
            'retries': 2,
            'fragment_retries': 0,
        }
        
        self.ydl = yt_dlp.YoutubeDL(self.ydl_opts)
    
    def _throttle(self):
        """Rate limiting"""
        elapsed = time.time() - self.last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request = time.time()
    
    def search(self, query: str, max_results: int = 5, fetch_transcripts: bool = False) -> List[Dict]:
        """
        Fast search using yt-dlp's flat extraction
        
        Returns results in < 2 seconds typically
        """
        
        results = []
        search_query = f"ytsearch{max_results}:{query}"
        
        try:
            self._throttle()
            logger.info(f"Searching: '{query}' (max={max_results})")
            
            # FLAT extraction - only basic info, super fast
            info = self.ydl.extract_info(search_query, download=False, process=False)
            
            if not info or 'entries' not in info:
                logger.warning("No results found")
                return []
            
            # Process each video
            for entry in info['entries']:
                if not entry:
                    continue
                
                video_id = entry.get('id')
                if not video_id:
                    continue
                
                # Parse duration
                duration = entry.get('duration', 0)
                if duration:
                    hours = duration // 3600
                    minutes = (duration % 3600) // 60
                    seconds = duration % 60
                    if hours > 0:
                        dur_str = f"{hours}h {minutes}m {seconds}s"
                    elif minutes > 0:
                        dur_str = f"{minutes}m {seconds}s"
                    else:
                        dur_str = f"{seconds}s"
                else:
                    dur_str = ""
                
                # Parse date
                upload_date = entry.get('upload_date', '')
                if upload_date and len(upload_date) == 8:
                    published = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
                else:
                    published = ""
                
                # Build result from flat data (already available, no extra requests!)
                result = {
                    'collector': 'youtube',
                    'video_id': video_id,
                    'title': entry.get('title', 'Untitled'),
                    'content': entry.get('description', '')[:500],  # Limit description
                    'url': f"https://youtube.com/watch?v={video_id}",
                    'source': entry.get('channel', '') or entry.get('uploader', 'Unknown'),
                    'published': published,
                    'views': entry.get('view_count', 0),
                    'duration_seconds': duration,
                    'duration_str': dur_str,
                    'thumbnail': entry.get('thumbnail', ''),
                    'has_transcript': False,
                    'transcript': ''
                }
                
                results.append(result)
                
                if len(results) >= max_results:
                    break
            
            logger.info(f"Found {len(results)} videos in {time.time() - self.last_request:.1f}s")
            return results
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def get_transcript(self, video_id: str) -> str:
        """Get transcript for a single video (slower, call separately)"""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            return " ".join(chunk["text"] for chunk in transcript)
        except Exception as e:
            logger.debug(f"No transcript for {video_id}: {e}")
            return ""
    
    def close(self):
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


# ====================== FAST BATCH SEARCH ======================

def search_batch(queries: List[str], max_per_query: int = 3) -> Dict[str, List[Dict]]:
    """Search multiple queries quickly"""
    results = {}
    
    with YouTubeCollector() as collector:
        for query in queries:
            results[query] = collector.search(query, max_results=max_per_query)
    
    return results


# ====================== CLI ======================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="YouTube Collector - Fast yt-dlp")
    parser.add_argument("query", nargs="*", help="Search query")
    parser.add_argument("--max", "-m", type=int, default=5, help="Max results")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--transcript", action="store_true", help="Fetch transcripts (slower)")
    
    args = parser.parse_args()
    
    query = " ".join(args.query).strip() or "python tutorial"
    
    with YouTubeCollector() as collector:
        # Quick search
        results = collector.search(query, max_results=args.max)
        
        # Fetch transcripts if requested (separate step)
        if args.transcript and results:
            print("\n📝 Fetching transcripts (this may take a moment)...")
            for video in results:
                transcript = collector.get_transcript(video['video_id'])
                if transcript:
                    video['transcript'] = transcript
                    video['has_transcript'] = True
                    video['content'] = transcript  # Use transcript as content
                    print(f"   ✓ Got transcript for: {video['title'][:50]}...")
                time.sleep(0.3)  # Small delay between transcript fetches
        
        # Output
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\n🎥 Results for: '{query}' ({len(results)} videos)")
            print("=" * 90)
            
            for i, video in enumerate(results, 1):
                print(f"\n[{i}] {video['title']}")
                print(f"   📺 {video['source']}")
                print(f"   👁️ {video['views']:,} views")
                print(f"   ⏱️ {video['duration_str']}")
                print(f"   📅 {video['published']}")
                print(f"   🔗 {video['url']}")
                
                if video.get('has_transcript'):
                    print(f"   📝 Transcript: {len(video['transcript']):,} chars")
                    print(f"      Preview: {video['transcript'][:150]}...")
                else:
                    desc = video['content'][:150] if video['content'] else "No description"
                    print(f"   📝 {desc}...")
                
                print("-" * 90)
