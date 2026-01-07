"""Command-line interface for the Jama Guide Scraper."""

import argparse
import asyncio
from pathlib import Path

from rich.console import Console

from .scraper import run_scraper

console = Console()


def main() -> None:
    """Run the Jama Guide Scraper CLI."""
    parser = argparse.ArgumentParser(
        description="Scrape Jama Software's Requirements Management Guide",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - outputs JSON and JSONL
  jama-scrape

  # Specify output directory
  jama-scrape --output ./data

  # Include all formats including Markdown
  jama-scrape --format json --format jsonl --format markdown

  # Include raw HTML for debugging
  jama-scrape --include-html
        """,
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory for scraped files (default: ./output)",
    )

    parser.add_argument(
        "-f",
        "--format",
        action="append",
        choices=["json", "jsonl", "markdown"],
        dest="formats",
        help="Output format(s). Can be specified multiple times. Default: json, jsonl",
    )

    parser.add_argument(
        "--include-html",
        action="store_true",
        help="Include raw HTML in output (increases file size significantly)",
    )

    parser.add_argument(
        "--rate-limit",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0)",
    )

    args = parser.parse_args()

    # Default formats if none specified
    formats = args.formats or ["json", "jsonl"]

    console.print("[bold]Jama Requirements Management Guide Scraper[/]")
    console.print(f"Output directory: {args.output}")
    console.print(f"Formats: {', '.join(formats)}")

    try:
        asyncio.run(
            run_scraper(
                output_dir=args.output,
                include_raw_html=args.include_html,
                formats=formats,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Scraping interrupted by user[/]")
        raise SystemExit(1) from None
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/]")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
