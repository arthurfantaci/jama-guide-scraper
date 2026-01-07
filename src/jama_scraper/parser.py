"""HTML parsing utilities for extracting and converting Jama guide content.

Converts HTML to clean Markdown and extracts metadata for RAG/knowledge graph use.
"""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from .config import BASE_URL
from .models import CrossReference, ImageReference, Section

# Constants for content extraction
MIN_CONCEPT_LENGTH = 2
MAX_CONCEPT_LENGTH = 50
MAX_KEY_CONCEPTS = 20
MIN_CONTENT_ELEMENTS = 2


class HTMLParser:
    """Parser for Jama guide HTML content."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        """Initialize the parser with the base URL for resolving relative links."""
        self.base_url = base_url

    def parse_article(self, html: str, source_url: str) -> dict:
        """Parse an article page and extract all content.

        Returns a dict with:
        - title: Article title
        - markdown_content: Full content as markdown
        - sections: List of Section objects
        - cross_references: List of CrossReference objects
        - key_concepts: Extracted key terms
        """
        soup = BeautifulSoup(html, "lxml")

        # Extract title
        title = self._extract_title(soup)

        # Find main content area
        content_elem = self._find_content_element(soup)

        if not content_elem:
            return {
                "title": title,
                "markdown_content": "",
                "sections": [],
                "cross_references": [],
                "key_concepts": [],
                "images": [],
            }

        # Extract cross-references before converting to markdown
        cross_refs = self._extract_cross_references(content_elem, source_url)

        # Extract images
        images = self._extract_images(content_elem, source_url)

        # Convert to markdown (now includes image references)
        markdown = self._html_to_markdown(content_elem, include_images=True)

        # Parse into sections
        sections = self._parse_sections(content_elem, source_url)

        # Extract key concepts
        key_concepts = self._extract_key_concepts(content_elem, title)

        return {
            "title": title,
            "markdown_content": markdown,
            "sections": sections,
            "cross_references": cross_refs,
            "key_concepts": key_concepts,
            "images": images,
        }

    def parse_glossary(self, html: str, _source_url: str) -> list[dict]:
        """Parse the glossary page and extract all terms.

        Args:
            html: Raw HTML content of the glossary page.
            _source_url: Source URL (unused, kept for API consistency).

        Returns:
            A list of dicts with 'term' and 'definition' keys.
        """
        soup = BeautifulSoup(html, "lxml")
        content_elem = self._find_content_element(soup)

        if not content_elem:
            return []

        terms = []

        # Glossaries often use dt/dd, h3/p, or strong/text patterns
        # Try multiple strategies

        # Strategy 1: Definition lists
        for dl in content_elem.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds, strict=False):
                terms.append(
                    {
                        "term": dt.get_text(strip=True),
                        "definition": dd.get_text(strip=True),
                    }
                )

        # Strategy 2: Headings followed by paragraphs
        if not terms:
            current_term = None
            for elem in content_elem.find_all(["h2", "h3", "h4", "p"]):
                if elem.name in ["h2", "h3", "h4"]:
                    current_term = elem.get_text(strip=True)
                elif elem.name == "p" and current_term:
                    definition = elem.get_text(strip=True)
                    if definition:
                        terms.append(
                            {
                                "term": current_term,
                                "definition": definition,
                            }
                        )
                        current_term = None

        # Strategy 3: Strong tags for terms
        if not terms:
            for p in content_elem.find_all("p"):
                strong = p.find("strong")
                if strong:
                    term = strong.get_text(strip=True)
                    # Get text after the strong tag
                    definition_parts = []
                    for sibling in strong.next_siblings:
                        if isinstance(sibling, NavigableString):
                            definition_parts.append(str(sibling))
                        elif isinstance(sibling, Tag):
                            definition_parts.append(sibling.get_text())
                    definition = " ".join(definition_parts).strip()
                    definition = re.sub(
                        r"^[:\s\-]+", "", definition
                    )  # Remove leading colons/dashes
                    if term and definition:
                        terms.append(
                            {
                                "term": term,
                                "definition": definition,
                            }
                        )

        return terms

    def discover_articles(self, html: str, chapter_slug: str) -> list[dict]:
        """Discover article links from a chapter overview or TOC page.

        Returns list of dicts with:
        - title: Article title
        - slug: URL slug
        - url: Full URL
        """
        soup = BeautifulSoup(html, "lxml")
        articles = []
        seen_slugs = set()

        # Find all internal links that match the chapter pattern
        pattern = re.compile(
            rf"/requirements-management-guide/{re.escape(chapter_slug)}/([^/]+)/?"
        )

        for link in soup.find_all("a", href=True):
            href = link["href"]
            match = pattern.search(href)
            if match:
                slug = match.group(1)
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    articles.append(
                        {
                            "title": link.get_text(strip=True),
                            "slug": slug,
                            "url": urljoin(self.base_url, href),
                        }
                    )

        return articles

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract the page title."""
        # Try h1 first
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        # Fall back to title tag
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Remove common suffixes
            for suffix in [" | Jama Software", " - Jama Software"]:
                if title.endswith(suffix):
                    title = title[: -len(suffix)]
            return title

        return "Untitled"

    def _find_content_element(self, soup: BeautifulSoup) -> Tag | None:
        """Find the main content container."""
        # Jama's site uses Enfold/Avia theme with flex_cell layout
        # The second flex_cell contains the main article content (first is navigation)
        flex_cells = soup.select(".flex_cell")
        if len(flex_cells) >= MIN_CONTENT_ELEMENTS:
            return flex_cells[1]

        # Fallback: common content selectors
        selectors = [
            "article",
            ".post-content",
            ".entry-content",
            ".content-area",
            "main",
            "#main-content",
            ".main-content",
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem

        # Fall back to body
        return soup.find("body")

    def _extract_cross_references(
        self, elem: Tag, source_url: str
    ) -> list[CrossReference]:
        """Extract all links as cross-references."""
        refs = []
        source_domain = urlparse(source_url).netloc

        for link in elem.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            if not text or not href:
                continue

            # Skip anchor links and javascript
            if href.startswith(("#", "javascript:")):
                continue

            # Normalize URL
            full_url = urljoin(source_url, href)
            parsed = urlparse(full_url)

            # Check if internal
            is_internal = (
                parsed.netloc == source_domain or "jamasoftware.com" in parsed.netloc
            )

            # Try to extract section ID for internal links
            section_id = None
            if is_internal and "/requirements-management-guide/" in full_url:
                match = re.search(
                    r"/requirements-management-guide/([^/]+)/([^/]+)?", full_url
                )
                if match:
                    chapter_slug = match.group(1)
                    article_slug = match.group(2) or "overview"
                    section_id = f"{chapter_slug}/{article_slug}"

            refs.append(
                CrossReference(
                    text=text,
                    url=full_url,
                    is_internal=is_internal,
                    target_section_id=section_id,
                )
            )

        return refs

    def _extract_images(self, elem: Tag, source_url: str) -> list[ImageReference]:
        """Extract all images from the content as ImageReference objects."""
        images = []
        seen_urls = set()

        for img in elem.find_all("img"):
            # Get the actual image URL (skip lazy-loading placeholders)
            src = img.get("src", "")

            # Skip data: URLs (lazy loading placeholders)
            if src.startswith("data:"):
                # Try to get from data-src or parent noscript
                src = img.get("data-src", "") or img.get("data-lazy-src", "")

            # Also check noscript siblings for actual URL
            if not src or src.startswith("data:"):
                noscript = img.find_next_sibling("noscript")
                if noscript:
                    noscript_img = BeautifulSoup(str(noscript), "lxml").find("img")
                    if noscript_img:
                        src = noscript_img.get("src", "")

            # Skip if no valid URL or already seen
            if not src or src.startswith("data:") or src in seen_urls:
                continue

            seen_urls.add(src)

            # Normalize URL
            full_url = urljoin(source_url, src)

            # Get alt text and title
            alt_text = img.get("alt", "")
            title = img.get("title") or None

            # Look for figcaption
            caption = None
            figure = img.find_parent("figure")
            if figure:
                figcaption = figure.find("figcaption")
                if figcaption:
                    caption = figcaption.get_text(strip=True)

            # Get surrounding context (previous heading or paragraph)
            context = None
            prev_heading = img.find_previous(["h2", "h3", "h4"])
            if prev_heading:
                context = prev_heading.get_text(strip=True)

            images.append(
                ImageReference(
                    url=full_url,
                    alt_text=alt_text,
                    title=title,
                    caption=caption,
                    context=context,
                )
            )

        return images

    def _html_to_markdown(self, elem: Tag, include_images: bool = False) -> str:
        """Convert HTML element to markdown."""
        lines = []

        for child in elem.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    lines.append(text)
            elif isinstance(child, Tag):
                lines.append(self._tag_to_markdown(child, include_images))

        # Clean up the result
        markdown = "\n\n".join(line for line in lines if line.strip())
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)  # Limit consecutive newlines
        return markdown.strip()

    def _tag_to_markdown(self, tag: Tag, include_images: bool = False) -> str:
        """Convert a single tag to markdown."""
        name = tag.name

        # Handle images
        if name == "img" and include_images:
            return self._img_to_markdown(tag)

        # Handle noscript (skip - we handle images from the main img tags)
        if name == "noscript":
            return ""

        # Headings
        if name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(name[1])
            text = tag.get_text(strip=True)
            return f"{'#' * level} {text}"

        # Paragraphs
        if name == "p":
            return self._inline_to_markdown(tag)

        # Lists
        if name == "ul":
            items = []
            for li in tag.find_all("li", recursive=False):
                items.append(f"- {self._inline_to_markdown(li)}")
            return "\n".join(items)

        if name == "ol":
            items = []
            for i, li in enumerate(tag.find_all("li", recursive=False), 1):
                items.append(f"{i}. {self._inline_to_markdown(li)}")
            return "\n".join(items)

        # Blockquotes
        if name == "blockquote":
            text = self._inline_to_markdown(tag)
            return "\n".join(f"> {line}" for line in text.split("\n"))

        # Code blocks
        if name == "pre":
            code = tag.find("code")
            if code:
                lang = ""
                if code.get("class"):
                    for cls in code["class"]:
                        if cls.startswith("language-"):
                            lang = cls[9:]
                            break
                return f"```{lang}\n{code.get_text()}\n```"
            return f"```\n{tag.get_text()}\n```"

        # Divs and other containers - recurse
        if name in ["div", "section", "article", "main", "aside"]:
            return self._html_to_markdown(tag, include_images)

        # Tables
        if name == "table":
            return self._table_to_markdown(tag)

        # Default: just get text
        return tag.get_text(strip=True)

    def _img_to_markdown(self, img: Tag) -> str:
        """Convert an image tag to markdown with description."""
        # Get the actual image URL (skip lazy-loading placeholders)
        src = img.get("src", "")

        # Skip data: URLs - try alternatives
        if src.startswith("data:"):
            src = img.get("data-src", "") or img.get("data-lazy-src", "")

        # Check noscript for actual URL
        if not src or src.startswith("data:"):
            noscript = img.find_next_sibling("noscript")
            if noscript:
                noscript_img = BeautifulSoup(str(noscript), "lxml").find("img")
                if noscript_img:
                    src = noscript_img.get("src", "")

        if not src or src.startswith("data:"):
            return ""

        alt_text = img.get("alt", "")
        title = img.get("title", "")

        # Build description from available metadata
        description = alt_text or title or "Image"

        # Return markdown image with description
        return f"![{description}]({src})"

    def _inline_to_markdown(self, tag: Tag) -> str:
        """Convert inline content to markdown."""
        parts = []

        for child in tag.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif isinstance(child, Tag):
                if child.name in {"strong", "b"}:
                    parts.append(f"**{child.get_text()}**")
                elif child.name in {"em", "i"}:
                    parts.append(f"*{child.get_text()}*")
                elif child.name == "code":
                    parts.append(f"`{child.get_text()}`")
                elif child.name == "a":
                    text = child.get_text()
                    href = child.get("href", "")
                    parts.append(f"[{text}]({href})")
                elif child.name == "br":
                    parts.append("\n")
                elif child.name == "img":
                    parts.append(self._img_to_markdown(child))
                elif child.name == "noscript":
                    pass  # Skip noscript tags
                else:
                    parts.append(child.get_text())

        return "".join(parts).strip()

    def _table_to_markdown(self, table: Tag) -> str:
        """Convert HTML table to markdown table."""
        rows = []

        # Headers
        thead = table.find("thead")
        if thead:
            header_row = thead.find("tr")
            if header_row:
                headers = [
                    th.get_text(strip=True) for th in header_row.find_all(["th", "td"])
                ]
                rows.append("| " + " | ".join(headers) + " |")
                rows.append("| " + " | ".join(["---"] * len(headers)) + " |")

        # Body
        tbody = table.find("tbody") or table
        for tr in tbody.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                # Add header separator if we didn't have thead
                if len(rows) == 0:
                    rows.append("| " + " | ".join(cells) + " |")
                    rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
                else:
                    rows.append("| " + " | ".join(cells) + " |")

        return "\n".join(rows)

    def _parse_sections(self, elem: Tag, source_url: str) -> list[Section]:
        """Parse content into sections based on headings."""
        sections = []
        current_heading = None
        current_level = 0
        current_content = []

        for child in elem.descendants:
            if isinstance(child, Tag) and child.name in ["h2", "h3", "h4"]:
                # Save previous section
                if current_heading:
                    sections.append(
                        Section(
                            heading=current_heading,
                            level=current_level,
                            content="\n\n".join(current_content).strip(),
                            cross_references=self._extract_cross_references(
                                BeautifulSoup(
                                    "".join(str(c) for c in current_content), "lxml"
                                ),
                                source_url,
                            )
                            if current_content
                            else [],
                        )
                    )

                # Start new section
                current_heading = child.get_text(strip=True)
                current_level = int(child.name[1])
                current_content = []

            elif isinstance(child, Tag) and child.name == "p" and current_heading:
                current_content.append(self._inline_to_markdown(child))

        # Don't forget the last section
        if current_heading:
            sections.append(
                Section(
                    heading=current_heading,
                    level=current_level,
                    content="\n\n".join(current_content).strip(),
                    cross_references=[],
                )
            )

        return sections

    def _extract_key_concepts(self, elem: Tag, title: str) -> list[str]:
        """Extract key concepts/terms from the content."""
        concepts = set()

        # Add title words (excluding common words)
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "dare",
            "ought",
            "used",
            "how",
            "what",
            "why",
            "when",
            "where",
            "who",
            "which",
            "whom",
            "whose",
            "that",
            "this",
            "these",
            "those",
            "it",
            "its",
            "you",
            "your",
            "we",
            "our",
            "they",
            "their",
            "i",
            "my",
            "me",
            "he",
            "she",
            "him",
            "her",
            "his",
            "with",
            "from",
            "by",
            "about",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
        }

        for word in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", title):
            if word.lower() not in stop_words and len(word) > MIN_CONCEPT_LENGTH:
                concepts.add(word)

        # Look for emphasized terms
        for tag in elem.find_all(["strong", "b", "em"]):
            text = tag.get_text(strip=True)
            if (
                MIN_CONCEPT_LENGTH < len(text) < MAX_CONCEPT_LENGTH
                and text.lower() not in stop_words
            ):
                concepts.add(text)

        # Look for definition-like patterns
        for text in elem.stripped_strings:
            # Pattern: "Term is ..." or "Term refers to ..."
            match = re.match(
                r"^([A-Z][a-zA-Z\s]+?)\s+(?:is|are|refers?\s+to|means?)\s+", text
            )
            if match:
                term = match.group(1).strip()
                if len(term) < MAX_CONCEPT_LENGTH:
                    concepts.add(term)

        return sorted(concepts)[:MAX_KEY_CONCEPTS]
