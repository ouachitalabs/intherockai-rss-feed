import sqlite3
import logging
from datetime import datetime
import openai
from typing import Optional

logger = logging.getLogger(__name__)

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
        source TEXT,
        og_image TEXT,
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

def load_articles_to_db(tagged_data, db_path="articles.db", check_duplicates=True, similarity_threshold=0.70):
    logger.info(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign key constraints
    cursor.execute("PRAGMA foreign_keys = ON")

    # Create tables
    logger.debug("Creating database tables if they don't exist")
    for table_sql in CREATE_TABLES_SQL:
        cursor.execute(table_sql)

    # Initialize embeddings if checking duplicates
    if check_duplicates:
        try:
            from rss.embeddings import (
                initialize_vec_extension,
                check_duplicate,
                store_embedding,
                generate_embedding
            )
            initialize_vec_extension(conn)
            client = openai.Client()
            logger.info("Initialized embedding-based duplicate detection")
        except Exception as e:
            logger.warning(f"Could not initialize embeddings, continuing without duplicate detection: {e}")
            check_duplicates = False

    articles_loaded = 0
    duplicates_skipped = 0

    # Insert articles and tags
    logger.info(f"Processing {len(tagged_data.articles)} articles for database insertion")
    for article in tagged_data.articles:
        try:
            # Check for semantic duplicates if enabled
            if check_duplicates:
                duplicate_info = check_duplicate(
                    conn,
                    article.title,
                    article.summary,
                    similarity_threshold,
                    client
                )
                
                if duplicate_info:
                    duplicate_id, similarity = duplicate_info
                    logger.info(f"Skipping duplicate article (similar to ID {duplicate_id}, similarity: {similarity:.3f}): {article.title[:50]}...")
                    duplicates_skipped += 1
                    continue
            
            # Insert or update article
            cursor.execute("""
                INSERT OR REPLACE INTO articles
                (title, summary, link, published, updated, source, og_image)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                article.title,
                article.summary,
                article.link,
                article.published,
                article.updated,
                article.source,
                getattr(article, 'og_image', None)
            ))

            # Get the article ID (for INSERT OR REPLACE, this gets the ID of the inserted/updated row)
            article_id = cursor.execute(
                "SELECT id FROM articles WHERE link = ?", (article.link,)
            ).fetchone()[0]
            
            # Store embedding if duplicate checking is enabled
            if check_duplicates:
                article_text = f"{article.title} {article.summary or ''}"
                embedding = generate_embedding(article_text, client)
                if embedding:
                    store_embedding(conn, article_id, embedding)
                    logger.debug(f"Stored embedding for article {article_id}")
                else:
                    logger.warning(f"Could not generate embedding for article {article_id}")

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
    if duplicates_skipped > 0:
        logger.info(f"Skipped {duplicates_skipped} duplicate articles")
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