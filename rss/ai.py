import sys
import os
import time
import logging
from typing import Optional
import json

import openai

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.models import ArticleCollection

logger = logging.getLogger(__name__)

# Constants for OpenAI
MAX_RETRIES = 3
RETRY_DELAY = 1

# Initialize OpenAI client with error handling
try:
    client = openai.Client()
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    client = None


def _process_batch(articles_batch: list, batch_num: int) -> Optional[ArticleCollection]:
    """Process a single batch of articles through OpenAI"""
    try:
        # Convert articles to dict format for OpenAI
        articles_data = []
        for article in articles_batch:
            articles_data.append({
                'title': article.title,
                'summary': article.summary,
                'link': article.link,
                'published': article.published,
                'updated': article.updated,
                'source': article.source,
                'og_image': article.og_image
            })

        # Prepare OpenAI request
        articles_json = json.dumps(articles_data, indent=2, default=str)
        logger.info(f"Processing batch {batch_num} with {len(articles_data)} articles")

        # Make OpenAI request with retries
        for attempt in range(MAX_RETRIES):
            try:
                response = client.responses.parse(
                    model="gpt-4o-2024-08-06",
                    input=[
                        {
                            "role": "system",
                            "content": "Tag each article with one or more of the following tags: ['Artificial Intelligence', 'Technology', 'Startups']. If it doesn't belong to one of these tags, discard it. Also, clean up the important information (remove HTML tags and other junk).",
                        },
                        {
                            "role": "user",
                            "content": articles_json
                        }
                    ],
                    text_format=ArticleCollection
                )

                if not response or not hasattr(response, 'output_parsed'):
                    logger.error(f"Invalid response from OpenAI for batch {batch_num} on attempt {attempt + 1}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    return None

                tagged_articles = response.output_parsed

                if not isinstance(tagged_articles, ArticleCollection):
                    logger.error(f"OpenAI returned invalid ArticleCollection format for batch {batch_num}")
                    return None

                logger.info(f"Successfully processed batch {batch_num} with {len(tagged_articles.articles)} articles")
                return tagged_articles

            except openai.RateLimitError as e:
                logger.warning(f"OpenAI rate limit hit for batch {batch_num} on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                raise

            except openai.APIError as e:
                logger.error(f"OpenAI API error for batch {batch_num} on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                raise

            except Exception as e:
                logger.error(f"Unexpected error calling OpenAI for batch {batch_num} on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                break

        logger.error(f"Failed to get valid response from OpenAI for batch {batch_num} after {MAX_RETRIES} attempts")
        return None

    except Exception as e:
        logger.error(f"Unexpected error processing batch {batch_num}: {e}")
        return None


def route_to_openai(article_collection: ArticleCollection, db_path: str = "articles.db") -> Optional[ArticleCollection]:
    """Send ArticleCollection to OpenAI for tagging in batches of 10 and save each batch to database"""
    if not client:
        logger.error("OpenAI client not initialized")
        return None

    if not article_collection or not article_collection.articles:
        logger.warning("Empty article collection provided")
        return ArticleCollection(articles=[])

    # Import database functions
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import load_articles_to_db

    articles = article_collection.articles
    total_articles = len(articles)
    batch_size = 10

    logger.info(f"Processing {total_articles} articles in batches of {batch_size}")

    # Split articles into batches
    batches = [articles[i:i + batch_size] for i in range(0, total_articles, batch_size)]
    logger.info(f"Created {len(batches)} batches")

    all_tagged_articles = []

    for i, batch in enumerate(batches, 1):
        logger.info(f"Processing batch {i}/{len(batches)}")

        batch_result = _process_batch(batch, i)

        if batch_result and batch_result.articles:
            # Save this batch to database immediately
            try:
                load_articles_to_db(batch_result, db_path)
                logger.info(f"Saved batch {i} with {len(batch_result.articles)} articles to database")
            except Exception as e:
                logger.error(f"Failed to save batch {i} to database: {e}")

            all_tagged_articles.extend(batch_result.articles)
            logger.debug(f"Added {len(batch_result.articles)} articles from batch {i}")
        else:
            logger.error(f"Failed to process batch {i}, skipping")
            continue

        # Add delay between batches to avoid rate limits
        if i < len(batches):
            logger.debug(f"Waiting {RETRY_DELAY} seconds before next batch")
            time.sleep(RETRY_DELAY)

    if not all_tagged_articles:
        logger.error("No articles were successfully processed by OpenAI")
        return None

    logger.info(f"Successfully processed {len(all_tagged_articles)} total articles across {len(batches)} batches")
    return ArticleCollection(articles=all_tagged_articles)
