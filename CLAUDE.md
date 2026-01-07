# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an async Python scraper that consolidates Jama Software's "Essential Guide to Requirements Management and Traceability" into LLM-friendly formats (JSON, JSONL, Markdown) for use with AI agents, MCP servers, and RAG systems.

## Commands

### Install and Run
```bash
# Using UV (recommended)
uv sync
uv run python run.py

# Using pip
pip install -e .
python run.py
```

### CLI Usage
```bash
jama-scrape                           # Default: outputs JSON + JSONL
jama-scrape -o ./data                 # Custom output directory
jama-scrape -f json -f jsonl -f markdown  # Multiple formats
jama-scrape --include-html            # Include raw HTML in output
```

### Development
```bash
uv sync --group dev          # Install with dev tools
uv run pytest                # Run tests
uv run ruff check .          # Lint
uv run ruff format .         # Format
uv run ty check src/         # Type check
```

## Code Style Standards

This project uses strict Python standards enforced by Ruff and ty:

- **Python 3.13** - Latest language features
- **Line length**: 88 characters (Black standard)
- **Docstrings**: Google-style, required for all public functions
- **Type annotations**: Required for all public functions
- **Import sorting**: isort via Ruff

### Ruff Rule Sets
- Core: E, W, F (pycodestyle, pyflakes)
- Quality: B, C4, UP, SIM, RUF (bugbear, comprehensions, pyupgrade)
- Docs: D (pydocstyle with Google convention)
- Security: S (bandit)
- Types: ANN, TCH (annotations, TYPE_CHECKING optimization)
- Structure: TRY, EM, PIE, PT, RET, ARG, PL (best practices)

### VS Code Setup
The `.vscode/` directory contains:
- `settings.json` - Ruff integration, Pylance, pytest, format-on-save
- `extensions.json` - Recommended extensions (Ruff, Pylance, etc.)
- `launch.json` - Debug configurations for CLI, run.py, and pytest

## Architecture

The scraper follows a pipeline architecture:

1. **config.py** - Contains all URL configurations, chapter/article mappings, and rate limiting settings. `ChapterConfig` and `ArticleConfig` dataclasses define the guide structure. Some chapters have incomplete article lists and are discovered dynamically by scraping overview pages.

2. **scraper.py** - `JamaGuideScraper` is the main class. Uses `httpx.AsyncClient` with semaphore-based concurrency control and tenacity retry logic. The scraping flow:
   - `scrape_all()` → `_discover_all_articles()` → `_scrape_all_chapters()` → `_scrape_glossary()`
   - Rate limiting via `_fetch_with_rate_limit()` with configurable delay between requests

3. **parser.py** - `HTMLParser` converts HTML to Markdown and extracts metadata. Key methods:
   - `parse_article()` - Extracts title, markdown content, sections, cross-references, key concepts
   - `parse_glossary()` - Handles multiple glossary HTML patterns (dl/dt/dd, headings, strong tags)
   - `discover_articles()` - Finds article links from chapter overview pages

4. **models.py** - Pydantic models with computed fields for word/character counts. The `RequirementsManagementGuide` root model has `to_jsonl_articles()` for RAG-friendly export.

## Key Design Decisions

- Async with semaphore concurrency (default 3 parallel requests) for respectful scraping
- Exponential backoff retry on HTTP errors (max 3 retries)
- Articles auto-discovered from chapter overviews when not pre-configured in `config.py`
- Cross-references tracked with internal/external classification for knowledge graph use
- JSONL format provides self-contained records per article for easy RAG chunking
