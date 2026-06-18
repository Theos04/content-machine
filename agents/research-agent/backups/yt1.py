import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

def get_transcript(video_id: str) -> str:
    """Fetch full transcript for a YouTube video."""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(chunk["text"] for chunk in transcript)
    except Exception:
        # Fallback if no transcript (e.g., disabled, age-restricted, etc.)
        return ""


def search(query: str, max_results: int = 10):
    """
    Search YouTube and return videos in the same format
    used by the other collectors. Includes full metadata
    and video transcripts for richer content.
    """
    results = []
    try:
        # Enhanced options for richer metadata
        ydl_opts = {
            "quiet": True,
            "extract_flat": False,   # Get full entry details
            "skip_download": True,
            "ignoreerrors": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            data = ydl.extract_info(
                f"ytsearch{max_results}:{query}",
                download=False
            )
            for entry in data.get("entries", []):
                if not entry:
                    continue

                video_id = entry.get("id")
                if not video_id:
                    continue

                # Prioritize full transcript over description
                content = get_transcript(video_id)
                if not content.strip():
                    content = entry.get("description", "")

                results.append({
                    "collector": "youtube",
                    "title": entry.get("title", ""),
                    "content": content,
                    "url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                    "source": entry.get("channel", "") or entry.get("uploader", ""),
                    "published": entry.get("upload_date", "") or "",
                    "video_id": video_id,
                    "views": entry.get("view_count", 0),
                    "duration": entry.get("duration", 0),
                    "thumbnail": entry.get("thumbnail", ""),
                })
    except Exception as e:
        print(f"YouTube collector error: {e}")
    return results
