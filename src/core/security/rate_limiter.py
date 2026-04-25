"""
Rate Limiting Module.

Provides rate limiting for:
- Per-user query limits (prevent abuse)
- Per-session token usage caps (prevent cost runaway)
- Per-endpoint throttling

Storage backends:
- In-memory (single instance)
- Redis (distributed)

Configuration:
    RATE_LIMIT_STORAGE=memory|redis
    REDIS_URL=redis://localhost:6379/0
    DEFAULT_RATE_LIMIT_PER_MINUTE=60
    TOKEN_BUDGET_PER_HOUR=10000
"""

import os
import time
from typing import Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field
from functools import wraps
from collections import defaultdict
import threading

from fastapi import Request, HTTPException, status


# ============================================================================
# Configuration
# ============================================================================

RATE_LIMIT_STORAGE = os.getenv("RATE_LIMIT_STORAGE", "memory")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_RATE_LIMIT_PER_MINUTE = int(os.getenv("DEFAULT_RATE_LIMIT_PER_MINUTE", "60"))
TOKEN_BUDGET_PER_HOUR = int(os.getenv("TOKEN_BUDGET_PER_HOUR", "10000"))
BURST_SIZE = int(os.getenv("RATE_LIMIT_BURST_SIZE", "10"))


# ============================================================================
# Rate Limit Data Structures
# ============================================================================

@dataclass
class RateLimitState:
    """Internal state for a rate limit bucket."""
    tokens: float
    last_update: float
    request_count: int = 0
    token_usage: int = 0


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    remaining: int
    reset_time: float
    limit: int
    retry_after: Optional[float] = None
    reason: Optional[str] = None


# ============================================================================
# Storage Backends
# ============================================================================

class RateLimitStorage:
    """Abstract base for rate limit storage."""
    
    def get_bucket(self, key: str) -> Optional[RateLimitState]:
        raise NotImplementedError
    
    def set_bucket(self, key: str, state: RateLimitState) -> None:
        raise NotImplementedError
    
    def increment(self, key: str, amount: int = 1) -> int:
        raise NotImplementedError


class MemoryStorage(RateLimitStorage):
    """In-memory rate limit storage (thread-safe)."""
    
    def __init__(self):
        self._buckets: Dict[str, RateLimitState] = {}
        self._counters: Dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()
    
    def get_bucket(self, key: str) -> Optional[RateLimitState]:
        with self._lock:
            return self._buckets.get(key)
    
    def set_bucket(self, key: str, state: RateLimitState) -> None:
        with self._lock:
            self._buckets[key] = state
    
    def increment(self, key: str, amount: int = 1) -> int:
        with self._lock:
            self._counters[key] += amount
            return self._counters[key]
    
    def cleanup(self, max_age_seconds: int = 3600):
        """Remove stale buckets."""
        cutoff = time.time() - max_age_seconds
        with self._lock:
            stale_keys = [
                k for k, v in self._buckets.items()
                if v.last_update < cutoff
            ]
            for k in stale_keys:
                del self._buckets[k]
                del self._counters[k]


class RedisStorage(RateLimitStorage):
    """Redis-backed rate limit storage (for distributed deployments)."""
    
    def __init__(self, url: str):
        self._url = url
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                import redis
                self._client = redis.from_url(self._url)
            except ImportError:
                raise RuntimeError("redis package required. Install: pip install redis")
        return self._client
    
    def get_bucket(self, key: str) -> Optional[RateLimitState]:
        client = self._get_client()
        data = client.hgetall(f"ratelimit:{key}")
        if not data:
            return None
        return RateLimitState(
            tokens=float(data.get(b"tokens", 0)),
            last_update=float(data.get(b"last_update", 0)),
            request_count=int(data.get(b"request_count", 0)),
            token_usage=int(data.get(b"token_usage", 0)),
        )
    
    def set_bucket(self, key: str, state: RateLimitState) -> None:
        client = self._get_client()
        pipe = client.pipeline()
        bucket_key = f"ratelimit:{key}"
        pipe.hset(bucket_key, mapping={
            "tokens": state.tokens,
            "last_update": state.last_update,
            "request_count": state.request_count,
            "token_usage": state.token_usage,
        })
        pipe.expire(bucket_key, 3600)  # Expire after 1 hour
        pipe.execute()
    
    def increment(self, key: str, amount: int = 1) -> int:
        client = self._get_client()
        counter_key = f"ratelimit_counter:{key}"
        return client.incrby(counter_key, amount)


# ============================================================================
# Rate Limiter Implementation
# ============================================================================

