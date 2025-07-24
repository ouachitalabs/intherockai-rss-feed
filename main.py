import json
import sqlite3
from datetime import datetime

# Configure SQLite to handle datetime strings
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("TIMESTAMP", lambda s: datetime.fromisoformat(s.decode()))

from rss.ai import route_to_openai, clean_rss

url = 'https://www.google.com/alerts/feeds/12746746318701075297/17060129154597278148'
rss = clean_rss(url)

if not rss:
    print("Error: Failed to clean RSS feed")
    exit(1)

print("Cleaned RSS: ", json.dumps(rss, indent=2))

tagged = route_to_openai(rss)

if not tagged or not tagged.articles:
    print("Error: NO TAGGED ARTICLES")
    exit(1)

print("Tagged RSS: ")
print(tagged.model_dump_json(indent=2))

print("Load to the database: ")

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
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Enable foreign key constraints
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # Create tables
    for table_sql in CREATE_TABLES_SQL:
        cursor.execute(table_sql)
    
    articles_loaded = 0
    
    # Insert articles and tags
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
                        pass
            
            articles_loaded += 1
            
        except sqlite3.Error as e:
            print(f"Error inserting article {article.title}: {e}")
            continue
    
    conn.commit()
    
    # Get counts for reporting
    article_count = cursor.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    tag_count = cursor.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    
    conn.close()
    
    print(f"Successfully loaded {articles_loaded} articles to database.")
    print(f"Total articles: {article_count}, Total unique tags: {tag_count}")

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
    print(f"Error loading articles to database: {e}")

# Demonstrate the new querying capabilities
print("\n" + "="*50)
print("TAG ANALYTICS")
print("="*50)

# Show tag counts
print("\nTag counts:")
tag_counts = get_tag_counts()
for tag_name, count in tag_counts:
    print(f"  {tag_name}: {count} articles")

# Show popular tags
print("\nTop 5 popular tags:")
popular = get_popular_tags(5)
for tag_name, count in popular:
    print(f"  {tag_name}: {count} articles")
    
# Show articles for a specific tag (if any exist)
if popular:
    top_tag = popular[0][0]
    print(f"\nArticles tagged with '{top_tag}':")
    articles = get_articles_by_tag(top_tag)
    for article in articles[:3]:  # Show first 3
        print(f"  - {article[1][:60]}...")  # title truncated
