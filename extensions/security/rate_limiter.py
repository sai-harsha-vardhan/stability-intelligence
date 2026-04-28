"""
Rate limiting middleware and utilities for the Paperclip Dashboard API.

Provides per-client rate limiting with configurable limits for authenticated
vs anonymous users. Uses in-memory storage with sliding window algorithm.
"""

import functools
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 60
    burst_size: int = 10


@dataclass
class RateLimitEntry:
    """Tracks request timestamps for a single client."""

    timestamps: list[float] = field(default_factory=list)


class RateLimiter:
    """
    In-memory rate limiter using sliding window algorithm.

    Tracks requests per client (identified by IP + optional auth token).
    Automatically cleans up old entries on each check.
    """

    def __init__(self):
        self._storage: dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)
        self._anonymous_config = RateLimitConfig(
            requests_per_minute=30,
            burst_size=5,
        )
        self._authenticated_config = RateLimitConfig(
            requests_per_minute=120,
            burst_size=20,
        )
        self._window_seconds = 60.0  # 1 minute window

    def _get_client_key(self, request: Request) -> str:
        """Generate a unique key for the client."""
        client_ip = request.client.host if request.client else "unknown"

        # Check for auth token in header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            # Use hashed token as part of key for authenticated users
            token = auth_header[7:]
            return f"auth:{hash(token)}:{client_ip}"

        return f"anon:{client_ip}"

    def _is_authenticated(self, request: Request) -> bool:
        """Check if request has authentication."""
        auth_header = request.headers.get("authorization", "")
        return auth_header.startswith("Bearer ")

    def _get_config(self, request: Request) -> RateLimitConfig:
        """Get appropriate config based on authentication status."""
        if self._is_authenticated(request):
            return self._authenticated_config
        return self._anonymous_config

    def _clean_old_entries(self, entry: RateLimitEntry, now: float) -> None:
        """Remove timestamps older than the window."""
        cutoff = now - self._window_seconds
        entry.timestamps = [ts for ts in entry.timestamps if ts > cutoff]

    def check_rate_limit(self, request: Request) -> tuple[bool, dict]:
        """
        Check if request is within rate limits.

        Returns:
            Tuple of (allowed: bool, headers: dict)
            Headers include X-RateLimit-Limit, X-RateLimit-Remaining,
            X-RateLimit-Reset, and Retry-After (if limited).
        """
        client_key = self._get_client_key(request)
        config = self._get_config(request)
        now = time.time()

        entry = self._storage[client_key]
        self._clean_old_entries(entry, now)

        # Count requests in window
        request_count = len(entry.timestamps)
        remaining = max(0, config.requests_per_minute - request_count)

        # Calculate reset time (when oldest entry expires)
        if entry.timestamps:
            reset_time = int(min(entry.timestamps) + self._window_seconds)
        else:
            reset_time = int(now + self._window_seconds)

        headers = {
            "X-RateLimit-Limit": str(config.requests_per_minute),
            "X-RateLimit-Remaining": str(remaining - 1 if remaining > 0 else 0),
            "X-RateLimit-Reset": str(reset_time),
        }

        # Check burst limit
        if request_count >= config.burst_size:
            # Check if we're still within the rate limit
            if request_count >= config.requests_per_minute:
                headers["Retry-After"] = str(int(reset_time - now))
                return False, headers

        # Record this request
        entry.timestamps.append(now)
        return True, headers


# Global rate limiter instance
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return _rate_limiter


def rate_limit() -> Callable:
    """
    Decorator to apply rate limiting to a FastAPI endpoint.

    Usage:
        @app.get("/api/endpoint")
        @rate_limit()
        async def my_endpoint(request: Request):
            return {"data": "value"}
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract Request object from args/kwargs
            request = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                raise HTTPException(
                    status_code=500,
                    detail="Request object not found for rate limiting",
                )

            limiter = get_rate_limiter()
            allowed, headers = limiter.check_rate_limit(request)

            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please try again later.",
                    headers=headers,
                )

            # Call the original function
            result = await func(*args, **kwargs)

            # Add rate limit headers to response
            if hasattr(result, "headers"):
                result.headers.update(headers)
            elif isinstance(result, dict):
                # FastAPI will convert dict to JSONResponse
                # Headers need to be set differently
                from fastapi.responses import JSONResponse

                return JSONResponse(content=result, headers=headers)

            return result

        return wrapper

    return decorator


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to apply rate limiting globally to all requests.

    This is an alternative to the decorator approach for applying
    rate limiting to all endpoints automatically.
    """

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        limiter = get_rate_limiter()
        allowed, headers = limiter.check_rate_limit(request)

        if not allowed:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers=headers,
            )

        response = await call_next(request)

        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = value

        return response


def check_rate_limit(request: Request) -> tuple[bool, dict]:
    """
    Check rate limit for a request.

    This is the standalone function mentioned in requirements.
    Can be used directly or via the decorator.

    Returns:
        Tuple of (allowed: bool, headers: dict)
    """
    limiter = get_rate_limiter()
    return limiter.check_rate_limit(request)
