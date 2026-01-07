"""Pytest configuration and shared test fixtures.

This module provides fixtures for testing the Jama Guide Scraper,
including sample HTML content and mock HTTP responses.
"""

import pytest


@pytest.fixture
def sample_article_html() -> str:
    """Provide sample HTML content matching Jama's article pages.

    Returns:
        A minimal HTML structure for parser testing.
    """
    return """
    <html>
    <head><title>Test Article | Jama Software</title></head>
    <body>
        <div class="flex_cell">Navigation</div>
        <div class="flex_cell">
            <h1>Test Article Title</h1>
            <p>Test content paragraph with <strong>key concept</strong>.</p>
            <h2>Section One</h2>
            <p>Section one content.</p>
            <h2>Section Two</h2>
            <p>Section two content.</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_glossary_html() -> str:
    """Provide sample HTML content matching Jama's glossary page.

    Returns:
        A minimal HTML structure for glossary parser testing.
    """
    return """
    <html>
    <head><title>Glossary | Jama Software</title></head>
    <body>
        <div class="flex_cell">
            <h1>Glossary</h1>
            <dl>
                <dt>Requirements Traceability</dt>
                <dd>The ability to trace requirements through the development lifecycle.</dd>
                <dt>Verification</dt>
                <dd>Ensuring the product is built correctly.</dd>
            </dl>
        </div>
    </body>
    </html>
    """
