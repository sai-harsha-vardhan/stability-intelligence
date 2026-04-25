"""Shared test fixtures and mocks for Stability Intelligence System."""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_graph_client():
    """Create a mocked Neo4j graph client."""
    client = Mock()
    client.read.return_value = []
    client.write.return_value = []
    client.health_check.return_value = {"status": "healthy", "components": []}
    return client


@pytest.fixture
def mock_neo4j_driver():
    """Create a mocked Neo4j driver."""
    driver = Mock()
    driver.session.return_value.__enter__ = Mock(return_value=MagicMock())
    driver.session.return_value.__exit__ = Mock(return_value=False)
    return driver


@pytest.fixture
def sample_issue_data():
    """Return sample GitHub issue data for tests."""
    return {
        "number": 123,
        "title": "Test Issue",
        "body": "This is a test issue body",
        "state": "closed",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "closed_at": "2024-01-02T00:00:00Z",
        "labels": [{"name": "rca-discussed"}],
        "user": {"login": "testuser"},
        "assignees": [],
        "comments": 5,
    }


@pytest.fixture
def sample_rca_issue():
    """Return sample RCA issue data."""
    return {
        "number": 456,
        "title": "[RCA] Payment failure investigation",
        "body": """## Summary
Payment failures observed in production.

## Root Cause
Database connection pool exhaustion.

## Action Items
- Increase connection pool size
- Add alerting
""",
        "state": "closed",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-03T00:00:00Z",
        "labels": [{"name": "rca-discussed"}, {"name": "severity:high"}],
        "user": {"login": "oncall-engineer"},
    }


@pytest.fixture
def mock_litellm_response():
    """Return a mocked LiteLLM API response."""
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": int(datetime.utcnow().timestamp()),
        "model": "claude-3-opus",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response from the LLM.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


@pytest.fixture
def sample_pattern_cluster():
    """Return sample pattern cluster data."""
    return {
        "id": "cluster-abc123",
        "name": "Database Connection Failures",
        "description": "Recurring database connection timeout incidents",
        "frequency": 5,
        "trend": "worsening",
        "keywords": ["database", "connection", "timeout"],
    }


@pytest.fixture
def sample_strategy():
    """Return sample strategy data."""
    return {
        "id": "strat-def456",
        "title": "Increase Connection Pool Size",
        "description": "Auto-generated strategy to address database connection timeouts",
        "strategy_type": "automated_regression_suite",
        "pattern_cluster_id": "cluster-abc123",
        "estimated_reduction_percent": 30.0,
        "status": "proposed",
        "forward_score": 5,
        "backward_score": 5,
        "blocking_multiplier": 1.5,
        "priority_score": 3.75,
    }


@pytest.fixture
def sample_action_item():
    """Return sample action item data."""
    return {
        "id": "action-ghi789",
        "issue_number": 456,
        "repository": "juspay/hyperswitch",
        "title": "Increase connection pool size",
        "description": "Add more connections to the pool",
        "status": "completed",
        "priority": "high",
        "created_at": "2024-01-01T00:00:00Z",
        "resolved_at": "2024-01-03T00:00:00Z",
        "resolution_verified": True,
        "related_incidents_after": [],
    }


@pytest.fixture(autouse=True)
def reset_graph_client_singleton():
    """Reset the graph client singleton between tests."""
    # Import here to avoid circular imports
    import graph.client as client_module
    original_client = client_module._client
    client_module._client = None
    yield
    client_module._client = original_client


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables for testing."""
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "testpassword")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_API_KEY", "test-api-key")
    monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
    monkeypatch.setenv("GITHUB_REPO", "test/repo")


@pytest.fixture
def patch_graph_client(mock_graph_client):
    """Patch the graph client with a mock."""
    with patch("graph.client.get_client", return_value=mock_graph_client):
        yield mock_graph_client


@pytest.fixture
def patch_neo4j_driver(mock_neo4j_driver):
    """Patch the Neo4j driver with a mock."""
    with patch("graph.client.GraphDatabase.driver", return_value=mock_neo4j_driver):
        yield mock_neo4j_driver


@pytest.fixture
def mock_httpx_post(mock_litellm_response):
    """Mock httpx.post for LiteLLM calls."""
    with patch("httpx.post") as mock:
        response = Mock()
        response.json.return_value = mock_litellm_response
        response.raise_for_status.return_value = None
        mock.return_value = response
        yield mock


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory for tests."""
    cache_dir = tmp_path / "github-cache"
    cache_dir.mkdir()
    return cache_dir
