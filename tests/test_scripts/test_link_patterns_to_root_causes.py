"""Unit tests for link_patterns_to_root_causes.py script."""

from unittest.mock import MagicMock, patch
import pytest

from scripts.link_patterns_to_root_causes import (
    calculate_link_strength,
    fetch_pattern_clusters,
    fetch_root_causes,
    find_linked_incidents,
    get_neo4j_driver,
    link_patterns_to_root_causes,
    verify_link_integrity,
)


class TestFetchPatternClusters:
    """Test PatternCluster fetching."""

    def test_fetch_single_cluster(self):
        """Test fetching a single PatternCluster."""
        mock_tx = MagicMock()
        mock_result = [
            {
                "id": "pc_test123",
                "signature": "resource_exhaustion",
                "category": "performance",
                "severity": "high",
                "keywords": ["timeout", "cpu", "memory"],
            }
        ]
        mock_tx.run.return_value = mock_result

        result = fetch_pattern_clusters(mock_tx)

        assert len(result) == 1
        assert result[0]["id"] == "pc_test123"
        assert result[0]["signature"] == "resource_exhaustion"
        assert result[0]["category"] == "performance"

    def test_fetch_multiple_clusters(self):
        """Test fetching multiple PatternClusters."""
        mock_tx = MagicMock()
        mock_result = [
            {
                "id": f"pc_{i}",
                "signature": f"pattern_{i}",
                "category": "test",
                "severity": "low",
                "keywords": ["test"],
            }
            for i in range(5)
        ]
        mock_tx.run.return_value = mock_result

        result = fetch_pattern_clusters(mock_tx)

        assert len(result) == 5
        for i, cluster in enumerate(result):
            assert cluster["id"] == f"pc_{i}"

    def test_handles_null_keywords(self):
        """Test that null keywords are handled gracefully."""
        mock_tx = MagicMock()
        mock_result = [
            {
                "id": "pc_test",
                "signature": "test",
                "category": "test",
                "severity": "low",
                "keywords": None,
            }
        ]
        mock_tx.run.return_value = mock_result

        result = fetch_pattern_clusters(mock_tx)

        assert len(result) == 1
        assert result[0]["keywords"] == []


class TestFetchRootCauses:
    """Test RootCause fetching."""

    def test_fetch_single_root_cause(self):
        """Test fetching a single RootCause."""
        mock_tx = MagicMock()
        mock_result = [
            {
                "id": "rc_test123",
                "description": "Timeout error in service",
                "category": "performance",
                "mechanism": "timeout",
                "confidence": 0.85,
            }
        ]
        mock_tx.run.return_value = mock_result

        result = fetch_root_causes(mock_tx)

        assert len(result) == 1
        assert result[0]["id"] == "rc_test123"
        assert result[0]["description"] == "Timeout error in service"
        assert result[0]["confidence"] == 0.85

    def test_fetch_multiple_root_causes(self):
        """Test fetching multiple RootCauses."""
        mock_tx = MagicMock()
        mock_result = [
            {
                "id": f"rc_{i}",
                "description": f"Root cause {i}",
                "category": "test",
                "mechanism": "unknown",
                "confidence": None,
            }
            for i in range(5)
        ]
        mock_tx.run.return_value = mock_result

        result = fetch_root_causes(mock_tx)

        assert len(result) == 5
        # Default confidence should be 0.8 when null
        assert result[0]["confidence"] == 0.8


class TestFindLinkedIncidents:
    """Test finding incidents that link patterns and root causes."""

    def test_find_shared_incidents(self):
        """Test finding incidents that share both pattern and root cause."""
        mock_tx = MagicMock()
        mock_result = [
            {"incident_id": "inc_1"},
            {"incident_id": "inc_2"},
            {"incident_id": "inc_3"},
        ]
        mock_tx.run.return_value = mock_result

        result = find_linked_incidents(mock_tx, "pc_123", "rc_456")

        assert len(result) == 3
        assert "inc_1" in result
        assert "inc_2" in result

    def test_no_shared_incidents(self):
        """Test when no incidents share both entities."""
        mock_tx = MagicMock()
        mock_tx.run.return_value = []

        result = find_linked_incidents(mock_tx, "pc_123", "rc_456")

        assert len(result) == 0


