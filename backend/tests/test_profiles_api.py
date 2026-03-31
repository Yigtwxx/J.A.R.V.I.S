"""
Tests for the Profiles API endpoints.

Covers: CRUD operations for /api/profiles/*
"""



class TestCreateProfile:
    """POST /api/profiles/"""

    def test_create_profile_success(self, client):
        payload = {
            "name": "Test User",
            "github_url": "https://github.com/testuser",
            "description": "A developer",
        }
        response = client.post("/api/profiles/", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test User"
        assert data["github_url"] == "https://github.com/testuser"
        assert data["id"] is not None
        assert data["created_at"] is not None

    def test_create_profile_minimal(self, client):
        """Only name is required."""
        response = client.post("/api/profiles/", json={"name": "Minimal"})
        assert response.status_code == 200
        assert response.json()["name"] == "Minimal"
        assert response.json()["github_url"] is None

    def test_create_profile_all_fields(self, client):
        """Ensure all social media URL fields are persisted."""
        payload = {
            "name": "Full Profile",
            "github_url": "https://github.com/full",
            "instagram_url": "https://instagram.com/full",
            "twitter_url": "https://x.com/full",
            "linkedin_url": "https://linkedin.com/in/full",
            "spotify_url": "https://open.spotify.com/user/full",
            "tiktok_url": "https://tiktok.com/@full",
            "snapchat_url": "https://snapchat.com/add/full",
            "tumblr_url": "https://full.tumblr.com",
            "youtube_url": "https://youtube.com/@full",
            "reddit_url": "https://reddit.com/user/full",
            "facebook_url": "https://facebook.com/full",
            "pinterest_url": "https://pinterest.com/full",
            "medium_url": "https://medium.com/@full",
            "threads_url": "https://threads.net/@full",
            "steam_url": "https://steamcommunity.com/id/full",
            "tinder_mention": "Mentioned on Tinder",
            "bumble_mention": "Mentioned on Bumble",
            "discord_mention": "full#1234",
            "phone_numbers": ["+1234567890"],
            "description": "A full profile test",
            "email_addresses": ["full@example.com"],
        }
        response = client.post("/api/profiles/", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["pinterest_url"] == "https://pinterest.com/full"
        assert data["medium_url"] == "https://medium.com/@full"
        assert data["threads_url"] == "https://threads.net/@full"
        assert data["steam_url"] == "https://steamcommunity.com/id/full"
        assert data["discord_mention"] == "full#1234"

    def test_create_profile_missing_name(self, client):
        """Name is required — should fail validation."""
        response = client.post("/api/profiles/", json={"github_url": "https://github.com/x"})
        assert response.status_code == 422  # Pydantic validation error


class TestGetProfiles:
    """GET /api/profiles/"""

    def test_get_all_empty(self, client):
        response = client.get("/api/profiles/")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_all_returns_created(self, client):
        client.post("/api/profiles/", json={"name": "User A"})
        client.post("/api/profiles/", json={"name": "User B"})
        response = client.get("/api/profiles/")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_pagination(self, client):
        for i in range(5):
            client.post("/api/profiles/", json={"name": f"User {i}"})
        response = client.get("/api/profiles/?skip=2&limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2


class TestGetProfileById:
    """GET /api/profiles/{id}"""

    def test_get_existing(self, client):
        create_resp = client.post("/api/profiles/", json={"name": "Found User"})
        pid = create_resp.json()["id"]
        response = client.get(f"/api/profiles/{pid}")
        assert response.status_code == 200
        assert response.json()["name"] == "Found User"

    def test_get_nonexistent(self, client):
        response = client.get("/api/profiles/9999")
        assert response.status_code == 404


class TestDeleteProfile:
    """DELETE /api/profiles/{id}"""

    def test_delete_existing(self, client):
        create_resp = client.post("/api/profiles/", json={"name": "To Delete"})
        pid = create_resp.json()["id"]
        response = client.delete(f"/api/profiles/{pid}")
        assert response.status_code == 200

        # Verify deletion
        get_resp = client.get(f"/api/profiles/{pid}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent(self, client):
        response = client.delete("/api/profiles/9999")
        assert response.status_code == 404


class TestSearchByName:
    """GET /api/profiles/search/{name}"""

    def test_search_found(self, client):
        client.post("/api/profiles/", json={"name": "John Doe"})
        client.post("/api/profiles/", json={"name": "Jane Smith"})
        response = client.get("/api/profiles/search/John")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "John Doe"

    def test_search_case_insensitive(self, client):
        client.post("/api/profiles/", json={"name": "John Doe"})
        response = client.get("/api/profiles/search/john")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_search_no_results(self, client):
        response = client.get("/api/profiles/search/Nonexistent")
        assert response.status_code == 200
        assert response.json() == []
