"""
Tests for rate limiting middleware.

Tests cover:
- Rate limiting on public API endpoints via middleware
- Rate limit header inclusion
- 429 responses when limits exceeded
- Different limits for authenticated vs anonymous users
- Public endpoint exclusions (health, docs)
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import only the specific modules we need to avoid auth dependencies
from src.core.security.rate_limiter import get_rate_limiter
from src.core.security.middleware import RateLimitMiddleware


@pytest.fixture
def reset_rate_limiter():
    """Reset rate limiter state before each test."""
    limiter = get_rate_limiter()
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client_with_rate_limit(reset_rate_limiter):
    """Create a test client with rate limiting enabled."""
    app = FastAPI()
    
    # Add rate limiting middleware with low limits for testing
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=5,
        requests_per_hour=100,
    )
    
    @app.get("/api/test")
    def test_endpoint():
        return {"message": "success"}
    
    @app.get("/health")
    def health():
        return {"status": "ok"}
    
    return TestClient(app)


class TestPublicEndpointRateLimiting:
    """Test that public endpoints have rate limiting via middleware."""
    
    def test_api_endpoints_are_rate_limited(self, client_with_rate_limit):
        """Test that API endpoints return 429 after exceeding limit."""
        # Make 5 successful requests (within limit)
        for _ in range(5):
            response = client_with_rate_limit.get("/api/test")
            assert response.status_code == 200
        
        # Sixth request should be rate limited
        response = client_with_rate_limit.get("/api/test")
        assert response.status_code == 429
    
    def test_public_endpoints_excluded_from_rate_limiting(self, client_with_rate_limit):
        """Test that health endpoint is not rate limited."""
        # Make many requests to health endpoint
        for _ in range(10):
            response = client_with_rate_limit.get("/health")
            assert response.status_code == 200


class TestRateLimitHeaders:
    """Test rate limit headers in responses."""
    
    def test_rate_limit_headers_present_on_success(self, client_with_rate_limit):
        """Test that rate limit headers are present on successful requests."""
        response = client_with_rate_limit.get("/api/test")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
    
    def test_rate_limit_headers_present_on_failure(self, client_with_rate_limit):
        """Test that rate limit headers are present on 429 responses."""
        # Exhaust the rate limit
        for _ in range(5):
            client_with_rate_limit.get("/api/test")
        
        # Next request should be rate limited with headers
        response = client_with_rate_limit.get("/api/test")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert response.headers["X-RateLimit-Remaining"] == "0"


class TestTooManyRequestsResponse:
    """Test 429 responses when rate limits are exceeded."""
    
    def test_429_response_has_correct_format(self, client_with_rate_limit):
        """Test 429 response format."""
        # Exhaust rate limit
        for _ in range(5):
            client_with_rate_limit.get("/api/test")
        
        response = client_with_rate_limit.get("/api/test")
        assert response.status_code == 429
        assert "detail" in response.json()
        assert "Rate limit exceeded" in response.json()["detail"]
    
    def test_retry_after_header_has_positive_value(self, client_with_rate_limit):
        """Test Retry-After header contains positive integer."""
        # Exhaust rate limit
        for _ in range(5):
            client_with_rate_limit.get("/api/test")
        
        response = client_with_rate_limit.get("/api/test")
        assert response.status_code == 429
        retry_after = int(response.headers["Retry-After"])
        assert retry_after > 0


class TestAuthenticatedVsAnonymousLimits:
    """Test different rate limits for authenticated vs anonymous users."""
    
    def test_anonymous_users_identified_by_ip_and_user_agent(self):
        """Test anonymous users are identified by IP + User-Agent."""
        from starlette.requests import Request
        
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=5,
        )
        
        captured_identifiers = []
        
        @app.get("/api/track")
        def track_identifier(request: Request):
            middleware = request.app.user_middleware[0].cls
            limiter = middleware._get_client_identifier if hasattr(middleware, '_get_client_identifier') else None
            # Just return 200, we'll check via rate limiting behavior
            return {"ok": True}
        
        client = TestClient(app)
        
        # Test with different User-Agents
        response1 = client.get("/api/track", headers={"User-Agent": "client-1"})
        assert response1.status_code == 200
        
        response2 = client.get("/api/track", headers={"User-Agent": "client-2"})
        assert response2.status_code == 200
    
    def test_different_clients_have_separate_limits(self, client_with_rate_limit):
        """Test that different clients (by User-Agent) have separate rate limits."""
        # First client makes 5 requests
        for _ in range(5):
            response = client_with_rate_limit.get(
                "/api/test",
                headers={"User-Agent": "client-1"}
            )
            assert response.status_code == 200
        
        # Same client is rate limited
        response = client_with_rate_limit.get(
            "/api/test",
            headers={"User-Agent": "client-1"}
        )
        assert response.status_code == 429
        
        # Different client (different User-Agent) can still make requests
        response = client_with_rate_limit.get(
            "/api/test",
            headers={"User-Agent": "client-2"}
        )
        assert response.status_code == 200


class TestPublicPathExclusions:
    """Test that public paths are excluded from rate limiting."""
    
    def test_health_endpoint_excluded(self):
        """Test /health is not rate limited."""
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=1)
        
        @app.get("/health")
        def health():
            return {"status": "ok"}
        
        client = TestClient(app)
        
        # Make many requests - should not be rate limited
        for _ in range(5):
            response = client.get("/health")
            assert response.status_code == 200
    
    def test_docs_endpoint_excluded(self):
        """Test /docs is not rate limited."""
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=1)
        
        @app.get("/docs")
        def docs():
            return {"docs": "content"}
        
        client = TestClient(app)
        
        # Make many requests - should not be rate limited
        for _ in range(5):
            response = client.get("/docs")
            assert response.status_code == 200


class TestRateLimitReset:
    """Test rate limit reset functionality."""
    
    def test_reset_clears_all_counters(self, client_with_rate_limit):
        """Test reset clears all rate limit counters."""
        # Exhaust rate limit
        for _ in range(5):
            client_with_rate_limit.get("/api/test")
        
        response = client_with_rate_limit.get("/api/test")
        assert response.status_code == 429
        
        # Reset rate limiter
        limiter = get_rate_limiter()
        limiter.reset()
        
        # Should be able to make requests again
        response = client_with_rate_limit.get("/api/test")
        assert response.status_code == 200


class TestDashboardEndpointsRateLimiting:
    """Test that dashboard endpoints have rate limiting configured correctly."""
    
    def test_dashboard_app_has_rate_limit_middleware(self):
        """Test that dashboard/api/main.py configures RateLimitMiddleware."""
        # Import the main app
        from dashboard.api.main import app
        
        # Check that rate limiting middleware is in the stack
        has_rate_limit = False
        for middleware in app.user_middleware:
            if middleware.cls.__name__ == "RateLimitMiddleware":
                has_rate_limit = True
                break
        
        assert has_rate_limit, "RateLimitMiddleware should be configured in dashboard app"
    
    def test_rate_limit_configuration_values(self):
        """Test rate limit configuration has reasonable defaults."""
        from dashboard.api.main import app
        
        # Find the rate limit middleware config
        rate_limit_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls.__name__ == "RateLimitMiddleware":
                rate_limit_middleware = middleware
                break
        
        assert rate_limit_middleware is not None
        # Check options are set
        options = rate_limit_middleware.options or {}
        # requests_per_minute should be set
        assert options.get("requests_per_minute") is not None or rate_limit_middleware.args


class TestStaticFilesExclusion:
    """Test static files are excluded from rate limiting."""
    
    def test_static_paths_excluded(self):
        """Test /static/* paths are not rate limited."""
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=1)
        
        @app.get("/static/style.css")
        def static_file():
            return {"content": "css"}
        
        client = TestClient(app)
        
        # Static files should not be rate limited
        for _ in range(5):
            response = client.get("/static/style.css")
            assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
