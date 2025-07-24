import feedparser
import logging
import os
import sqlite3
from dateutil import parser as date_parser
from typing import Annotated

from api.models import Article, ArticleCollection

logger = logging.getLogger(__name__)

RSS_FEEDS = os.getenv("RSS_FEEDS", "").split(',')

def link_exists_in_db(link: str, db_path: str = "articles.db") -> bool:
    """Check if a link already exists in the database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM articles WHERE link = ?", (link,))
        result = cursor.fetchone()
        conn.close()
        exists = result is not None
        if exists:
            logger.debug(f"Link already exists in database: {link}")
        return exists
    except sqlite3.Error as e:
        logger.error(f"Database error checking if link exists: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking if link exists: {e}")
        return False

def fetch_new_articles(url: Annotated[str, "URL"]) -> ArticleCollection:
    """Fetches new articles from RSS feed URL that don't already exist in database"""
    if not url:
        logger.warning("Empty URL provided to fetch_new_articles")
        return ArticleCollection(articles=[])
    
    logger.info(f"Fetching RSS feed from: {url}")
    
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        logger.error(f"Failed to parse RSS feed from {url}: {e}")
        return ArticleCollection(articles=[])
    
    if not feed:
        logger.error(f"No feed data received from {url}")
        return ArticleCollection(articles=[])
    
    if not feed.entries:
        logger.warning(f"No entries found in RSS feed from {url}")
        return ArticleCollection(articles=[])
    
    logger.info(f"Found {len(feed.entries)} entries in RSS feed")
    
    articles = []
    skipped_count = 0
    
    for i, entry in enumerate(feed.entries):
        try:
            title = getattr(entry, 'title', 'Untitled')
            link = getattr(entry, 'link', '')
            summary = getattr(entry, 'summary', '')
            
            # Skip entries without a link
            if not link:
                logger.debug(f"Skipping entry {i} - no link provided")
                skipped_count += 1
                continue
            
            # Skip if link already exists in database
            if link_exists_in_db(link):
                skipped_count += 1
                continue
            
            logger.debug(f"Processing new article: {title[:50]}...")
            
            # Try to get content if no summary
            if not summary and hasattr(entry, 'content') and entry.content:
                try:
                    summary = entry.content[0].get('value', '')
                    logger.debug("Used content field for summary")
                except Exception as e:
                    logger.debug(f"Failed to extract content field: {e}")
            
            # Parse dates
            published = None
            if hasattr(entry, 'published'):
                try:
                    published = date_parser.parse(entry.published).isoformat()
                except Exception as e:
                    logger.debug(f"Failed to parse published date '{entry.published}': {e}")
            
            updated = None
            if hasattr(entry, 'updated'):
                try:
                    updated = date_parser.parse(entry.updated).isoformat()
                except Exception as e:
                    logger.debug(f"Failed to parse updated date '{entry.updated}': {e}")
            
            article = Article(
                title=title,
                summary=summary,
                link=link,
                published=published,
                updated=updated,
                tags=[]
            )
            articles.append(article)
            
        except Exception as e:
            logger.warning(f"Error processing entry {i}: {e}")
            skipped_count += 1
            continue

    logger.info(f"Successfully processed {len(articles)} new articles, skipped {skipped_count} entries")
    return ArticleCollection(articles=articles)
