# Services built for local AI meetup (intherock.ai)

## Tagging service

Input: RSS feed
Output: Database records of RSS content + AI generated tags

### Purpose

- Ingest RSS feeds
- convert to JSON
- send JSON to OpenAI for tagging
- store information in database

### Details

Simple cron job scheduling (open to alternatives)
Python RSS -> JSON conversion using RSS feed library
Python sqlite3 database storage

Main two queries that will be coming from the website:
(Open to data model suggestions here, but ideally a single table for now)

- `select * from feed where tags contains tag;`
- `select tag, count(1) as n from feed;`

## API

The api exposes the data that is produced by the tagging service to users on the website.

### Endpoints

Fetch articles that relate to one or more tags:
```
GET /articles/?tag=...&tag=...
```

Fetch all tags and their counts:
```
GET /tags/
```

### Auth

No auth, all public api endpoints and database.
This is not mission critical stuff and we want people to have access to it.
We will address caching and other potential issues like that when the time comes.
For now, focus on an MVP.
