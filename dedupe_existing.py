#!/usr/bin/env python3
"""
One-time deduplication script for existing articles in the database.
This script:
1. Generates embeddings for all existing articles
2. Finds semantically similar articles
3. Removes duplicates keeping the earliest version
4. Stores embeddings for remaining articles
"""

import sqlite3
import logging
from datetime import datetime
import sys
import os
from typing import List, Dict, Set
import openai

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from rss.embeddings import (
    initialize_vec_extension,
    generate_embeddings_batch,
    store_embedding,
    find_similar_articles
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
SIMILARITY_THRESHOLD = 0.70  # Adjusted based on testing - articles about same topic score 0.6-0.75
DB_PATH = "articles.db"
BACKUP_PATH = f"articles.db.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def load_all_articles(conn: sqlite3.Connection) -> List[Dict]:
    """Load all articles from database"""
    cursor = conn.execute("""
        SELECT id, title, summary, link, published
        FROM articles
        ORDER BY id
    """)
    
    articles = []
    for row in cursor:
        articles.append({
            'id': row[0],
            'title': row[1],
            'summary': row[2],
            'link': row[3],
            'published': row[4]
        })
    
    return articles


def find_duplicate_groups(
    conn: sqlite3.Connection,
    articles: List[Dict],
    embeddings: List[List[float]]
) -> Dict[int, Set[int]]:
    """
    Find groups of duplicate articles based on embeddings.
    Returns a dict mapping the earliest article ID to set of duplicate IDs.
    """
    duplicate_groups = {}
    processed = set()
    
    logger.info("Finding duplicate articles...")
    
    for i, (article, embedding) in enumerate(zip(articles, embeddings)):
        if article['id'] in processed or embedding is None:
            continue
        
        # Find similar articles
        similar = find_similar_articles(conn, embedding, SIMILARITY_THRESHOLD, limit=20)
        
        if similar:
            # Get all similar article IDs (excluding self)
            similar_ids = {aid for aid, _ in similar if aid != article['id']}
            
            if similar_ids:
                # Find the earliest article in the group
                all_ids = similar_ids | {article['id']}
                earliest_id = min(all_ids)
                
                # Add to duplicate groups
                if earliest_id not in duplicate_groups:
                    duplicate_groups[earliest_id] = set()
                
                duplicate_groups[earliest_id].update(all_ids - {earliest_id})
                processed.update(all_ids)
                
                logger.debug(f"Found duplicate group: keeping {earliest_id}, removing {all_ids - {earliest_id}}")
        
        if (i + 1) % 100 == 0:
            logger.info(f"Processed {i + 1}/{len(articles)} articles")
    
    return duplicate_groups


def main():
    """Main deduplication process"""
    logger.info("Starting article deduplication process")
    
    # Create backup
    logger.info(f"Creating database backup: {BACKUP_PATH}")
    import shutil
    shutil.copy2(DB_PATH, BACKUP_PATH)
    
    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # Initialize sqlite-vec
        initialize_vec_extension(conn)
        
        # Load all articles
        articles = load_all_articles(conn)
        logger.info(f"Loaded {len(articles)} articles from database")
        
        if not articles:
            logger.info("No articles to process")
            return
        
        # Generate embeddings for all articles
        logger.info("Generating embeddings for all articles...")
        texts = [f"{a['title']} {a['summary'] or ''}" for a in articles]
        
        client = openai.Client()
        embeddings = generate_embeddings_batch(texts, client)
        
        # Count successful embeddings
        valid_embeddings = sum(1 for e in embeddings if e is not None)
        logger.info(f"Generated {valid_embeddings}/{len(articles)} embeddings successfully")
        
        # Store embeddings first (needed for similarity search)
        logger.info("Storing embeddings in database...")
        stored = 0
        for article, embedding in zip(articles, embeddings):
            if embedding is not None:
                if store_embedding(conn, article['id'], embedding):
                    stored += 1
        
        conn.commit()
        logger.info(f"Stored {stored} embeddings")
        
        # Find duplicate groups
        duplicate_groups = find_duplicate_groups(conn, articles, embeddings)
        
        # Calculate total duplicates to remove
        total_duplicates = sum(len(dups) for dups in duplicate_groups.values())
        logger.info(f"Found {total_duplicates} duplicate articles to remove")
        
        if total_duplicates > 0:
            # Remove duplicates
            logger.info("Removing duplicate articles...")
            
            for keep_id, remove_ids in duplicate_groups.items():
                # Log what we're doing - check if keep article still exists
                cursor = conn.execute(
                    "SELECT title FROM articles WHERE id = ?", (keep_id,)
                )
                result = cursor.fetchone()
                if result:
                    keep_title = result[0]
                    logger.debug(f"Keeping article {keep_id}: {keep_title[:50]}...")
                    
                    for remove_id in remove_ids:
                        # Check if article exists before deleting
                        cursor = conn.execute(
                            "SELECT title FROM articles WHERE id = ?", (remove_id,)
                        )
                        result = cursor.fetchone()
                        if result:
                            remove_title = result[0]
                            # Delete the article
                            conn.execute("DELETE FROM articles WHERE id = ?", (remove_id,))
                            # Delete its embedding
                            conn.execute("DELETE FROM article_embeddings WHERE article_id = ?", (remove_id,))
                            logger.debug(f"  Removed duplicate article {remove_id}: {remove_title[:50]}...")
                        else:
                            logger.debug(f"  Article {remove_id} already removed")
                else:
                    logger.warning(f"Keep article {keep_id} not found, skipping group")
            
            conn.commit()
            logger.info(f"Successfully removed {total_duplicates} duplicate articles")
            
            # Clean up article_tags for deleted articles
            logger.info("Cleaning up orphaned tags...")
            conn.execute("""
                DELETE FROM article_tags 
                WHERE article_id NOT IN (SELECT id FROM articles)
            """)
            
            # Remove unused tags
            conn.execute("""
                DELETE FROM tags 
                WHERE id NOT IN (SELECT DISTINCT tag_id FROM article_tags)
            """)
            
            conn.commit()
            
            # Vacuum database to reclaim space
            logger.info("Vacuuming database...")
            conn.execute("VACUUM")
        
        # Final statistics
        cursor = conn.execute("SELECT COUNT(*) FROM articles")
        final_count = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM article_embeddings")
        embedding_count = cursor.fetchone()[0]
        
        logger.info(f"Deduplication complete!")
        logger.info(f"  Original articles: {len(articles)}")
        logger.info(f"  Duplicates removed: {total_duplicates}")
        logger.info(f"  Final article count: {final_count}")
        logger.info(f"  Embeddings stored: {embedding_count}")
        logger.info(f"  Database backup saved to: {BACKUP_PATH}")
        
    except Exception as e:
        logger.error(f"Error during deduplication: {e}")
        conn.rollback()
        raise
    
    finally:
        conn.close()


if __name__ == "__main__":
    main()