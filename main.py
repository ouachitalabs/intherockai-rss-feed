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
from database import get_articles_by_tag, get_tag_counts, get_popular_tags

urls = [
    "https://arktimes.com/feed",
    "https://www.arkansasbusiness.com/feed/",
    "https://talkbusiness.net/feed/",
    "https://arkansasadvocate.com/feed/",
    "https://www.kark.com/feed/",
    # "Arkansas" artificial intelligence
    "https://www.google.com/alerts/feeds/12746746318701075297/3421192965394397903",
    # "Arkansas" startup
    "https://www.google.com/alerts/feeds/12746746318701075297/1492688489120319382",
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


# Note: Articles are now saved to database after each batch in route_to_openai()
logger.info("Articles have been saved to database after each batch processing")

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
