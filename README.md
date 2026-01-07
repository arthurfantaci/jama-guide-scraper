# Jama Requirements Management Guide Scraper

A Python tool to scrape and consolidate Jama Software's **"The Essential Guide to Requirements Management and Traceability"** into LLM-friendly formats for use with AI agents, MCP servers, and RAG systems.

## Features

- **Async scraping** with `httpx` for efficient parallel fetching
- **Rate limiting** to be respectful to the source server
- **Retry logic** with exponential backoff for reliability
- **Rich progress output** showing scraping status
- **Multiple output formats**:
  - **JSON**: Complete hierarchical structure
  - **JSONL**: One record per article (ideal for RAG chunking)
  - **Markdown**: Human-readable consolidated document
- **Comprehensive metadata** for knowledge graph construction:
  - Cross-references between sections
  - Key concepts extraction
  - Section-level parsing
  - Source URLs and timestamps

## Requirements

- **Python 3.13+** (uses modern datetime and typing features)
- **UV** (recommended) or pip for package management

## Installation

### Using UV (Recommended)

```bash
# Clone or copy the project
cd jama-guide-scraper

# Install dependencies (including dev tools)
uv sync --group dev

# Run the scraper
uv run python run.py
```

### Using pip

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Run the scraper
python run.py
```

## Usage

### Quick Start

```bash
# Run with default settings (outputs JSON + JSONL)
python run.py
```

### CLI Usage

After installation, you can use the `jama-scrape` command:

```bash
# Basic usage
jama-scrape

# Specify output directory
jama-scrape --output ./data

# Include all formats
jama-scrape -f json -f jsonl -f markdown

# Include raw HTML (for debugging)
jama-scrape --include-html

# Adjust rate limiting
jama-scrape --rate-limit 2.0
```

### Programmatic Usage

```python
import asyncio
from pathlib import Path
from jama_scraper import JamaGuideScraper, run_scraper

# Quick run with defaults
guide = asyncio.run(run_scraper())

# Or with more control
async def custom_scrape():
    scraper = JamaGuideScraper(
        rate_limit_delay=1.5,  # seconds between requests
        max_concurrent=2,      # parallel requests
        include_raw_html=False,
    )
    
    guide = await scraper.scrape_all()
    
    # Save in multiple formats
    scraper.save_json(guide, Path("output/guide.json"))
    scraper.save_jsonl(guide, Path("output/guide.jsonl"))
    scraper.save_markdown(guide, Path("output/guide.md"))
    
    return guide

guide = asyncio.run(custom_scrape())
print(f"Scraped {guide.total_articles} articles")
```

## Output Formats

### JSON Structure

The JSON output contains the complete hierarchical structure:

```json
{
  "metadata": {
    "title": "The Essential Guide to Requirements Management and Traceability",
    "publisher": "Jama Software",
    "base_url": "https://www.jamasoftware.com/requirements-management-guide/",
    "scraped_at": "2024-01-15T10:30:00Z",
    "total_chapters": 15
  },
  "chapters": [
    {
      "chapter_number": 1,
      "title": "Requirements Management",
      "overview_url": "...",
      "articles": [
        {
          "article_id": "ch1-art1",
          "title": "What is Requirements Management?",
          "url": "...",
          "content_type": "article",
          "markdown_content": "...",
          "sections": [...],
          "key_concepts": ["Requirements Management", "Traceability"],
          "cross_references": [...],
          "word_count": 1500
        }
      ]
    }
  ],
  "glossary": {
    "terms": [
      {
        "term": "Traceability",
        "definition": "..."
      }
    ]
  }
}
```

### JSONL Structure

Each line in the JSONL file is a self-contained record, ideal for RAG systems:

```jsonl
{"type": "article", "guide_title": "...", "chapter_number": 1, "chapter_title": "Requirements Management", "article_id": "ch1-art1", "title": "What is Requirements Management?", ...}
{"type": "article", "guide_title": "...", "chapter_number": 1, "chapter_title": "Requirements Management", "article_id": "ch1-art2", ...}
{"type": "glossary_term", "guide_title": "...", "term": "Traceability", "definition": "..."}
```

## Data Models

The scraper uses Pydantic models for type safety and serialization:

- **`RequirementsManagementGuide`**: Root model containing everything
- **`Chapter`**: A chapter with multiple articles
- **`Article`**: Individual article with content and metadata
- **`Section`**: Parsed section within an article
- **`CrossReference`**: Link to another section or external resource
- **`Glossary`**: Collection of glossary terms
- **`GlossaryTerm`**: Single term with definition

## Project Structure

```
jama-guide-scraper/
├── pyproject.toml          # Project configuration (UV/pip compatible)
├── README.md               # This file
├── CLAUDE.md               # AI assistant guidance
├── run.py                  # Quick-run script
├── .python-version         # Python 3.13
├── .gitattributes          # Git line ending config
├── .env.example            # Environment template (for future GraphRAG)
├── .vscode/                # VS Code configuration
│   ├── settings.json       # Editor, Ruff, Pylance settings
│   ├── extensions.json     # Recommended extensions
│   └── launch.json         # Debug configurations
├── src/
│   └── jama_scraper/
│       ├── __init__.py     # Package exports
│       ├── cli.py          # Command-line interface
│       ├── config.py       # URLs and configuration
│       ├── models.py       # Pydantic data models
│       ├── parser.py       # HTML to Markdown parser
│       └── scraper.py      # Async scraper logic
├── tests/
│   ├── __init__.py
│   └── conftest.py         # Pytest fixtures
└── output/                 # Generated output (created on run)
    ├── requirements_management_guide.json
    ├── requirements_management_guide.jsonl
    └── requirements_management_guide.md
