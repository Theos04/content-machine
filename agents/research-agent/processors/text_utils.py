import re
from typing import List
from collections import Counter
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize

# Download NLTK data if needed (will be handled by main script)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

def extract_keywords(text: str, num_keywords: int = 10) -> List[str]:
    """
    Extract keywords from text
    
    Args:
        text: Input text
        num_keywords: Number of keywords to extract
    
    Returns:
        List of keywords
    """
    if not text:
        return []
    
    # Simple keyword extraction
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'will',
        'would', 'could', 'should', 'may', 'might', 'must', 'this', 'that',
        'these', 'those', 'it', 'they', 'we', 'you', 'he', 'she', 'it', 'them',
        'from', 'as', 'about', 'into', 'through', 'during', 'before', 'after',
        'above', 'below', 'between', 'under', 'over', 'again', 'further',
        'then', 'once', 'here', 'there', 'all', 'any', 'both', 'each', 'few',
        'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
        'own', 'same', 'so', 'than', 'too', 'very', 'just', 'but', 'can',
        'get', 'use', 'used', 'using', 'like', 'just', 'make', 'made',
        'making', 'see', 'seen', 'seeing', 'know', 'known', 'knowing',
        'think', 'thought', 'thinking', 'want', 'wanted', 'wanting'
    }
    
    # Convert to lowercase and extract words
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    
    # Filter stop words and short words
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    
    # Count frequencies
    keyword_counts = Counter(keywords)
    
    # Return top keywords
    return [word for word, count in keyword_counts.most_common(num_keywords)]

def extractive_summary(text: str, num_sentences: int = 5) -> str:
    """
    Generate a simple extractive summary
    
    Args:
        text: Input text
        num_sentences: Number of sentences in summary
    
    Returns:
        Summarized text
    """
    if not text:
        return ""
    
    # Try NLTK sentence tokenization, fall back to simple splitting
    try:
        sentences = sent_tokenize(text)
    except:
        # Simple sentence splitting as fallback
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return text[:500]
    
    # Score sentences by length and position
    def score_sentence(sentence, index):
        words = sentence.split()
        length_score = min(len(words) / 20, 1.0)  # Prefer sentences with 15-25 words
        position_score = 1.0 - (index / len(sentences))  # Prefer earlier sentences
        return length_score * 0.4 + position_score * 0.6
    
    # Score all sentences
    scored_sentences = [(sentence, score_sentence(sentence, i)) 
                        for i, sentence in enumerate(sentences)]
    
    # Sort by score and select top sentences
    scored_sentences.sort(key=lambda x: x[1], reverse=True)
    selected = [s for s, score in scored_sentences[:num_sentences]]
    
    # Sort selected sentences by original order
    selected.sort(key=lambda x: sentences.index(x))
    
    # Join sentences
    summary = ' '.join(selected)
    
    # Ensure summary ends with proper punctuation
    if summary and summary[-1] not in '.!?':
        summary += '.'
    
    return summary

def extract_entities(text: str) -> List[str]:
    """
    Simple entity extraction (proper nouns, capitalized words)
    
    Args:
        text: Input text
    
    Returns:
        List of potential entities
    """
    if not text:
        return []
    
    # Extract capitalized words (potential proper nouns)
    entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    
    # Filter out common words that aren't entities
    common_caps = {'The', 'And', 'Or', 'But', 'For', 'With', 'From', 'This', 
                   'That', 'These', 'Those', 'There', 'Their', 'They', 'What',
                   'Which', 'When', 'Where', 'Who', 'Whom', 'How', 'Why'}
    
    entities = [e for e in entities if e not in common_caps and len(e) > 2]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_entities = []
    for e in entities:
        if e not in seen:
            seen.add(e)
            unique_entities.append(e)
    
    return unique_entities[:10]

if __name__ == "__main__":
    # Test the functions
    test_text = """
    Python is a powerful programming language. It is widely used in data science,
    web development, and artificial intelligence. Many companies like Google,
    Facebook, and Netflix use Python for their backend systems.
    """
    
    print("Keywords:", extract_keywords(test_text, num_keywords=5))
    print("Summary:", extractive_summary(test_text, num_sentences=2))
    print("Entities:", extract_entities(test_text))
