import sqlite3
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
import os

# Configure logging with both console and file handlers
def setup_logging():
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with 24-hour rotation
    file_handler = TimedRotatingFileHandler(
        filename='logs/rss_processing.log',
        when='midnight',
        interval=1,
        backupCount=1,  # Keep only 1 backup (24h)
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

# Set up logging
setup_logging()
logger = logging.getLogger(__name__)

# Configure SQLite to handle datetime strings
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("TIMESTAMP", lambda s: datetime.fromisoformat(s.decode()))

from rss.ai import route_to_openai
from rss.parse import fetch_new_articles

urls = [
    "https://arktimes.com/feed",
    "https://www.arkansasbusiness.com/feed/",
    "https://talkbusiness.net/feed/",
    "https://arkansasadvocate.com/feed/",
    "https://www.kark.com/feed/",
]

logger.info(f"Starting RSS processing for {len(urls)} URLs")

# Collect articles from all URLs
all_articles = []
for url in urls:
    logger.info(f"Processing URL: {url}")
    new_articles = fetch_new_articles(url)
    if new_articles.articles:
        all_articles.extend(new_articles.articles)
        logger.info(f"Found {len(new_articles.articles)} new articles from {url}")
    else:
        logger.warning(f"No new articles found from {url}")

if not all_articles:
    logger.warning("No new articles found from any URL, exiting")
    exit(1)

logger.info(f"Found {len(all_articles)} total new articles from all sources")

# Create combined ArticleCollection for processing
from api.models import ArticleCollection
combined_articles = ArticleCollection(articles=all_articles)

tagged = route_to_openai(combined_articles)

if not tagged or not tagged.articles:
    logger.error("Failed to get tagged articles from OpenAI")
    exit(1)

logger.info(f"Successfully tagged {len(tagged.articles)} articles")

logger.info("Loading articles to database")

# Create normalized database schema
CREATE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        summary TEXT,
        link TEXT UNIQUE NOT NULL,
        published TEXT,
        updated TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS article_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
        UNIQUE(article_id, tag_id)
    );
    """
]

def _get_or_create_tag(cursor, tag_name):
    """Get existing tag ID or create new tag and return ID"""
    # Try to get existing tag
    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    result = cursor.fetchone()

    if result:
        return result[0]

    # Create new tag
    cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
    return cursor.lastrowid

def load_articles_to_db(tagged_data, db_path="articles.db"):
    logger.info(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign key constraints
    cursor.execute("PRAGMA foreign_keys = ON")

    # Create tables
    logger.debug("Creating database tables if they don't exist")
    for table_sql in CREATE_TABLES_SQL:
        cursor.execute(table_sql)

    articles_loaded = 0

    # Insert articles and tags
    logger.info(f"Processing {len(tagged_data.articles)} articles for database insertion")
    for article in tagged_data.articles:
        try:
            # Insert or update article
            cursor.execute("""
                INSERT OR REPLACE INTO articles
                (title, summary, link, published, updated)
                VALUES (?, ?, ?, ?, ?)
            """, (
                article.title,
                article.summary,
                article.link,
                article.published,
                article.updated
            ))

            # Get the article ID (for INSERT OR REPLACE, this gets the ID of the inserted/updated row)
            article_id = cursor.execute(
                "SELECT id FROM articles WHERE link = ?", (article.link,)
            ).fetchone()[0]

            # Clear existing tags for this article (in case of update)
            cursor.execute("DELETE FROM article_tags WHERE article_id = ?", (article_id,))

            # Process tags
            logger.debug(f"Processing {len(article.tags)} tags for article: {article.title[:50]}")
            for tag_name in article.tags:
                if tag_name and tag_name.strip():
                    tag_name = tag_name.strip()

                    # Get or create tag
                    tag_id = _get_or_create_tag(cursor, tag_name)

                    # Link article to tag
                    try:
                        cursor.execute("""
                            INSERT INTO article_tags (article_id, tag_id)
                            VALUES (?, ?)
                        """, (article_id, tag_id))
                    except sqlite3.IntegrityError:
                        # Tag already exists for this article, skip
                        logger.debug(f"Tag '{tag_name}' already exists for article, skipping")

            articles_loaded += 1

        except sqlite3.Error as e:
            logger.error(f"Error inserting article '{article.title}': {e}")
            continue

    conn.commit()
    logger.debug("Database transaction committed")

    # Get counts for reporting
    article_count = cursor.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    tag_count = cursor.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

    conn.close()

    logger.info(f"Successfully loaded {articles_loaded} articles to database")
    logger.info(f"Total articles in database: {article_count}, Total unique tags: {tag_count}")

def get_articles_by_tag(tag_name, db_path="articles.db"):
    """Get all articles associated with a specific tag"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.id, a.title, a.summary, a.link, a.published, a.updated, a.created_at
        FROM articles a
        JOIN article_tags at ON a.id = at.article_id
        JOIN tags t ON at.tag_id = t.id
        WHERE t.name = ?
        ORDER BY a.created_at DESC
    """, (tag_name,))

    articles = cursor.fetchall()
    conn.close()
    return articles

def get_tag_counts(db_path="articles.db"):
    """Get count of articles per tag"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t.name, COUNT(at.article_id) as article_count
        FROM tags t
        LEFT JOIN article_tags at ON t.id = at.tag_id
        GROUP BY t.id, t.name
        ORDER BY article_count DESC, t.name
    """)

    tag_counts = cursor.fetchall()
    conn.close()
    return tag_counts

def get_popular_tags(limit=10, db_path="articles.db"):
    """Get most popular tags by article count"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t.name, COUNT(at.article_id) as article_count
        FROM tags t
        JOIN article_tags at ON t.id = at.tag_id
        GROUP BY t.id, t.name
        ORDER BY article_count DESC
        LIMIT ?
    """, (limit,))

    popular_tags = cursor.fetchall()
    conn.close()
    return popular_tags

# Load the tagged articles to database
try:
    load_articles_to_db(tagged)
except Exception as e:
    logger.error(f"Error loading articles to database: {e}")
    exit(1)

# Generate analytics
logger.info("Generating tag analytics")

# Show tag counts
tag_counts = get_tag_counts()
logger.info(f"Found {len(tag_counts)} unique tags")

# Show popular tags
popular = get_popular_tags(5)
if popular:
    logger.info("Top 5 popular tags:")
    for tag_name, count in popular:
        logger.info(f"  {tag_name}: {count} articles")

    # Show articles for most popular tag
    top_tag = popular[0][0]
    articles = get_articles_by_tag(top_tag)
    logger.info(f"Found {len(articles)} articles tagged with '{top_tag}'")

    if articles:
        logger.debug(f"Sample articles for '{top_tag}':")
        for article in articles[:3]:  # Show first 3
            logger.debug(f"  - {article[1][:60]}...")

logger.info("RSS processing completed successfully")