```

## Use Cases

### RAG / Vector Database Ingestion

The JSONL format is ideal for chunking and embedding:

```python
import json

with open("output/requirements_management_guide.jsonl") as f:
    for line in f:
        record = json.loads(line)
        
        # Create embedding-friendly text
        text = f"{record['chapter_title']} - {record['title']}\n\n{record['markdown_content']}"
        
        # Add to your vector database
        # vector_db.add(text, metadata=record)
```

### Knowledge Graph Construction

Use the cross-references to build relationships:

```python
import json

with open("output/requirements_management_guide.json") as f:
    guide = json.load(f)

edges = []
for chapter in guide["chapters"]:
    for article in chapter["articles"]:
        for ref in article["cross_references"]:
            if ref["is_internal"]:
                edges.append({
                    "source": article["article_id"],
                    "target": ref["target_section_id"],
                    "relationship": "references",
                })
```

### MCP Server Integration

Load the guide data into an MCP server for AI assistant access:

```python
from jama_scraper import RequirementsManagementGuide
import json

# Load scraped data
with open("output/requirements_management_guide.json") as f:
    data = json.load(f)
    guide = RequirementsManagementGuide.model_validate(data)

# Use in your MCP server
def search_guide(query: str) -> list[dict]:
    results = []
    for chapter in guide.chapters:
        for article in chapter.articles:
            if query.lower() in article.markdown_content.lower():
                results.append({
                    "title": article.title,
                    "chapter": chapter.title,
                    "url": article.url,
                    "excerpt": article.markdown_content[:500],
                })
    return results
```

## Development

### Running Tests

```bash
uv run pytest
```

### Linting & Formatting

```bash
uv run ruff check .          # Lint check
uv run ruff check . --fix    # Auto-fix lint issues
uv run ruff format .         # Format code
```

### Type Checking

```bash
uv run ty check src/         # Type check with ty (Astral's type checker)
```

### Code Style

This project enforces strict Python standards:

- **Line length**: 88 characters (Black standard)
- **Docstrings**: Google-style, required for public functions
- **Type annotations**: Required for public functions
- **Import sorting**: Automatic via Ruff

See `pyproject.toml` for the full Ruff and ty configuration.

### VS Code Integration

The `.vscode/` directory contains pre-configured settings:
- Ruff integration with format-on-save
- Pylance type checking
- Debug configurations for CLI and pytest
- Recommended extensions

Open the project in VS Code and install the recommended extensions when prompted.

## Legal Notice

This tool is for educational and research purposes. Please respect Jama Software's terms of service and use the scraped content responsibly. The content remains the intellectual property of Jama Software.

## License

MIT License - See LICENSE file for details.
