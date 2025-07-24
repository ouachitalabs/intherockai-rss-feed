import sqlite3
import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from .models import Article, ArticleCollection

app = FastAPI(
    title="News Feed API", 
    description="Read-only API for news feed with article pagination and tag filtering",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

DATABASE_PATH = "articles.db"

def get_db_connection():
    """Get database connection with row factory for dict-like access"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def parse_datetime(date_str: Optional[str]) -> Optional[datetime.datetime]:
    """Parse datetime string from database"""
    if not date_str:
        return None
    try:
        return datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None

def get_article_tags(article_id: int, conn: sqlite3.Connection) -> List[str]:
    """Get tags for a specific article"""
    cursor = conn.execute("""
        SELECT t.name 
        FROM tags t
        JOIN article_tags at ON t.id = at.tag_id
        WHERE at.article_id = ?
    """, (article_id,))
    return [row["name"] for row in cursor.fetchall()]

@app.get("/")
def read_root():
    """Root endpoint with API information"""
    return {"message": "News Feed API", "version": "1.0.0"}

@app.get("/articles", response_model=ArticleCollection)
def get_articles(
    limit: int = Query(default=50, le=500, description="Maximum number of articles to return"),
    offset: int = Query(default=0, ge=0, description="Number of articles to skip"),
    tag: Optional[str] = Query(default=None, description="Filter by tag name")
):
    """Get paginated articles for news feed with optional tag filtering"""
    conn = get_db_connection()
    try:
        if tag:
            query = """
                SELECT DISTINCT a.id, a.title, a.summary, a.link, a.published, a.updated, a.source
                FROM articles a
                JOIN article_tags at ON a.id = at.article_id
                JOIN tags t ON at.tag_id = t.id
                WHERE t.name = ?
                ORDER BY a.created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = conn.execute(query, (tag, limit, offset))
        else:
            query = """
                SELECT id, title, summary, link, published, updated, source
                FROM articles
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = conn.execute(query, (limit, offset))
        
        articles = []
        for row in cursor.fetchall():
            tags = get_article_tags(row["id"], conn)
            article = Article(
                title=row["title"],
                summary=row["summary"],
                link=row["link"],
                published=parse_datetime(row["published"]),
                updated=parse_datetime(row["updated"]),
                source=row["source"],
                tags=tags
            )
            articles.append(article)
        
        return ArticleCollection(articles=articles)
    finally:
        conn.close()


@app.get("/tags")
def get_tags():
    """Get all available tags with article counts, sorted by count descending"""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT t.name, COUNT(at.article_id) as article_count
            FROM tags t
            LEFT JOIN article_tags at ON t.id = at.tag_id
            GROUP BY t.id, t.name
            ORDER BY article_count DESC, t.name
        """)
        tags_with_counts = [{"name": row["name"], "count": row["article_count"]} for row in cursor.fetchall()]
        return {"tags": tags_with_counts}
    finally:
        conn.close()


@app.get("/health")
def health_check():
    """Health check endpoint"""
    conn = get_db_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) as count FROM articles")
        article_count = cursor.fetchone()["count"]
        return {"status": "healthy", "article_count": article_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        conn.close()