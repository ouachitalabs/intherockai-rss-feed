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


def route_to_openai(article_collection: ArticleCollection) -> Optional[ArticleCollection]:
    """Send ArticleCollection to OpenAI for tagging"""
    if not client:
        logger.error("OpenAI client not initialized")
        return None

    if not article_collection or not article_collection.articles:
        logger.warning("Empty article collection provided")
        return ArticleCollection(articles=[])

    try:
        # Convert articles to dict format for OpenAI
        articles_data = []
        for article in article_collection.articles:
            articles_data.append({
                'title': article.title,
                'summary': article.summary,
                'link': article.link,
                'published': article.published,
                'updated': article.updated
            })

        # Prepare OpenAI request
        articles_json = json.dumps(articles_data, indent=2, default=str)
        logger.info(f"Sending {len(articles_data)} articles to OpenAI for tagging")

        # Make OpenAI request with retries
        for attempt in range(MAX_RETRIES):
            try:
                response = client.responses.parse(
                    model="gpt-4o-2024-08-06",
                    input=[
                        {
                            "role": "system",
                            "content": "Tag each article with relevant categories and clean up the important information. Return valid JSON only."
                        },
                        {
                            "role": "user",
                            "content": articles_json
                        }
                    ],
                    text_format=ArticleCollection
                )

                if not response or not hasattr(response, 'output_parsed'):
                    logger.error(f"Invalid response from OpenAI on attempt {attempt + 1}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    return None

                tagged_articles = response.output_parsed

                if not isinstance(tagged_articles, ArticleCollection):
                    logger.error("OpenAI returned invalid ArticleCollection format")
                    return None

                logger.info(f"Successfully processed {len(tagged_articles.articles)} articles with OpenAI")
                return tagged_articles

            except openai.RateLimitError as e:
                logger.warning(f"OpenAI rate limit hit on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                raise

            except openai.APIError as e:
                logger.error(f"OpenAI API error on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                raise

            except Exception as e:
                logger.error(f"Unexpected error calling OpenAI on attempt {attempt + 1}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                break

        logger.error(f"Failed to get valid response from OpenAI after {MAX_RETRIES} attempts")
        return None

    except Exception as e:
        logger.error(f"Unexpected error in route_to_openai: {e}")
        return None
