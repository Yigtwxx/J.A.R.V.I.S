"""
Shared pytest fixtures for J.A.R.V.I.S backend tests.

Provides:
- In-memory SQLite database + session
- FastAPI TestClient
- Mock service singletons
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.history import SearchHistory  # noqa: F401

# Import all models so Base.metadata knows about all tables
from app.models.profile import Profile  # noqa: F401
from app.models.snapshot import ProfileSnapshot  # noqa: F401

# ---------------------------------------------------------------------------
# Database Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine with all tables.

    Uses StaticPool so all connections share the SAME in-memory database.
    Without this, each new connection would create a separate empty database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Provide a fresh database session, rolled back after each test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def client(db_session):
    """FastAPI TestClient with database dependency overridden."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Mock Services
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ai_service():
    """Mock AIService with common methods."""
    svc = MagicMock()
    svc.generate_response = AsyncMock(return_value="Test AI response about the person.")
    svc.extract_profile_data = AsyncMock(return_value={
        "name": "Test User",
        "description": "A test user",
        "email_addresses": [],
        "similar_profiles": [],
        "cross_validation_issues": [],
        "network_connections": [],
        "estimated_location": "Turkey",
        "capital_city": "Ankara",
        "additional_info": {},
    })
    svc.analyze_sentiment = AsyncMock(return_value={
        "overall_sentiment": "positive",
        "sentiment_score": 0.75,
        "dominant_emotion": "neutral",
        "emotions": {},
    })
    return svc


@pytest.fixture
def mock_github_service():
    """Mock GitHubService."""
    svc = MagicMock()
    svc.search_user.return_value = {
        "login": "testuser",
        "name": "Test User",
        "username": "testuser",
        "profile_url": "https://github.com/testuser",
        "avatar_url": "https://avatars.githubusercontent.com/testuser",
        "bio": "Developer",
        "location": "Istanbul",
        "followers": 100,
        "public_repos": 10,
        "twitter": None,
        "blog": None,
        "last_active": "2026-03-01T10:00:00Z",
    }
    svc.format_github_data.return_value = "GitHub: testuser - Developer"
    return svc


@pytest.fixture
def mock_scraper_service():
    """Mock ScraperService."""
    svc = MagicMock()
    svc.find_all_profiles.return_value = {
        "instagram": [{"url": "https://instagram.com/testuser", "bio": "Test bio"}],
        "twitter": [],
        "linkedin": [],
        "spotify": [],
        "tiktok": [],
        "snapchat": [],
        "tumblr": [],
        "tinder": [],
        "bumble": [],
        "youtube": [],
        "reddit": [],
        "facebook": [],
        "pinterest": [],
        "medium": [],
        "threads": [],
        "steam": [],
        "discord": [],
    }
    svc.format_social_profiles.return_value = "Social media summary for test user."
    svc.extract_phone_numbers.return_value = []
    svc.find_profiles_by_username.return_value = {}
    svc.fetch_avatar_from_url.return_value = None
    return svc


@pytest.fixture
def mock_search_service():
    """Mock SearchService."""
    svc = MagicMock()
    svc.search_person.return_value = (
        None,                         # wiki_image
        "Web results for test user.",  # web_results
        "Deep context content.",       # deep_context
        [{"title": "Result 1", "url": "https://example.com", "snippet": "..."}],  # raw_sources
    )
    return svc


@pytest.fixture
def mock_weather_service():
    """Mock WeatherService."""
    svc = MagicMock()
    svc.get_weather.return_value = {
        "temperature": 15,
        "description": "Partly cloudy",
        "city": "Ankara",
    }
    return svc
