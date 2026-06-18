from database.db import ResearchDB
from collections import Counter
import re
from typing import List, Set, Dict
from datetime import datetime

# Common stopwords to filter out
STOPWORDS = {
    'href', 'https', 'http', 'target', 'bash', 'shell', 'nbsp', 'user',
    'that', 'line', 'class', 'default', 'configuration', 'command',
    'google', 'articles', 'news', 'reddit', 'wikipedia', 'arxiv',
    'web', 'page', 'site', 'blog', 'post', 'comment', 'thread',
    'the', 'be', 'to', 'of', 'and', 'a', 'in', 'for', 'on',
    'with', 'as', 'by', 'at', 'from', 'into', 'through',
    'during', 'including', 'according', 'would', 'could',
    'should', 'might', 'must', 'shall', 'will', 'can', 'may'
}

# Domain-specific stopwords
DOMAIN_STOPWORDS = {
    'bjp', 'modi', 'india', 'party', 'political', 'election',
    'government', 'minister', 'prime', 'minister', 'narendra'
}

class GraphStatistics:
    def __init__(self, db: ResearchDB):
        self.db = db
        self.sources = []
        self.keywords = []
        self.keyword_freq = Counter()
        self.source_keywords = {}
        
    def extract_keywords(self, text: str, max_keywords: int = 15) -> List[str]:
        """Extract meaningful keywords from text using multiple patterns"""
        if not text:
            return []
            
        # Clean text
        text = re.sub(r'<[^>]+>', ' ', text)  # Remove HTML tags
        text = re.sub(r'https?://\S+', '', text)  # Remove URLs
        text = re.sub(r'[^\w\s]', ' ', text)  # Remove punctuation
        
        # Extract multi-word phrases (2-3 words)
        phrases = []
        words = text.lower().split()
        
        # Extract noun phrases (simplified)
        for i in range(len(words) - 1):
            if words[i] not in STOPWORDS and words[i+1] not in STOPWORDS:
                phrases.append(f"{words[i]} {words[i+1]}")
                
        for i in range(len(words) - 2):
            if all(w not in STOPWORDS for w in words[i:i+3]):
                phrases.append(f"{words[i]} {words[i+1]} {words[i+2]}")
        
        # Extract single words (filtered)
        single_words = [w for w in words if len(w) > 3 and w not in STOPWORDS]
        
        # Combine and prioritize
        all_keywords = phrases + single_words
        
        # Count frequencies within this text
        temp_counter = Counter(all_keywords)
        
        # Return top keywords
        return [kw for kw, _ in temp_counter.most_common(max_keywords)]
    
    def analyze_sources(self, query: str = None):
        """Analyze all sources and extract statistics"""
        self.sources = self.db.get_sources(query=query) if query else self.db.get_sources()
        
        all_keywords = []
        self.source_keywords = {}
        
        for source in self.sources:
            keywords = self.extract_keywords(source.get('content', ''))
            self.source_keywords[source['id']] = keywords
            all_keywords.extend(keywords)
            
        self.keywords = all_keywords
        self.keyword_freq = Counter(all_keywords)
        
    def get_temporal_analysis(self) -> Dict:
        """Analyze sources by time periods"""
        now = datetime.now()
        time_periods = {
            'today': 0,
            'this_week': 0,
            'this_month': 0,
            'older': 0
        }
        
        for source in self.sources:
            created = source.get('created_at')
            if created:
                try:
                    if isinstance(created, str):
                        created = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    days_ago = (now - created).days
                    
                    if days_ago == 0:
                        time_periods['today'] += 1
                    elif days_ago <= 7:
                        time_periods['this_week'] += 1
                    elif days_ago <= 30:
                        time_periods['this_month'] += 1
                    else:
                        time_periods['older'] += 1
                except:
                    pass
                    
        return time_periods
    
    def display_stats(self, query: str = None):
        """Display comprehensive graph statistics"""
        print(f"\n{'='*70}")
        print(f"📊 KNOWLEDGE GRAPH STATISTICS")
        print(f"{'='*70}")
        
        if query:
            print(f"🔍 Filter: '{query}'")
            print(f"{'='*70}")
        
        # Basic stats
        print(f"\n📈 OVERVIEW:")
        print(f"{'-'*40}")
        print(f"Total Sources: {len(self.sources)}")
        print(f"Total Unique Keywords: {len(set(self.keywords))}")
        print(f"Total Keyword Mentions: {len(self.keywords)}")
        print(f"Avg Keywords/Source: {len(self.keywords)/len(self.sources):.1f}")
        
        # Source type distribution
        print(f"\n📂 SOURCE TYPES:")
        print(f"{'-'*40}")
        collector_stats = Counter([s.get('collector', 'unknown') for s in self.sources])
        for collector, count in collector_stats.most_common():
            percentage = (count / len(self.sources)) * 100
            bar = '█' * int(percentage / 2)
            print(f"  {collector:12}: {count:3} ({percentage:5.1f}%) {bar}")
        
        # Temporal analysis
        time_stats = self.get_temporal_analysis()
        print(f"\n⏰ TEMPORAL DISTRIBUTION:")
        print(f"{'-'*40}")
        for period, count in time_stats.items():
            if count > 0:
                percentage = (count / len(self.sources)) * 100
                bar = '█' * int(percentage / 2)
                print(f"  {period:12}: {count:3} ({percentage:5.1f}%) {bar}")
        
        # Top keywords with better formatting
        print(f"\n🏷️ TOP KEYWORDS (meaningful):")
        print(f"{'-'*40}")
        
        # Filter out domain-specific and generic keywords
        meaningful_keywords = [
            (kw, count) for kw, count in self.keyword_freq.most_common(30)
            if kw not in DOMAIN_STOPWORDS and len(kw.split()) <= 3
        ]
        
        for i, (keyword, count) in enumerate(meaningful_keywords[:20], 1):
            bar_length = min(count * 2, 30)
            bar = '█' * bar_length
            # Show if it's a phrase or single word
            kw_type = "📝" if ' ' in keyword else "🔤"
            print(f"{i:2}. {kw_type} {keyword:25} ({count:2}) {bar}")
        
        # Keyword co-occurrence analysis
        print(f"\n🔗 KEYWORD CO-OCCURRENCE:")
        print(f"{'-'*40}")
        
        # Find top 3 keywords that often appear together
        keyword_pairs = Counter()
        for keywords in self.source_keywords.values():
            for i in range(len(keywords)):
                for j in range(i+1, min(i+3, len(keywords))):
                    pair = tuple(sorted([keywords[i], keywords[j]]))
                    if keywords[i] not in STOPWORDS and keywords[j] not in STOPWORDS:
                        keyword_pairs[pair] += 1
        
        top_pairs = keyword_pairs.most_common(10)
        if top_pairs:
            print("  Most common keyword pairs:")
            for (kw1, kw2), count in top_pairs[:5]:
                print(f"    • {kw1} ↔ {kw2} (appears together in {count} sources)")
        
        # Content quality metrics
        print(f"\n📊 CONTENT METRICS:")
        print(f"{'-'*40}")
        
        content_lengths = [len(s.get('content', '')) for s in self.sources]
        if content_lengths:
            avg_length = sum(content_lengths) / len(content_lengths)
            max_length = max(content_lengths)
            min_length = min(content_lengths)
            print(f"  Avg content length: {avg_length:.0f} characters")
            print(f"  Min content length: {min_length} characters")
            print(f"  Max content length: {max_length} characters")
        
        # Concept clusters (improved)
        print(f"\n🧠 CONCEPT CLUSTERS:")
        print(f"{'-'*40}")
        
        # Academic cluster
        academic_terms = ['research', 'study', 'analysis', 'data', 'model', 
                         'algorithm', 'method', 'approach', 'framework', 'system']
        academic_keywords = [kw for kw, _ in meaningful_keywords 
                           if any(term in kw.lower() for term in academic_terms)]
        if academic_keywords:
            print(f"  Academic: {', '.join(academic_keywords[:6])}")
        
        # Technology cluster
        tech_terms = ['software', 'code', 'program', 'algorithm', 'data', 'api',
                     'database', 'server', 'network', 'security']
        tech_keywords = [kw for kw, _ in meaningful_keywords 
                        if any(term in kw.lower() for term in tech_terms)]
        if tech_keywords:
            print(f"  Technology: {', '.join(tech_keywords[:6])}")
        
        # Political cluster (if relevant)
        political_terms = ['policy', 'government', 'election', 'vote', 'democracy',
                          'reform', 'development', 'welfare', 'scheme']
        political_keywords = [kw for kw, _ in meaningful_keywords 
                            if any(term in kw.lower() for term in political_terms)]
        if political_keywords:
            print(f"  Political: {', '.join(political_keywords[:6])}")
        
        # Health cluster
        health_terms = ['health', 'medical', 'disease', 'treatment', 'vaccine',
                       'healthcare', 'patient', 'doctor', 'hospital']
        health_keywords = [kw for kw, _ in meaningful_keywords 
                         if any(term in kw.lower() for term in health_terms)]
        if health_keywords:
            print(f"  Health: {', '.join(health_keywords[:6])}")
        
        # Summary
        print(f"\n{'='*70}")
        print(f"✅ ANALYSIS COMPLETE")
        print(f"{'='*70}")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        print(f"{'-'*40}")
        
        # Identify gaps
        if len(collector_stats) < 3:
            print("  • Consider adding more diverse source types")
        
        if len(set(self.keywords)) < 100:
            print("  • Consider broadening your search queries")
        
        if sum(1 for s in self.sources if len(s.get('content', '')) < 100) > len(self.sources) * 0.2:
            print("  • Some sources have short content - consider improving data quality")
        
        # Popular concepts not in top keywords
        print("  • Try exploring: " + ", ".join([kw for kw, _ in self.keyword_freq.most_common(5) if kw not in [k for k, _ in meaningful_keywords[:10]]]))
        
        print("\n")

def show_graph_stats(query: str = None):
    """Main function to display graph statistics"""
    db = ResearchDB()
    stats = GraphStatistics(db)
    stats.analyze_sources(query)
    stats.display_stats(query)

if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    show_graph_stats(query)
