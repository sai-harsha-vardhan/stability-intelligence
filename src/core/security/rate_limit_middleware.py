"""
Rate Limiting Middleware for FastAPI.

Provides global rate limiting for all API requests with support for:
- Per-client rate limits (authenticated users vs anonymous)
- Sliding window counter for per-minute and per-hour limits
- Public path exclusions (health, docs, static files)
- Rate limit headers in responses
- Configurable limits per endpoint

Usage:
    from src.core.security.rate_limit_middleware import RateLimitMiddleware
    
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=120,
        requests_per_hour=3600,
    )
"""

import json
from typing import Optional, Callable, Set
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from rate_limiter import get_rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global rate limiting middleware for all API requests.
    
    Applies rate limiting to all non-public paths. Public paths
    (health, docs) are excluded.
    
    Usage:
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=120,
            requests_per_hour=3600,
        )
    """
    
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
    
    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        public_paths: Optional[Set[str]] = None,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.public_paths = public_paths or self.PUBLIC_PATHS
        
        # Initialize rate limiter
        self.limiter = get_rate_limiter()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting."""
        path = request.url.path
        
        # Skip rate limiting for public paths
        if path in self.public_paths or path.startswith("/static/"):
            return await call_next(request)
        
        # Get client identifier
        client_id = self._get_client_identifier(request)
        resource = path.replace("/", "_").strip("_") or "api"
        
        # Check rate limits using token bucket
        if self.requests_per_minute:
            key = f"{client_id}:{resource}:minute"
            result = self.limiter.check_rate_limit(
                key=key,
                limit=self.requests_per_minute,
                cost=1,
            )
            
            if not result.allowed:
                retry_after = result.retry_after or 60
                return Response(
                    status_code=429,
                    content=json.dumps({"detail": "Rate limit exceeded. Too many requests per minute."}),
                    media_type="application/json",
                    headers={
                        "Retry-After": str(int(retry_after)),
                        "X-RateLimit-Limit": str(self.requests_per_minute),
                        "X-RateLimit-Remaining": "0",
                    },
                )
        
        # Process the request
        response = await call_next(request)
        
        # Add rate limit headers to successful response
        if self.requests_per_minute:
            key = f"{client_id}:{resource}:minute"
            result = self.limiter.check_rate_limit(key=key, limit=self.requests_per_minute)
            response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        
        return response
    
    def _get_client_identifier(self, request: Request) -> str:
        """Generate a unique identifier for rate limiting.
        
        Uses authenticated user ID if available, falls back to IP + User-Agent.
        """
        # Try to get authenticated user from scope
        user = getattr(request.state, "user", None)
        if user and user != "anonymous":
            if isinstance(user, dict):
                user_id = user.get("id", user.get("sub"))
                if user_id:
                    return f"user:{user_id}"
            elif hasattr(user, "id"):
                return f"user:{user.id}"
            else:
                return f"user:{user}"
        
        # Fallback: use IP address + User-Agent for anonymous clients
        client_host = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")
        
        # Simple hash-based identifier for anonymous clients
        import hashlib
        identifier = hashlib.sha256(
            f"{client_host}:{user_agent}".encode()
        ).hexdigest()[:16]
        
        return f"anon:{identifier}"
