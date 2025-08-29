import sqlite3
import sqlite_vec
import openai
import json
import logging
from typing import List, Tuple, Optional
import time

logger = logging.getLogger(__name__)

# Constants
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
BATCH_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAY = 1


def initialize_vec_extension(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec extension and create embeddings table if needed"""
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    
    # Create virtual table for embeddings if it doesn't exist
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS article_embeddings USING vec0(
            article_id INTEGER PRIMARY KEY,
            embedding float[1536]
        )
    """)
    conn.commit()
    logger.info("Initialized sqlite-vec extension and embeddings table")


def generate_embedding(text: str, client: Optional[openai.Client] = None) -> Optional[List[float]]:
    """Generate embedding for a single text using OpenAI text-embedding-3-small"""
    if not client:
        client = openai.Client()
    
    if not text or not text.strip():
        logger.warning("Empty text provided for embedding")
        return None
    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.embeddings.create(
                input=text[:8000],  # Truncate to avoid token limits
                model=EMBEDDING_MODEL
            )
            return response.data[0].embedding
        
        except openai.RateLimitError as e:
            logger.warning(f"Rate limit hit on attempt {attempt + 1}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            return None
        
        except Exception as e:
            logger.error(f"Error generating embedding on attempt {attempt + 1}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return None
    
    return None


def generate_embeddings_batch(texts: List[str], client: Optional[openai.Client] = None) -> List[Optional[List[float]]]:
    """Generate embeddings for multiple texts in batches"""
    if not client:
        client = openai.Client()
    
    embeddings = []
    
    # Process in batches
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        batch_texts = [t[:8000] if t else "" for t in batch]  # Truncate long texts
        
        for attempt in range(MAX_RETRIES):
            try:
                response = client.embeddings.create(
                    input=batch_texts,
                    model=EMBEDDING_MODEL
                )
                
                batch_embeddings = [data.embedding for data in response.data]
                embeddings.extend(batch_embeddings)
                logger.debug(f"Generated embeddings for batch {i//BATCH_SIZE + 1}")
                break
                
            except openai.RateLimitError as e:
                logger.warning(f"Rate limit hit for batch on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                # If all retries failed, add None for this batch
                embeddings.extend([None] * len(batch))
                break
                
            except Exception as e:
                logger.error(f"Error generating batch embeddings on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                embeddings.extend([None] * len(batch))
                break
        
        # Add delay between batches
        if i + BATCH_SIZE < len(texts):
            time.sleep(RETRY_DELAY)
    
    return embeddings


def store_embedding(conn: sqlite3.Connection, article_id: int, embedding: List[float]) -> bool:
    """Store an embedding for an article"""
    try:
        embedding_json = json.dumps(embedding)
        conn.execute("""
            INSERT OR REPLACE INTO article_embeddings (article_id, embedding)
            VALUES (?, ?)
        """, (article_id, embedding_json))
        return True
    except Exception as e:
        logger.error(f"Error storing embedding for article {article_id}: {e}")
        return False


def find_similar_articles(
    conn: sqlite3.Connection, 
    embedding: List[float], 
    threshold: float = 0.85,
    limit: int = 10
) -> List[Tuple[int, float]]:
    """
    Find articles with similarity above threshold
    Returns list of (article_id, similarity_score) tuples
    """
    try:
        embedding_json = json.dumps(embedding)
        
        # Query for similar articles using KNN
        cursor = conn.execute("""
            SELECT article_id, distance 
            FROM article_embeddings 
            WHERE embedding MATCH ? 
            ORDER BY distance 
            LIMIT ?
        """, (embedding_json, limit))
        
        results = []
        for article_id, distance in cursor:
            # Convert L2 distance to cosine similarity approximation
            # For normalized vectors, cosine_similarity ≈ 1 - (distance^2 / 2)
            # Since text-embedding-3-small returns normalized vectors
            similarity = max(0, 1 - (distance * distance / 2))
            
            if similarity >= threshold:
                results.append((article_id, similarity))
        
        return results
        
    except Exception as e:
        logger.error(f"Error finding similar articles: {e}")
        return []


def check_duplicate(
    conn: sqlite3.Connection,
    title: str,
    summary: str,
    threshold: float = 0.85,
    client: Optional[openai.Client] = None
) -> Optional[Tuple[int, float]]:
    """
    Check if an article is a duplicate based on semantic similarity
    Returns (article_id, similarity) of the most similar article if above threshold, None otherwise
    """
    # Generate embedding for the new article
    text = f"{title} {summary or ''}"
    embedding = generate_embedding(text, client)
    
    if not embedding:
        logger.warning(f"Could not generate embedding for article: {title[:50]}")
        return None
    
    # Find similar articles
    similar = find_similar_articles(conn, embedding, threshold, limit=1)
    
    if similar:
        article_id, similarity = similar[0]
        logger.info(f"Found similar article (ID: {article_id}, similarity: {similarity:.3f}) for: {title[:50]}")
        return (article_id, similarity)
    
    return None


def get_article_embedding(conn: sqlite3.Connection, article_id: int) -> Optional[List[float]]:
    """Retrieve embedding for a specific article"""
    try:
        cursor = conn.execute("""
            SELECT embedding 
            FROM article_embeddings 
            WHERE article_id = ?
        """, (article_id,))
        
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None
        
    except Exception as e:
        logger.error(f"Error retrieving embedding for article {article_id}: {e}")
        return None


def delete_embedding(conn: sqlite3.Connection, article_id: int) -> bool:
    """Delete embedding for an article"""
    try:
        conn.execute("""
            DELETE FROM article_embeddings 
            WHERE article_id = ?
        """, (article_id,))
        return True
    except Exception as e:
        logger.error(f"Error deleting embedding for article {article_id}: {e}")
        return False