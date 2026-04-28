"""
Token Budgeting Middleware for Analytics Features

Implements rate limiting based on token consumption to prevent
excessive LLM API costs during analytics operations.
"""

from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio

class TokenBudgetManager:
    """Manages token budgets for analytics features"""
    
    def __init__(self):
        self.budgets: Dict[str, Dict] = {}
        self.default_daily_limit = 100000  # 100k tokens per day per feature
        self.default_hourly_limit = 10000   # 10k tokens per hour per feature
        
    def initialize_feature(self, feature_name: str, 
                          daily_limit: Optional[int] = None,
                          hourly_limit: Optional[int] = None):
        """Initialize budget tracking for a feature"""
        self.budgets[feature_name] = {
            'daily_limit': daily_limit or self.default_daily_limit,
            'hourly_limit': hourly_limit or self.default_hourly_limit,
            'daily_used': 0,
            'hourly_used': 0,
            'daily_reset': datetime.now() + timedelta(days=1),
            'hourly_reset': datetime.now() + timedelta(hours=1),
            'total_calls': 0,
            'total_tokens': 0
        }
    
    def reset_if_needed(self, feature_name: str):
        """Reset counters if time window has passed"""
        if feature_name not in self.budgets:
            self.initialize_feature(feature_name)
            
        budget = self.budgets[feature_name]
        now = datetime.now()
        
        if now >= budget['daily_reset']:
            budget['daily_used'] = 0
            budget['daily_reset'] = now + timedelta(days=1)
            
        if now >= budget['hourly_reset']:
            budget['hourly_used'] = 0
            budget['hourly_reset'] = now + timedelta(hours=1)
    
    def check_budget(self, feature_name: str, estimated_tokens: int) -> tuple[bool, str]:
        """
        Check if feature has budget for estimated tokens
        
        Returns:
            (allowed, reason) - allowed is True if within budget
        """
        self.reset_if_needed(feature_name)
        budget = self.budgets[feature_name]
        
        # Check hourly limit
        if budget['hourly_used'] + estimated_tokens > budget['hourly_limit']:
            remaining_time = (budget['hourly_reset'] - datetime.now()).total_seconds() / 60
            return False, f"Hourly token limit exceeded. Resets in {remaining_time:.0f} minutes"
        
        # Check daily limit
        if budget['daily_used'] + estimated_tokens > budget['daily_limit']:
            remaining_time = (budget['daily_reset'] - datetime.now()).total_seconds() / 3600
            return False, f"Daily token limit exceeded. Resets in {remaining_time:.1f} hours"
        
        return True, "OK"
    
    def consume_tokens(self, feature_name: str, tokens_used: int):
        """Record token consumption for a feature"""
        self.reset_if_needed(feature_name)
        budget = self.budgets[feature_name]
        
        budget['daily_used'] += tokens_used
        budget['hourly_used'] += tokens_used
        budget['total_tokens'] += tokens_used
        budget['total_calls'] += 1
    
    def get_budget_status(self, feature_name: str) -> Dict:
        """Get current budget status for a feature"""
        self.reset_if_needed(feature_name)
        budget = self.budgets[feature_name]
        
        return {
            'feature': feature_name,
            'hourly': {
                'limit': budget['hourly_limit'],
                'used': budget['hourly_used'],
                'remaining': budget['hourly_limit'] - budget['hourly_used'],
                'reset_in_minutes': (budget['hourly_reset'] - datetime.now()).total_seconds() / 60
            },
            'daily': {
                'limit': budget['daily_limit'],
                'used': budget['daily_used'],
                'remaining': budget['daily_limit'] - budget['daily_used'],
                'reset_in_hours': (budget['daily_reset'] - datetime.now()).total_seconds() / 3600
            },
            'total_calls': budget['total_calls'],
            'total_tokens': budget['total_tokens']
        }
    
    def get_all_budgets(self) -> Dict:
        """Get budget status for all features"""
        return {
            feature: self.get_budget_status(feature)
            for feature in self.budgets.keys()
        }


# Global instance
token_budget = TokenBudgetManager()

# Initialize budgets for analytics features
token_budget.initialize_feature('rca_analysis', daily_limit=50000, hourly_limit=5000)
token_budget.initialize_feature('pattern_detection', daily_limit=30000, hourly_limit=3000)
token_budget.initialize_feature('impact_analysis', daily_limit=20000, hourly_limit=2000)
token_budget.initialize_feature('dashboard_insights', daily_limit=10000, hourly_limit=1000)


def require_token_budget(feature_name: str, estimated_tokens: int = 1000):
    """
    Decorator to enforce token budgets on endpoints
    
    Usage:
        @require_token_budget('rca_analysis', estimated_tokens=2000)
        async def analyze_rca(request):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Check budget
            allowed, reason = token_budget.check_budget(feature_name, estimated_tokens)
            
            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429,
                    detail={
                        'error': 'Token budget exceeded',
                        'reason': reason,
                        'feature': feature_name,
                        'budget_status': token_budget.get_budget_status(feature_name)
                    }
                )
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Record token usage (use actual if available, otherwise estimated)
            actual_tokens = estimated_tokens
            if isinstance(result, dict) and 'token_usage' in result:
                actual_tokens = result['token_usage']
            
            token_budget.consume_tokens(feature_name, actual_tokens)
            
            return result
        
        return wrapper
    return decorator


# Usage example:
"""
from src.token_budget import require_token_budget, token_budget

@app.get("/api/analyze")
@require_token_budget('rca_analysis', estimated_tokens=2000)
async def analyze_endpoint(query: str):
    # Your analysis code here
    result = perform_analysis(query)
    
    # Optionally include actual token count in result
    result['token_usage'] = 1500  # actual tokens used
    
    return result

@app.get("/api/token-budgets")
async def get_token_budgets():
    return token_budget.get_all_budgets()
"""