class TestCalculateLinkStrength:
    """Test link strength calculation."""

    def test_strong_category_match(self):
        """Test that category match contributes significantly to strength."""
        pattern_cluster = {
            "category": "performance",
            "keywords": ["timeout", "cpu"],
        }
        root_cause = {
            "category": "performance",
            "description": "Service timeout error",
        }

        strength = calculate_link_strength(pattern_cluster, root_cause, [])

        assert strength >= 0.4  # Category match alone gives 0.4

    def test_shared_incidents_boost_strength(self):
        """Test that shared incidents increase strength."""
        pattern_cluster = {
            "category": "different",  # No category match
            "keywords": ["timeout"],
        }
        root_cause = {
            "category": "other",
            "description": "Error occurred",
        }

        strength = calculate_link_strength(pattern_cluster, root_cause, ["inc_1", "inc_2", "inc_3"])

        assert strength >= 0.45  # 3 incidents * 0.15 = 0.45

    def test_keyword_overlap_adds_bonus(self):
        """Test keyword overlap in description adds bonus."""
        pattern_cluster = {
            "category": "different",
            "keywords": ["timeout", "error"],
        }
        root_cause = {
            "category": "other",
            "description": "There was a timeout error",  # Contains keywords
        }

        strength_without = calculate_link_strength(pattern_cluster, root_cause, [])
        strength_with = calculate_link_strength(pattern_cluster, root_cause, [])

        assert strength_with >= 0.1  # Keyword bonus

    def test_maximum_strength_capped(self):
        """Test that strength is capped at 1.0."""
        pattern_cluster = {
            "category": "performance",
            "keywords": ["timeout"],
        }
        root_cause = {
            "category": "performance",
            "description": "Timeout error",
        }

        strength = calculate_link_strength(pattern_cluster, root_cause, ["inc_{}".format(i) for i in range(100)])

        assert strength <= 1.0

    def test_weak_link_below_threshold(self):
        """Test links can be very weak."""
        pattern_cluster = {
            "category": "performance",
            "keywords": [],
        }
        root_cause = {
            "category": "database",
            "description": "Schema migration failed",
        }

        strength = calculate_link_strength(pattern_cluster, root_cause, [])

        assert strength < 0.3  # Below default threshold


class TestLinkPatternsToRootCauses:
    """Test MANIFESTS_AS relationship creation."""

    def test_create_links_above_threshold(self):
        """Test creating links above strength threshold."""
        mock_tx = MagicMock()
        mock_tx.run.side_effect = [
            [{"incident_id": "inc_1"}, {"incident_id": "inc_2"}],  # Shared incidents
            MagicMock(single=lambda: {"rel_count": 1}),
        ]

        pattern_clusters = [
            {"id": "pc_1", "signature": "test_pattern", "category": "performance", "keywords": ["timeout"]},
        ]
        root_causes = [
            {"id": "rc_1", "description": "Timeout error", "category": "performance", "mechanism": "timeout", "confidence": 0.8},
        ]

        count = link_patterns_to_root_causes(mock_tx, pattern_clusters, root_causes, min_strength=0.3, dry_run=False)

        assert count == 1

    def test_skip_links_below_threshold(self):
        """Test skipping links below strength threshold."""
        mock_tx = MagicMock()
        mock_tx.run.return_value = []  # No shared incidents

        pattern_clusters = [
            {"id": "pc_1", "signature": "test_pattern", "category": "performance", "keywords": []},
        ]
        root_causes = [
            {"id": "rc_1", "description": "Different issue", "category": "database", "mechanism": "schema", "confidence": 0.8},
        ]

        count = link_patterns_to_root_causes(mock_tx, pattern_clusters, root_causes, min_strength=0.3, dry_run=False)

        assert count == 0  # Category mismatch, no incidents, no keywords

    def test_dry_run_no_db_calls(self):
        """Test dry run mode doesn't make database calls."""
        mock_tx = MagicMock()

        pattern_clusters = [
            {"id": "pc_1", "signature": "test", "category": "test", "keywords": ["test"]},
        ]
        root_causes = [
            {"id": "rc_1", "description": "Test", "category": "test", "mechanism": "test", "confidence": 0.8},
        ]

        count = link_patterns_to_root_causes(mock_tx, pattern_clusters, root_causes, min_strength=0.3, dry_run=True)

        assert count == 1  # Counts what would be created
        mock_tx.run.assert_not_called()  # No actual DB calls

    def test_multiple_links_created(self):
        """Test creating multiple links."""
        mock_tx = MagicMock()
        # 2 patterns × 2 root causes = 4 pairs
        # Each pair: 1 call to find incidents + 1 call to create relationship = 8 total calls
        mock_tx.run.side_effect = [
            [{"incident_id": "inc_1"}],  # pc_1 + rc_1: find incidents
            MagicMock(single=lambda: {"rel_count": 1}),  # create relationship
            [{"incident_id": "inc_2"}],  # pc_1 + rc_2: find incidents
            MagicMock(single=lambda: {"rel_count": 1}),  # create relationship
            [{"incident_id": "inc_3"}],  # pc_2 + rc_1: find incidents
            MagicMock(single=lambda: {"rel_count": 1}),  # create relationship
            [{"incident_id": "inc_4"}],  # pc_2 + rc_2: find incidents
            MagicMock(single=lambda: {"rel_count": 1}),  # create relationship
        ]

        pattern_clusters = [
            {"id": "pc_1", "signature": "pattern_1", "category": "performance", "keywords": ["cpu"]},
            {"id": "pc_2", "signature": "pattern_2", "category": "performance", "keywords": ["memory"]},
        ]
        root_causes = [
            {"id": "rc_1", "description": "CPU overload", "category": "performance", "mechanism": "cpu", "confidence": 0.8},
            {"id": "rc_2", "description": "Memory leak", "category": "performance", "mechanism": "memory", "confidence": 0.8},
        ]

        count = link_patterns_to_root_causes(mock_tx, pattern_clusters, root_causes, min_strength=0.3, dry_run=False)

        assert count == 4


