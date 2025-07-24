import sys
import os
import time
import logging
from typing import Optional
from urllib.parse import urlparse

import openai
import feedparser
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.models import ArticleCollection

logger = logging.getLogger(__name__)

# Constants for resilience
REQUEST_TIMEOUT = 30
MAX_CONTENT_SIZE = 10 * 1024 * 1024  # 10MB
MAX_RETRIES = 3
RETRY_DELAY = 1
MAX_ARTICLES_TO_PROCESS = 10

# Initialize OpenAI client with error handling
try:
    client = openai.Client()
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    client = None

def _validate_url(url: str) -> bool:
    """Validate URL format and scheme"""
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc and parsed.scheme in ['http', 'https'])
    except Exception:
        return False

def _safe_get(obj, attr: str, default='') -> str:
    """Safely get attribute with validation"""
    try:
        value = getattr(obj, attr, default)
        if value is None:
            return default
        return str(value).strip() if value else default
    except Exception:
        return default

def clean_rss(url: str) -> list[dict]:
    """Clean RSS feed with defensive programming"""
    if not url or not isinstance(url, str):
        logger.error("Invalid URL provided to clean_rss")
        return []
    
    if not _validate_url(url):
        logger.error(f"Invalid URL format: {url}")
        return []
    
    try:
        logger.info(f"Cleaning RSS feed: {url}")
        
        # Parse with timeout and retries
        rss = None
        for attempt in range(MAX_RETRIES):
            try:
                rss = feedparser.parse(url)
                if rss.bozo and rss.bozo_exception:
                    logger.warning(f"Feed parsing warning: {rss.bozo_exception}")
                break
            except Exception as e:
                logger.error(f"Feed parsing attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
        
        if not rss:
            logger.error("Failed to parse RSS feed after all retries")
            return []
        
        # Safely extract feed info
        feed = rss.feed if hasattr(rss, 'feed') else {}
        entries = rss.entries if hasattr(rss, 'entries') and rss.entries else []
        
        if not entries:
            logger.warning("No entries found in RSS feed")
            return []
        
        # Process entries with error handling
        output = []
        for i, entry in enumerate(entries[:MAX_ARTICLES_TO_PROCESS]):
            try:
                if not entry:
                    continue
                
                # Validate required fields
                title = _safe_get(entry, 'title', f'Article {i+1}')
                link = _safe_get(entry, 'link', '')
                
                if not link or not _validate_url(link):
                    logger.warning(f"Skipping entry {i} with invalid link: {link}")
                    continue
                
                # Build entry dict safely
                entry_dict = {
                    'feed': {
                        'title': _safe_get(feed, 'title', 'Unknown Feed'),
                        'subtitle': _safe_get(feed, 'subtitle', ''),
                        'link': _safe_get(feed, 'link', ''),
                    },
                    'title': title[:500],  # Limit title length
                    'link': link,
                    'summary': _safe_get(entry, 'summary', '')[:2000],  # Limit summary
                    'published': _safe_get(entry, 'published', ''),
                    'updated': _safe_get(entry, 'updated', ''),
                }
                
                output.append(entry_dict)
                
            except Exception as e:
                logger.error(f"Error processing entry {i}: {e}")
                continue
        
        logger.info(f"Successfully cleaned {len(output)} articles from RSS feed")
        return output
        
    except Exception as e:
        logger.error(f"Unexpected error in clean_rss: {e}")
        return []


def route_to_openai(rss: list[dict]) -> Optional[ArticleCollection]:
    """Route RSS data to OpenAI with defensive error handling"""
    if not client:
        logger.error("OpenAI client not initialized")
        return None
    
    if not rss or not isinstance(rss, list):
        logger.error("Invalid RSS data provided to route_to_openai")
        return None
    
    if len(rss) == 0:
        logger.warning("Empty RSS data provided")
        return ArticleCollection(articles=[])
    
    try:
        # Validate and sanitize input data
        sanitized_rss = []
        for i, item in enumerate(rss[:MAX_ARTICLES_TO_PROCESS]):
            if not isinstance(item, dict):
                logger.warning(f"Skipping non-dict item at index {i}")
                continue
            
            # Ensure required fields exist
            if 'title' not in item or 'link' not in item:
                logger.warning(f"Skipping item {i} missing required fields")
                continue
            
            sanitized_rss.append(item)
        
        if not sanitized_rss:
            logger.warning("No valid articles to process")
            return ArticleCollection(articles=[])
        
        # Prepare OpenAI request with size limits
        rss_json = json.dumps(sanitized_rss, indent=2)
        if len(rss_json) > 50000:  # 50KB limit
            logger.warning("RSS data too large, truncating")
            rss_json = rss_json[:50000] + "...}"
        
        logger.info(f"Sending {len(sanitized_rss)} articles to OpenAI for tagging")
        
        # Make OpenAI request with retries
        for attempt in range(MAX_RETRIES):
            try:
                response = client.responses.parse(
                    model="gpt-4o-2024-08-06",
                    input=[
                        {
                            "role": "system",
                            "content": "Tag each article with relevant categories and clean up the important information. Return valid JSON only."
                        },
                        {
                            "role": "user",
                            "content": rss_json
                        }
                    ],
                    text_format=ArticleCollection
                )
                
                if not response or not hasattr(response, 'output_parsed'):
                    logger.error(f"Invalid response from OpenAI on attempt {attempt + 1}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    return None
                
                articles = response.output_parsed
                
                # Validate parsed response
                if not isinstance(articles, ArticleCollection):
                    logger.error("OpenAI returned invalid ArticleCollection format")
                    return None
                
                if not articles.articles:
                    logger.warning("OpenAI returned empty articles list")
                    return ArticleCollection(articles=[])
                
                logger.info(f"Successfully processed {len(articles.articles)} articles with OpenAI")
                return articles
                
            except openai.RateLimitError as e:
                logger.warning(f"OpenAI rate limit hit on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                    continue
                raise
                
            except openai.APIError as e:
                logger.error(f"OpenAI API error on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                raise
                
            except Exception as e:
                logger.error(f"Unexpected error calling OpenAI on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                break
        
        logger.error(f"Failed to get valid response from OpenAI after {MAX_RETRIES} attempts")
        return None
        
    except Exception as e:
        logger.error(f"Unexpected error in route_to_openai: {e}")
        return None
