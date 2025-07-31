# InTheRock.ai RSS Feed Service

AI-powered news aggregation and tagging service for the InTheRock.ai local AI meetup.

## Features

- **RSS Feed Processing**: Ingests RSS feeds and converts to structured data
- **AI Tagging**: Uses OpenAI to generate relevant tags for articles
- **SQLite Storage**: Simple database for articles and tags
- **REST API**: Public endpoints for article and tag queries
- **Email Notifications**: Sends notifications when new articles are processed

## Development

Activate virtual environment:
```bash
. .venv/bin/activate
```

Run commands:
```bash
make help      # Show available commands
make install   # Install/update dependencies
make api       # Start the API server
```

## API Endpoints

- `GET /articles/?tag=...&tag=...` - Fetch articles by tags
- `GET /tags/` - Get all tags with counts

## Deployment

Deployed on DigitalOcean as `intherock-api.service` with nginx reverse proxy.
