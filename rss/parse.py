import feedparser
import os
import sqlite3
from dateutil import parser as date_parser
from typing import Annotated

from api.models import Article, ArticleCollection

RSS_FEEDS = os.getenv("RSS_FEEDS", "").split(',')

def link_exists_in_db(link: str, db_path: str = "articles.db") -> bool:
    """Check if a link already exists in the database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM articles WHERE link = ?", (link,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except:
        return False

def fetch_new_articles(url: Annotated[str, "URL"]) -> ArticleCollection:
    """Fetches new articles from RSS feed URL that don't already exist in database"""
    if not url:
        return ArticleCollection(articles=[])
    
    feed = feedparser.parse(url)
    if not feed or not feed.entries:
        return ArticleCollection(articles=[])
    
    articles = []
    for entry in feed.entries:
        try:
            title = getattr(entry, 'title', 'Untitled')
            link = getattr(entry, 'link', '')
            summary = getattr(entry, 'summary', '')
            
            # Skip entries without a link or if link already exists in database
            if not link or link_exists_in_db(link):
                continue
            
            # Try to get content if no summary
            if not summary and hasattr(entry, 'content') and entry.content:
                try:
                    summary = entry.content[0].get('value', '')
                except:
                    pass
            
            # Parse dates
            published = None
            if hasattr(entry, 'published'):
                try:
                    published = date_parser.parse(entry.published).isoformat()
                except:
                    pass
            
            updated = None
            if hasattr(entry, 'updated'):
                try:
                    updated = date_parser.parse(entry.updated).isoformat()
                except:
                    pass
            
            article = Article(
                title=title,
                summary=summary,
                link=link,
                published=published,
                updated=updated,
                tags=[]
            )
            articles.append(article)
            
        except:
            # Skip problematic entries
            continue

    return ArticleCollection(articles=articles)
