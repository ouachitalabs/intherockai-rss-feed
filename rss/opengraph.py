import requests
import logging
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Optional

logger = logging.getLogger(__name__)

# Domains known to block scraping
BLOCKED_DOMAINS = {
    'arkansasadvocate.com'
}

def extract_og_image(url: str, timeout: int = 10) -> Optional[str]:
    """
    Extract Open Graph image URL from a webpage.
    
    Args:
        url: The URL to scrape
        timeout: Request timeout in seconds
        
    Returns:
        Open Graph image URL if found, None otherwise
    """
    if not url or not url.strip():
        return None
    
    # Check if domain is known to block scraping
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower()
    if any(blocked_domain in domain for blocked_domain in BLOCKED_DOMAINS):
        logger.debug(f"Skipping {url} - domain known to block scraping")
        return None
        
    try:
        logger.debug(f"Fetching Open Graph data from: {url}")
        
        # Rotate between different user agents to avoid detection
        user_agents = [
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
        ]
        
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for Open Graph image meta tag
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content'].strip()
            
            # Convert relative URLs to absolute
            if image_url.startswith('//'):
                # Protocol-relative URL
                parsed_url = urlparse(url)
                image_url = f"{parsed_url.scheme}:{image_url}"
            elif image_url.startswith('/'):
                # Relative URL
                image_url = urljoin(url, image_url)
            elif not image_url.startswith(('http://', 'https://')):
                # Relative URL without leading slash
                image_url = urljoin(url, image_url)
            
            logger.debug(f"Found Open Graph image: {image_url}")
            return image_url
        
        # Fallback: look for other image meta tags
        twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
        if twitter_image and twitter_image.get('content'):
            image_url = twitter_image['content'].strip()
            if not image_url.startswith(('http://', 'https://')):
                image_url = urljoin(url, image_url)
            logger.debug(f"Found Twitter image as fallback: {image_url}")
            return image_url
            
        # Another fallback: look for article image
        article_image = soup.find('meta', attrs={'property': 'article:image'})
        if article_image and article_image.get('content'):
            image_url = article_image['content'].strip()
            if not image_url.startswith(('http://', 'https://')):
                image_url = urljoin(url, image_url)
            logger.debug(f"Found article image as fallback: {image_url}")
            return image_url
        
        logger.debug(f"No Open Graph image found for: {url}")
        return None
        
    except requests.RequestException as e:
        if '403' in str(e):
            logger.debug(f"403 Forbidden for {domain} - adding to blocked domains")
            BLOCKED_DOMAINS.add(domain)
        else:
            logger.warning(f"Failed to fetch {url} for Open Graph extraction: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error extracting Open Graph image from {url}: {e}")
        return None


def extract_og_images_batch(urls: list[str], timeout: int = 10, delay_range: tuple = (0.5, 2.0)) -> dict[str, Optional[str]]:
    """
    Extract Open Graph images from multiple URLs with rate limiting.
    
    Args:
        urls: List of URLs to process
        timeout: Request timeout in seconds per URL
        delay_range: Random delay range between requests (min, max) in seconds
        
    Returns:
        Dictionary mapping URL to Open Graph image URL (or None if not found)
    """
    results = {}
    total_urls = len(urls)
    
    for i, url in enumerate(urls):
        results[url] = extract_og_image(url, timeout)
        
        # Add random delay between requests to be respectful to servers
        if i < total_urls - 1:  # Don't delay after the last request
            delay = random.uniform(delay_range[0], delay_range[1])
            time.sleep(delay)
    
    return results