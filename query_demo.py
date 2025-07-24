#!/usr/bin/env python3
"""
Demo script showing the normalized database querying capabilities
"""
import sqlite3
from main import get_articles_by_tag, get_tag_counts, get_popular_tags

def show_database_structure():
    """Show the database structure"""
    conn = sqlite3.connect("articles.db")
    cursor = conn.cursor()
    
    print("=== DATABASE STRUCTURE ===\n")
    
    # Show articles table
    cursor.execute("SELECT COUNT(*) FROM articles")
    article_count = cursor.fetchone()[0]
    print(f"Articles table: {article_count} records")
    
    # Show tags table
    cursor.execute("SELECT COUNT(*) FROM tags")
    tag_count = cursor.fetchone()[0]
    print(f"Tags table: {tag_count} records")
    
    # Show article_tags junction table
    cursor.execute("SELECT COUNT(*) FROM article_tags")
    relation_count = cursor.fetchone()[0]
    print(f"Article-Tag relationships: {relation_count} records")
    
    conn.close()

def demo_tag_queries():
    """Demonstrate tag-based queries"""
    print("\n=== TAG ANALYTICS ===\n")
    
    # Show all tags with counts
    print("All tags with article counts:")
    tag_counts = get_tag_counts()
    for tag_name, count in tag_counts:
        print(f"  📊 {tag_name}: {count} articles")
    
    print(f"\nMost popular tags:")
    popular = get_popular_tags(3)
    for tag_name, count in popular:
        print(f"  🏆 {tag_name}: {count} articles")
    
    # Show articles for each popular tag
    if popular:
        print(f"\n=== ARTICLES BY TAG ===\n")
        for tag_name, count in popular[:2]:  # Show top 2 tags
            print(f"Articles tagged with '{tag_name}':")
            articles = get_articles_by_tag(tag_name)
            for i, article in enumerate(articles, 1):
                print(f"  {i}. {article[1]}")  # title
                print(f"     Link: {article[3]}")  # link
                print(f"     Published: {article[4]}")  # published
                print()

def demo_sql_queries():
    """Show some advanced SQL queries possible with normalized schema"""
    print("=== ADVANCED QUERIES ===\n")
    
    conn = sqlite3.connect("articles.db")
    cursor = conn.cursor()
    
    # Articles with multiple tags
    print("Articles with multiple tags:")
    cursor.execute("""
        SELECT a.title, COUNT(at.tag_id) as tag_count
        FROM articles a
        JOIN article_tags at ON a.id = at.article_id
        GROUP BY a.id, a.title
        HAVING tag_count > 1
        ORDER BY tag_count DESC
    """)
    multi_tag_articles = cursor.fetchall()
    for title, tag_count in multi_tag_articles:
        print(f"  📝 {title[:50]}... ({tag_count} tags)")
    
    # Co-occurring tags (tags that appear together)
    print(f"\nTag co-occurrence (tags that appear together):")
    cursor.execute("""
        SELECT t1.name, t2.name, COUNT(*) as co_occurrence
        FROM article_tags at1
        JOIN article_tags at2 ON at1.article_id = at2.article_id
        JOIN tags t1 ON at1.tag_id = t1.id
        JOIN tags t2 ON at2.tag_id = t2.id
        WHERE t1.id < t2.id
        GROUP BY t1.id, t2.id
        ORDER BY co_occurrence DESC
        LIMIT 5
    """)
    co_occurrences = cursor.fetchall()
    for tag1, tag2, count in co_occurrences:
        print(f"  🔗 {tag1} + {tag2}: {count} articles")
    
    conn.close()

if __name__ == "__main__":
    show_database_structure()
    demo_tag_queries()
    demo_sql_queries()