class RateLimiter:
    """
    Token bucket rate limiter.
    
    Supports:
    - Per-minute request limits
    - Burst allowance
    - Token usage budgets (for LLM cost control)
    - Multiple window sizes
    """
    
    def __init__(
        self,
        storage: Optional[RateLimitStorage] = None,
        default_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
        burst_size: int = BURST_SIZE,
    ):
        if storage is None:
            if RATE_LIMIT_STORAGE == "redis":
                storage = RedisStorage(REDIS_URL)
            else:
                storage = MemoryStorage()
        
        self.storage = storage
        self.default_limit = default_limit_per_minute
        self.burst_size = burst_size
        self.token_budget_per_hour = TOKEN_BUDGET_PER_HOUR
    
    def check_rate_limit(
        self,
        key: str,
        limit: Optional[int] = None,
        cost: int = 1,
    ) -> RateLimitResult:
        """
        Check if request is within rate limit.
        
        Args:
            key: Unique identifier (user ID, session ID, IP)
            limit: Max requests per minute (uses default if None)
            cost: Token cost of this request (for weighted limiting)
        
        Returns:
            RateLimitResult with allowed status and metadata
        """
        limit = limit or self.default_limit
        now = time.time()
        
        # Get or create bucket
        bucket = self.storage.get_bucket(key)
        if bucket is None:
            bucket = RateLimitState(
                tokens=self.burst_size,
                last_update=now,
            )
        
        # Calculate tokens to add based on time elapsed
        time_passed = now - bucket.last_update
        tokens_to_add = time_passed * (limit / 60.0)  # Tokens per second
        bucket.tokens = min(bucket.tokens + tokens_to_add, self.burst_size)
        bucket.last_update = now
        
        # Check if request can be accommodated
        if bucket.tokens >= cost:
            bucket.tokens -= cost
            bucket.request_count += 1
            self.storage.set_bucket(key, bucket)
            
            return RateLimitResult(
                allowed=True,
                remaining=int(bucket.tokens),
                reset_time=now + (60 / limit) * (self.burst_size - bucket.tokens),
                limit=limit,
            )
        else:
            # Request denied
            retry_after = (cost - bucket.tokens) / (limit / 60.0)
            self.storage.set_bucket(key, bucket)
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=now + retry_after,
                limit=limit,
                retry_after=retry_after,
                reason="Rate limit exceeded",
            )
    
    def check_token_budget(
        self,
        key: str,
        tokens_requested: int,
        budget_per_hour: Optional[int] = None,
    ) -> RateLimitResult:
        """
        Check token usage against hourly budget.
        
        Used for LLM API cost control.
        """
        budget = budget_per_hour or self.token_budget_per_hour
        now = time.time()
        window_start = now - 3600  # 1 hour ago
        
        # Get bucket
        bucket = self.storage.get_bucket(f"{key}:tokens")
        if bucket is None or bucket.last_update < window_start:
            # Reset for new window
            bucket = RateLimitState(
                tokens=budget,
                last_update=now,
                token_usage=0,
            )
        
        # Check remaining budget
        remaining_budget = budget - bucket.token_usage
        
        if tokens_requested <= remaining_budget:
            bucket.token_usage += tokens_requested
            bucket.last_update = now
            self.storage.set_bucket(key, bucket)
            
            return RateLimitResult(
                allowed=True,
                remaining=remaining_budget - tokens_requested,
                reset_time=window_start + 3600,
                limit=budget,
            )
        else:
            return RateLimitResult(
                allowed=False,
                remaining=remaining_budget,
                reset_time=window_start + 3600,
                limit=budget,
                reason=f"Token budget exhausted. Requested: {tokens_requested}, Remaining: {remaining_budget}",
            )
    
    def get_usage_stats(self, key: str) -> Dict:
        """Get current usage statistics for a key."""
        bucket = self.storage.get_bucket(key)
        token_bucket = self.storage.get_bucket(f"{key}:tokens")
        
        return {
            "requests_last_minute": bucket.request_count if bucket else 0,
            "tokens_remaining": self.token_budget_per_hour - (token_bucket.token_usage if token_bucket else 0),
            "tokens_used_this_hour": token_bucket.token_usage if token_bucket else 0,
            "current_tokens": bucket.tokens if bucket else self.burst_size,
        }


# ============================================================================
# Global Instance
# ============================================================================

_limiter_instance: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _limiter_instance
    if _limiter_instance is None:
        _limiter_instance = RateLimiter()
    return _limiter_instance


def rate_limit(
    key_func: Optional[Callable] = None,
    limit: Optional[int] = None,
    cost: int = 1,
):
    """
    Decorator to apply rate limiting to a function.
    
    Usage:
        @rate_limit(key_func=lambda: request.state.user_id, limit=100)
        def expensive_operation():
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # Default to function name
                key = f"func:{func.__module__}.{func.__name__}"
            
            result = limiter.check_rate_limit(key, limit, cost)
            
            if not result.allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=result.reason,
                    headers={"Retry-After": str(int(result.retry_after or 60))},
                )
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================================
# FastAPI Dependencies
# ============================================================================

async def rate_limit_dependency(
    request: Request,
    limit: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
) -> None:
    """
    FastAPI dependency for rate limiting.
    
    Usage:
        @app.get("/api/items")
        async def list_items(_: None = Depends(rate_limit_dependency)):
            pass
    """
    limiter = get_rate_limiter()
    
    # Determine key from request
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        key = f"user:{user_id}"
    else:
        # Fall back to IP address
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            key = f"ip:{forwarded_for.split(',')[0].strip()}"
        else:
            key = f"ip:{request.client.host if request.client else 'unknown'}"
    
    result = limiter.check_rate_limit(key, limit)
    
    # Add rate limit headers
    request.state.rate_limit_remaining = result.remaining
    request.state.rate_limit_reset = result.reset_time
    
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result.reason,
            headers={
                "Retry-After": str(int(result.retry_after or 60)),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(result.reset_time)),
            },
        )


async def token_budget_dependency(
    request: Request,
    estimated_tokens: int = 1000,
) -> None:
    """
    FastAPI dependency for LLM token budgeting.
    """
    limiter = get_rate_limiter()
    
    user_id = getattr(request.state, "user_id", "anonymous")
    key = f"user:{user_id}"
    
    result = limiter.check_token_budget(key, estimated_tokens)
    
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Token budget exceeded: {result.reason}",
            headers={
                "X-TokenBudget-Limit": str(result.limit),
                "X-TokenBudget-Remaining": str(result.remaining),
            },
        )