class TestVerifyLinkIntegrity:
    """Test link integrity verification."""

    def test_verify_returns_expected_structure(self):
        """Test verification returns correct structure."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        class MockRecord:
            def __init__(self, data):
                self._data = data
            def __getitem__(self, key):
                return self._data[key]

        mock_session.run.side_effect = [
            MagicMock(single=lambda: {"count": 150}),  # Total links
            MagicMock(single=lambda: {"avg_strength": 0.65, "min_strength": 0.3}),  # Strength stats
            MagicMock(single=lambda: {"count": 5}),  # Orphaned patterns
            MagicMock(single=lambda: {"count": 10}),  # Unlinked root causes
            MagicMock(single=lambda: {"strong": 50, "medium": 70, "weak": 30}),  # Distribution
        ]

        stats = verify_link_integrity(mock_driver)

        assert stats["manifests_as_relationships"] == 150
        assert stats["average_strength"] == 0.65
        assert stats["orphaned_patterns"] == 5
        assert stats["strong_links"] == 50

    def test_verify_handles_null_values(self):
        """Test verification handles null averages gracefully."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_session.run.side_effect = [
            MagicMock(single=lambda: {"count": 0}),
            MagicMock(single=lambda: {"avg_strength": None, "min_strength": None}),
            MagicMock(single=lambda: {"count": 0}),
            MagicMock(single=lambda: {"count": 0}),
            MagicMock(single=lambda: {"strong": 0, "medium": 0, "weak": 0}),
        ]

        stats = verify_link_integrity(mock_driver)

        assert stats["manifests_as_relationships"] == 0
        assert stats["average_strength"] == 0.0  # Should default to 0
        assert stats["minimum_strength"] == 0.0


class TestGetNeo4jDriver:
    """Test Neo4j driver creation."""

    @patch("scripts.link_patterns_to_root_causes.GraphDatabase.driver")
    @patch.dict(
        "os.environ",
        {
            "NEO4J_URI": "bolt://test:7687",
            "NEO4J_USER": "testuser",
            "NEO4J_PASSWORD": "testpass",
        },
        clear=True,
    )
    def test_driver_created_from_env_vars(self, mock_driver_class):
        """Test driver is created from environment variables."""
        mock_driver = MagicMock()
        mock_driver_class.return_value = mock_driver

        driver = get_neo4j_driver()

        mock_driver_class.assert_called_once_with("bolt://test:7687", auth=("testuser", "testpass"))
        assert driver == mock_driver

    @patch("scripts.link_patterns_to_root_causes.GraphDatabase.driver")
    @patch.dict("os.environ", {}, clear=True)
    def test_driver_uses_defaults_when_no_env(self, mock_driver_class):
        """Test driver uses default values when env vars not set."""
        mock_driver = MagicMock()
        mock_driver_class.return_value = mock_driver

        driver = get_neo4j_driver()

        mock_driver_class.assert_called_once_with(
            "bolt://localhost:7687", auth=("neo4j", "changeme_neo4j_pass123")
        )
