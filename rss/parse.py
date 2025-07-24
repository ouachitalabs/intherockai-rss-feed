import feedparser
import logging
import os
from dateutil import parser as date_parser
from urllib.parse import urlparse
import time
from typing import Annotated, Optional

from api.models import Article

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants for resilience
REQUEST_TIMEOUT = 30  # seconds
MAX_CONTENT_SIZE = 10 * 1024 * 1024  # 10MB
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

RSS_FEEDS = os.getenv("RSS_FEEDS", "").split(',')

def _validate_url(url: str) -> bool:
    """Validate URL format and scheme"""
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc and parsed.scheme in ['http', 'https'])
    except Exception:
        return False

def _safe_getattr(obj, attr: str, default: str = '') -> str:
    """Safely get attribute with type validation"""
    try:
        value = getattr(obj, attr, default)
        if value is None:
            return default
        return str(value).strip() if isinstance(value, (str, int, float)) else default
    except Exception:
        return default

def _parse_date_safely(date_str: str) -> Optional[str]:
    """Parse date string with multiple fallback formats"""
    if not date_str or not isinstance(date_str, str):
        return None
    
    # Try parsing with dateutil which handles most formats automatically
    try:
        return date_parser.parse(date_str).isoformat()
    except (ValueError, TypeError):
        pass
    
    logger.warning(f"Could not parse date: {date_str}")
    return None

def parse_feed_manually(url: Annotated[str, "URL"]) -> list[Article]:
    """
    Takes an RSS feed URL and parses into a list of Article objects
    Implements defensive programming against various edge cases
    """
    if not url or not isinstance(url, str):
        logger.error("Invalid URL provided")
        return []
    
    if not _validate_url(url):
        logger.error(f"Invalid URL format: {url}")
        return []
    
    logger.info(f"Parsing feed: {url}")
    
    # Parse feed with retries and error handling
    feed = None
    for attempt in range(MAX_RETRIES):
        try:
            # Set timeout and other safety parameters
            feedparser.USER_AGENT = "RSS Parser 1.0 (defensive)"
            feed = feedparser.parse(url, request_headers={
                'User-Agent': 'RSS Parser 1.0 (defensive)'
            })
            
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"Feed parsing warning on attempt {attempt + 1}: {feed.bozo_exception}")
            
            break
            
        except Exception as e:
            logger.error(f"Feed parsing failed on attempt {attempt + 1}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"Failed to parse feed after {MAX_RETRIES} attempts")
                return []
    
    if not feed or not hasattr(feed, 'entries'):
        logger.error("No valid feed data received")
        return []
    
    entries = feed.entries if feed.entries else []
    if not entries:
        logger.warning("No entries found in feed")
        return []
    
    articles = []
    for i, entry in enumerate(entries[:50]):  # Limit to 50 entries max
        try:
            if not entry:
                logger.warning(f"Empty entry at index {i}")
                continue
            
            # Extract and validate title
            title = _safe_getattr(entry, 'title', 'Untitled')
            if not title or len(title.strip()) == 0:
                title = 'Untitled'
            
            # Extract and validate link
            link = _safe_getattr(entry, 'link', '')
            if not link or not _validate_url(link):
                logger.warning(f"Invalid or missing link for entry {i}: {link}")
                continue  # Skip entries without valid links
            
            # Parse dates safely
            published_str = _safe_getattr(entry, 'published', '')
            published = _parse_date_safely(published_str) if published_str else None
            
            updated_str = _safe_getattr(entry, 'updated', '')
            updated = _parse_date_safely(updated_str) if updated_str else None
            
            # Extract summary/content with size limits
            summary = _safe_getattr(entry, 'summary', '')
            if not summary and hasattr(entry, 'content') and entry.content:
                try:
                    content_list = entry.content if isinstance(entry.content, list) else []
                    if content_list and isinstance(content_list[0], dict):
                        summary = str(content_list[0].get('value', '')).strip()
                except (IndexError, AttributeError, TypeError):
                    summary = ''
            
            # Limit summary size
            if summary and len(summary) > 5000:  # 5KB limit
                summary = summary[:5000] + '...'
                logger.warning(f"Truncated large summary for entry {i}")
            
            # Create article with validation
            try:
                article = Article(
                    title=title[:500],  # Limit title length
                    summary=summary,
                    link=link,
                    published=published,
                    updated=updated,
                    tags=[]  # Will be populated by AI processing
                )
                articles.append(article)
                
            except Exception as e:
                logger.error(f"Failed to create Article object for entry {i}: {e}")
                continue
                
        except Exception as e:
            logger.error(f"Error processing entry {i}: {e}")
            continue

    return articles
