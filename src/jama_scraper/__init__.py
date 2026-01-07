"""Jama Requirements Management Guide Scraper.

A tool to scrape and consolidate Jama Software's "Essential Guide to
Requirements Management and Traceability" into LLM-friendly formats.

Usage:
    from jama_scraper import JamaGuideScraper, run_scraper
    import asyncio

    # Quick run
    guide = asyncio.run(run_scraper())

    # Or with more control
    scraper = JamaGuideScraper()
    guide = asyncio.run(scraper.scrape_all())
"""

from .models import (
    Article,
    Chapter,
    ContentType,
    CrossReference,
    Glossary,
    GlossaryTerm,
    GuideMetadata,
    ImageReference,
    RequirementsManagementGuide,
    Section,
)
from .scraper import JamaGuideScraper, run_scraper

__version__ = "0.1.0"

__all__ = [
    "Article",
    "Chapter",
    "ContentType",
    "CrossReference",
    "Glossary",
    "GlossaryTerm",
    "GuideMetadata",
    "ImageReference",
    "JamaGuideScraper",
    "RequirementsManagementGuide",
    "Section",
    "run_scraper",
]
