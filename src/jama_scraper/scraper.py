"""Async web scraper for the Jama Requirements Management Guide.

Features:
- Async HTTP requests with httpx
- Rate limiting to be respectful to the server
- Retry logic with exponential backoff
- Progress tracking with Rich
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import (
    CHAPTERS,
    GLOSSARY_URL,
    MAX_CONCURRENT_REQUESTS,
    MAX_RETRIES,
    RATE_LIMIT_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    ArticleConfig,
    ChapterConfig,
)
from .models import (
    Article,
    Chapter,
    ContentType,
    Glossary,
    GlossaryTerm,
    GuideMetadata,
    RequirementsManagementGuide,
)
from .parser import HTMLParser

if TYPE_CHECKING:
    from rich.progress import TaskID

# HTTP status codes
HTTP_NOT_FOUND = 404

console = Console()


class JamaGuideScraper:
    """Scraper for the Jama Requirements Management Guide.

    Usage:
        scraper = JamaGuideScraper()
        guide = await scraper.scrape_all()
        scraper.save_json(guide, Path("output/guide.json"))
        scraper.save_jsonl(guide, Path("output/guide.jsonl"))
    """

    def __init__(
        self,
        rate_limit_delay: float = RATE_LIMIT_DELAY_SECONDS,
        max_concurrent: int = MAX_CONCURRENT_REQUESTS,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        include_raw_html: bool = False,
    ) -> None:
        """Initialize the scraper with rate limiting and concurrency settings."""
        self.rate_limit_delay = rate_limit_delay
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.include_raw_html = include_raw_html
        self.parser = HTMLParser()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._last_request_time = 0.0

    async def scrape_all(self) -> RequirementsManagementGuide:
        """Scrape the entire guide including all chapters and glossary."""
        console.print(
            "[bold blue]Starting Jama Requirements Management Guide Scraper[/]"
        )
        console.print(
            f"Rate limit: {self.rate_limit_delay}s delay, "
            f"{self.max_concurrent} concurrent requests"
        )

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "JamaGuideScraper/0.1.0 (Educational/Research)"},
        ) as client:
            # First, discover any missing articles from chapter overviews
            chapters_config = await self._discover_all_articles(client)

            # Scrape all chapters
            chapters = await self._scrape_all_chapters(client, chapters_config)

            # Scrape glossary
            glossary = await self._scrape_glossary(client)

            guide = RequirementsManagementGuide(
                metadata=GuideMetadata(scraped_at=datetime.now(UTC)),
                chapters=chapters,
                glossary=glossary,
            )

            console.print("\n[bold green]✓ Scraping complete![/]")
            console.print(f"  Chapters: {len(guide.chapters)}")
            console.print(f"  Total articles: {guide.total_articles}")
            console.print(f"  Total words: {guide.total_word_count:,}")
            if guide.glossary:
                console.print(f"  Glossary terms: {guide.glossary.term_count}")

            return guide

    async def _discover_all_articles(
        self, client: httpx.AsyncClient
    ) -> list[ChapterConfig]:
        """Discover articles by scraping chapter overview pages."""
        console.print("\n[yellow]Discovering articles from chapter overviews...[/]")

        updated_chapters = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Discovering...", total=len(CHAPTERS))

            for chapter_config in CHAPTERS:
                # If chapter only has overview, try to discover more
                current_chapter = chapter_config
                if len(chapter_config.articles) <= 1:
                    html = await self._fetch_with_rate_limit(
                        client, chapter_config.overview_url
                    )
                    if html:
                        discovered = self.parser.discover_articles(
                            html, chapter_config.slug
                        )
                        if discovered:
                            console.print(
                                f"  Found {len(discovered)} articles "
                                f"in Chapter {chapter_config.number}"
                            )
                            # Create new chapter config with discovered articles
                            new_articles = [ArticleConfig(0, "Overview", "")]
                            for i, art in enumerate(discovered, 1):
                                new_articles.append(
                                    ArticleConfig(i, art["title"], art["slug"])
                                )
                            current_chapter = replace(
                                chapter_config, articles=new_articles
                            )

                updated_chapters.append(current_chapter)
                progress.advance(task)

        return updated_chapters

    async def _scrape_all_chapters(
        self,
        client: httpx.AsyncClient,
        chapters_config: list[ChapterConfig],
    ) -> list[Chapter]:
        """Scrape all chapters."""
        console.print("\n[yellow]Scraping chapters...[/]")

        chapters = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            total_articles = sum(len(ch.articles) for ch in chapters_config)
            task = progress.add_task("Scraping articles...", total=total_articles)

            for chapter_config in chapters_config:
                chapter = await self._scrape_chapter(
                    client, chapter_config, progress, task
                )
                chapters.append(chapter)

        return chapters

    async def _scrape_chapter(
        self,
        client: httpx.AsyncClient,
        config: ChapterConfig,
        progress: Progress,
        task: "TaskID",
    ) -> Chapter:
        """Scrape a single chapter."""
        articles = []

        for article_config in config.articles:
            url = config.get_article_url(article_config)

            html = await self._fetch_with_rate_limit(client, url)

            if html:
                parsed = self.parser.parse_article(html, url)

                content_type = (
                    ContentType.CHAPTER_OVERVIEW
                    if article_config.number == 0
                    else ContentType.ARTICLE
                )

                article = Article(
                    article_id=f"ch{config.number}-art{article_config.number}",
                    chapter_number=config.number,
                    article_number=article_config.number,
                    title=parsed["title"] or article_config.title,
                    url=url,
                    content_type=content_type,
                    raw_html=html if self.include_raw_html else None,
                    markdown_content=parsed["markdown_content"],
                    sections=parsed["sections"],
                    key_concepts=parsed["key_concepts"],
                    cross_references=parsed["cross_references"],
                    images=parsed["images"],
                )
                articles.append(article)
            else:
                console.print(f"[red]Failed to fetch: {url}[/]")

            progress.advance(task)

        return Chapter(
            chapter_number=config.number,
            title=config.title,
            overview_url=config.overview_url,
            articles=articles,
        )

    async def _scrape_glossary(self, client: httpx.AsyncClient) -> Glossary | None:
        """Scrape the glossary page."""
        console.print("\n[yellow]Scraping glossary...[/]")

        html = await self._fetch_with_rate_limit(client, GLOSSARY_URL)

        if not html:
            console.print("[red]Failed to fetch glossary[/]")
            return None

        terms_data = self.parser.parse_glossary(html, GLOSSARY_URL)

        terms = [
            GlossaryTerm(
                term=t["term"],
                definition=t["definition"],
            )
            for t in terms_data
        ]

        console.print(f"  Found {len(terms)} glossary terms")

        return Glossary(
            url=GLOSSARY_URL,
            terms=terms,
        )

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def _fetch_with_rate_limit(
        self, client: httpx.AsyncClient, url: str
    ) -> str | None:
        """Fetch a URL with rate limiting and retry logic."""
        async with self._semaphore:
            # Rate limiting
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            if elapsed < self.rate_limit_delay:
                await asyncio.sleep(self.rate_limit_delay - elapsed)

            try:
                response = await client.get(url)
                response.raise_for_status()
                self._last_request_time = asyncio.get_event_loop().time()
                return response.text
            except httpx.HTTPStatusError as e:
                if e.response.status_code == HTTP_NOT_FOUND:
                    console.print(f"[yellow]404 Not Found: {url}[/]")
                    return None
                raise
            except Exception as e:
                console.print(f"[red]Error fetching {url}: {e}[/]")
                raise

    def save_json(self, guide: RequirementsManagementGuide, path: Path) -> None:
        """Save the guide as a single JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                guide.model_dump(
                    exclude={"raw_html"} if not self.include_raw_html else None
                ),
                f,
                indent=2,
                default=str,  # Handle datetime
            )

        console.print(f"[green]Saved JSON to: {path}[/]")

    def save_jsonl(self, guide: RequirementsManagementGuide, path: Path) -> None:
        """Save the guide as JSONL (one record per article/term)."""
        path.parent.mkdir(parents=True, exist_ok=True)

        records = guide.to_jsonl_articles()

        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                json.dump(record, f, default=str)
                f.write("\n")

        console.print(f"[green]Saved JSONL to: {path} ({len(records)} records)[/]")

    def save_markdown(self, guide: RequirementsManagementGuide, path: Path) -> None:
        """Save the guide as a single consolidated Markdown file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# {guide.metadata.title}",
            "",
            f"*Published by {guide.metadata.publisher}*",
            f"*Scraped on {guide.metadata.scraped_at.strftime('%Y-%m-%d')}*",
            "",
            "---",
            "",
            "## Table of Contents",
            "",
        ]

        # TOC
        for chapter in guide.chapters:
            lines.append(f"- **Chapter {chapter.chapter_number}**: {chapter.title}")
            for article in chapter.articles:
                if article.article_number > 0:
                    lines.append(f"  - {article.title}")

        lines.extend(["", "---", ""])

        # Content
        for chapter in guide.chapters:
            lines.append(f"# Chapter {chapter.chapter_number}: {chapter.title}")
            lines.append("")

            for article in chapter.articles:
                if article.article_number == 0:
                    lines.append("## Overview")
                else:
                    lines.append(f"## {article.article_number}. {article.title}")

                lines.append("")
                lines.append(f"*Source: {article.url}*")
                lines.append("")
                lines.append(article.markdown_content)
                lines.append("")
                lines.append("---")
                lines.append("")

        # Glossary
        if guide.glossary:
            lines.append("# Glossary")
            lines.append("")
            for term in guide.glossary.terms:
                lines.append(f"**{term.term}**: {term.definition}")
                lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        console.print(f"[green]Saved Markdown to: {path}[/]")


async def run_scraper(
    output_dir: Path = Path("output"),
    include_raw_html: bool = False,
    formats: list[str] | None = None,
) -> RequirementsManagementGuide:
    """Run the scraper and save outputs.

    Args:
        output_dir: Directory for output files
        include_raw_html: Whether to include raw HTML in output
        formats: List of output formats ("json", "jsonl", "markdown")

    Returns:
        The scraped guide data
    """
    if formats is None:
        formats = ["json", "jsonl"]

    scraper = JamaGuideScraper(include_raw_html=include_raw_html)
    guide = await scraper.scrape_all()

    output_dir.mkdir(parents=True, exist_ok=True)

    if "json" in formats:
        scraper.save_json(guide, output_dir / "requirements_management_guide.json")

    if "jsonl" in formats:
        scraper.save_jsonl(guide, output_dir / "requirements_management_guide.jsonl")

    if "markdown" in formats:
        scraper.save_markdown(guide, output_dir / "requirements_management_guide.md")

    return guide
