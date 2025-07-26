import smtplib
import ssl
import os
import logging
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from datetime import datetime
from typing import List, Optional
from api.models import Article

logger = logging.getLogger(__name__)

def send_new_articles_email(articles: List[Article], recipient_email: str = None) -> bool:
    """Send email notification with new articles"""
    
    if not articles:
        logger.info("No articles to send, skipping email notification")
        return True
    
    # Email configuration from environment variables
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')
    recipient = recipient_email or os.getenv('RECIPIENT_EMAIL')
    
    if not all([sender_email, sender_password, recipient]):
        logger.error("Email configuration missing. Required: SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL")
        return False
    
    try:
        # Create message
        message = MimeMultipart("alternative")
        message["Subject"] = f"🗞️ {len(articles)} New Arkansas News Articles"
        message["From"] = sender_email
        message["To"] = recipient
        
        # Create HTML content
        html_content = _create_html_email(articles)
        
        # Create text version
        text_content = _create_text_email(articles)
        
        # Attach parts
        text_part = MimeText(text_content, "plain")
        html_part = MimeText(html_content, "html")
        
        message.attach(text_part)
        message.attach(html_part)
        
        # Send email
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient, message.as_string())
        
        logger.info(f"Successfully sent email notification for {len(articles)} articles to {recipient}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")
        return False

def _create_html_email(articles: List[Article]) -> str:
    """Create HTML email content"""
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ background: #007bff; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .article {{ border-bottom: 1px solid #eee; padding: 15px 0; display: flex; gap: 15px; }}
            .article:last-child {{ border-bottom: none; }}
            .article-image {{ width: 80px; height: 60px; object-fit: cover; border-radius: 4px; flex-shrink: 0; }}
            .article-content {{ flex: 1; }}
            .article-title {{ color: #333; font-weight: bold; margin: 0 0 5px 0; }}
            .article-title a {{ color: #007bff; text-decoration: none; }}
            .article-summary {{ color: #666; font-size: 14px; margin: 5px 0; line-height: 1.4; }}
            .article-meta {{ color: #888; font-size: 12px; }}
            .source {{ color: #007bff; font-weight: 500; }}
            .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; border-top: 1px solid #eee; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🗞️ Arkansas News Update</h1>
                <p>{len(articles)} new articles found on {timestamp}</p>
            </div>
            <div class="content">
    """
    
    for article in articles:
        # Use Arkansas flag as default image
        image_url = article.og_image or "https://upload.wikimedia.org/wikipedia/commons/9/9d/Flag_of_Arkansas.svg"
        
        # Truncate summary if too long
        summary = article.summary[:150] + "..." if article.summary and len(article.summary) > 150 else article.summary
        
        published_date = ""
        if article.published:
            try:
                pub_date = datetime.fromisoformat(article.published.replace('Z', '+00:00'))
                published_date = pub_date.strftime("%b %d, %Y")
            except:
                published_date = "Unknown date"
        
        html += f"""
                <div class="article">
                    <img src="{image_url}" alt="Article image" class="article-image">
                    <div class="article-content">
                        <h3 class="article-title"><a href="{article.link}" target="_blank">{article.title}</a></h3>
                        {f'<div class="article-summary">{summary}</div>' if summary else ''}
                        <div class="article-meta">
                            {f'<span class="source">{article.source}</span>' if article.source else ''}
                            {f' • {published_date}' if published_date else ''}
                            {f' • Tags: {", ".join(article.tags)}' if article.tags else ''}
                        </div>
                    </div>
                </div>
        """
    
    html += """
            </div>
            <div class="footer">
                <p>This email was automatically generated by the InTheRock.ai news processing system.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

def _create_text_email(articles: List[Article]) -> str:
    """Create plain text email content"""
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    
    text = f"Arkansas News Update - {len(articles)} new articles found on {timestamp}\\n"
    text += "=" * 60 + "\\n\\n"
    
    for i, article in enumerate(articles, 1):
        published_date = ""
        if article.published:
            try:
                pub_date = datetime.fromisoformat(article.published.replace('Z', '+00:00'))
                published_date = pub_date.strftime("%b %d, %Y")
            except:
                published_date = "Unknown date"
        
        text += f"{i}. {article.title}\\n"
        text += f"   Link: {article.link}\\n"
        if article.source:
            text += f"   Source: {article.source}\\n"
        if published_date:
            text += f"   Published: {published_date}\\n"
        if article.tags:
            text += f"   Tags: {', '.join(article.tags)}\\n"
        if article.summary:
            summary = article.summary[:200] + "..." if len(article.summary) > 200 else article.summary
            text += f"   Summary: {summary}\\n"
        text += "\\n"
    
    text += "\\n" + "-" * 60 + "\\n"
    text += "This email was automatically generated by the InTheRock.ai news processing system."
    
    return text