import datetime
from pydantic import BaseModel

class Article(BaseModel):
    title: str
    summary: str | None = None
    link: str # TODO - make this a true pydantic URL type
    published: datetime.datetime | None = None
    updated: datetime.datetime | None = None
    source: str | None = None
    tags: list[str] = []

class ArticleCollection(BaseModel):
    articles: list[Article]
