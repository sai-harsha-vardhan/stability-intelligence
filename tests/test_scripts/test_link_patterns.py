"""Unit tests for link_patterns.py pattern linking script."""

from unittest.mock import MagicMock, patch
import pytest

from scripts.link_patterns import (
    calculate_category_match_score,
    calculate_text_similarity_score,
    create_addresses_pattern_relationships,
    create_clustered_into_relationships,
    fetch_all_action_items,
    fetch_all_pattern_clusters,
    fetch_all_root_causes,
    find_matching_pattern_clusters,
    find_patterns_addressed_by_action_item,
    get_neo4j_driver,
    normalize_text_for_matching,
    verify_pattern_links,
)


class TestNormalizeTextForMatching:
    """Test text normalization for keyword matching."""

    def test_normalize_empty_text(self):
        """Test normalization of empty text."""
        result = normalize_text_for_matching("")
        assert result == set()

    def test_normalize_basic_text(self):
        """Test basic text normalization."""
        result = normalize_text_for_matching("Connection timeout error occurred")
        assert "connection" in result
        assert "timeout" in result
        assert "error" in result
        assert "occurred" in result

    def test_removes_filler_words(self):
        """Test removal of filler words."""
        result = normalize_text_for_matching("The server is on fire")
        assert "the" not in result
        assert "is" not in result
        assert "on" not in result
        assert "server" in result
        assert "fire" in result

    def test_handles_punctuation(self):
        """Test punctuation removal."""
        result = normalize_text_for_matching("Error: connection failed!")
        assert "error" in result
        assert "connection" in result
        assert "failed" in result
        assert ":" not in result
        assert "!" not in result

    def test_filters_short_words(self):
        """Test filtering of short words."""
        result = normalize_text_for_matching("a bc def ghi jklm")
        assert "a" not in result
        assert "bc" not in result
        assert "def" in result


class TestCalculateCategoryMatchScore:
    """Test category matching score calculation."""

    def test_exact_category_match(self):
        """Test matching identical categories."""
        score = calculate_category_match_score("performance", "timeout", "performance", "timeout")
        assert score >= 0.5  # Direct category match contributes 0.5

    def test_exact_mechanism_match(self):
        """Test matching mechanisms."""
        score = calculate_category_match_score("general", "timeout", "different", "timeout")
        assert score >= 0.3  # Mechanism match contributes 0.3

    def test_no_match(self):
        """Test completely different categories."""
        score = calculate_category_match_score("security", "auth", "database", "sql")
        assert score == 0.0

    def test_related_categories(self):
        """Test related categories get bonus."""
        # Both contain "timeout" which is in the network category relations list
        # PC: "timeout_errors" contains "timeout" -> matches network category
        # RC: "timeout_slow" contains "timeout" -> matches network category
        score = calculate_category_match_score("timeout_errors", "api", "timeout_slow", "latency")
        assert score >= 0.2  # Should get related category bonus (0.2)


class TestCalculateTextSimilarityScore:
    """Test text similarity calculation."""

    def test_identical_texts(self):
        """Test identical texts have high similarity."""
        text = "Connection timeout error occurred"
        score = calculate_text_similarity_score(text, text)
        assert score == 1.0

    def test_completely_different_texts(self):
        """Test completely different texts."""
        text1 = "Connection timeout"
        text2 = "Database query failed"
        score = calculate_text_similarity_score(text1, text2)
        assert score == 0.0

    def test_partial_overlap(self):
        """Test partially overlapping texts."""
        text1 = "Connection timeout error"
        text2 = "Connection failure timeout"
        score = calculate_text_similarity_score(text1, text2)
        assert 0 < score < 1.0

    def test_empty_texts(self):
        """Test empty text handling."""
        assert calculate_text_similarity_score("", "test") == 0.0
        assert calculate_text_similarity_score("test", "") == 0.0
        assert calculate_text_similarity_score("", "") == 0.0


class TestFetchAllPatternClusters:
    """Test fetching pattern clusters."""

    def test_fetch_returns_expected_structure(self):
        """Test that fetch returns correct data structure."""
        mock_tx = MagicMock()
        mock_records = [
            {
                "cluster_id": "pc_test123",
                "signature": "timeout_performance",
                "category": "performance",
                "mechanism": "timeout",
                "description": "Timeout errors",
                "frequency": 10,
            }
        ]
        mock_tx.run.return_value = mock_records

        result = fetch_all_pattern_clusters(mock_tx)

        assert len(result) == 1
        assert result[0]["cluster_id"] == "pc_test123"
        assert result[0]["category"] == "performance"
        assert result[0]["frequency"] == 10


class TestFetchAllRootCauses:
    """Test fetching root causes."""

    def test_fetch_returns_expected_structure(self):
        """Test that fetch returns correct data structure."""
        mock_tx = MagicMock()
        mock_records = [
            {
                "root_cause_id": "rc_test456",
                "category": "performance",
                "mechanism": "timeout",
                "description": "Connection timeout occurred",
                "confidence": 0.85,
                "incident_ids": ["inc_1", "inc_2"],
            }
        ]
        mock_tx.run.return_value = mock_records

        result = fetch_all_root_causes(mock_tx)

        assert len(result) == 1
        assert result[0]["root_cause_id"] == "rc_test456"
        assert result[0]["category"] == "performance"
        assert result[0]["confidence"] == 0.85
        assert result[0]["incident_ids"] == ["inc_1", "inc_2"]


class TestFetchAllActionItems:
    """Test fetching action items."""

    def test_fetch_returns_expected_structure(self):
        """Test that fetch returns correct data structure."""
        mock_tx = MagicMock()
        mock_records = [
            {
                "action_item_id": "ai_test789",
                "description": "Fix timeout issue",
                "category": "performance",
                "status": "open",
                "priority": 8.5,
                "linked_root_cause_ids": ["rc_test456"],
                "linked_rc_categories": ["performance"],
            }
        ]
        mock_tx.run.return_value = mock_records

        result = fetch_all_action_items(mock_tx)

        assert len(result) == 1
        assert result[0]["action_item_id"] == "ai_test789"
        assert result[0]["status"] == "open"
        assert result[0]["priority"] == 8.5
        assert result[0]["linked_root_cause_ids"] == ["rc_test456"]


class TestFindMatchingPatternClusters:
    """Test finding matching pattern clusters for root causes."""

    def test_exact_match(self):
        """Test matching identical category and mechanism."""
        root_cause = {
            "root_cause_id": "rc_1",
            "category": "performance",
            "mechanism": "timeout",
            "description": "Connection timeout",
            "confidence": 0.9,
        }
        pattern_clusters = [
            {
                "cluster_id": "pc_1",
                "signature": "timeout_perf",
                "category": "performance",
                "mechanism": "timeout",
                "description": "Timeout occurred",
                "frequency": 10,
            }
        ]

        matches = find_matching_pattern_clusters(root_cause, pattern_clusters, threshold=0.4)

        assert len(matches) == 1
        assert matches[0][0] == "pc_1"
        assert matches[0][1] >= 0.4

    def test_no_match_below_threshold(self):
        """Test that matches below threshold are filtered."""
        root_cause = {
            "root_cause_id": "rc_1",
            "category": "database",
            "mechanism": "query",
            "description": "Query timeout",
            "confidence": 0.8,
        }
        pattern_clusters = [
            {
                "cluster_id": "pc_1",
                "signature": "security_auth",
                "category": "security",
                "mechanism": "auth",
                "description": "Authentication failed",
                "frequency": 5,
            }
        ]

        matches = find_matching_pattern_clusters(root_cause, pattern_clusters, threshold=0.4)

        assert len(matches) == 0

    def test_limits_to_top_3(self):
        """Test that only top 3 matches are returned."""
        root_cause = {
            "root_cause_id": "rc_1",
            "category": "performance",
            "mechanism": "general",
            "description": "Performance issue",
            "confidence": 0.9,
        }
        pattern_clusters = [
            {
                "cluster_id": f"pc_{i}",
                "signature": f"perf_{i}",
                "category": "performance",
                "mechanism": f"mech_{i}",
                "description": f"Performance issue {i}",
                "frequency": 20,
            }
            for i in range(10)
        ]

        matches = find_matching_pattern_clusters(root_cause, pattern_clusters, threshold=0.1)

        assert len(matches) <= 3


class TestCreateClusteredIntoRelationships:
    """Test CLUSTERED_INTO relationship creation."""

    def test_create_single_relationship(self):
        """Test creating one CLUSTERED_INTO relationship."""
        mock_tx = MagicMock()
        mock_record = {"rel_count": 1}
        mock_tx.run.return_value.single.return_value = mock_record

        matches = [("rc_test", "pc_test", 0.85)]
        count = create_clustered_into_relationships(mock_tx, matches, dry_run=False)

        assert count == 1
        mock_tx.run.assert_called_once()

    def test_dry_run_no_db_calls(self):
        """Test dry run mode doesn't make database calls."""
        mock_tx = MagicMock()

        matches = [("rc_test", "pc_test", 0.85)]
        count = create_clustered_into_relationships(mock_tx, matches, dry_run=True)

        assert count == 1
        mock_tx.run.assert_not_called()

    def test_multiple_relationships(self):
        """Test creating multiple relationships."""
        mock_tx = MagicMock()
        mock_record = {"rel_count": 1}
        mock_tx.run.return_value.single.return_value = mock_record

        matches = [
            ("rc_1", "pc_1", 0.9),
            ("rc_2", "pc_1", 0.8),
            ("rc_3", "pc_2", 0.85),
        ]
        count = create_clustered_into_relationships(mock_tx, matches, dry_run=False)

        assert count == 3
        assert mock_tx.run.call_count == 3


class TestFindPatternsAddressedByActionItem:
    """Test finding patterns addressed by action items."""

    def test_shared_root_cause_link(self):
        """Test linking through shared root cause."""
        action_item = {
            "action_item_id": "ai_1",
            "description": "Fix timeout",
            "category": "performance",
            "status": "open",
            "linked_root_cause_ids": ["rc_shared"],
            "linked_rc_categories": ["performance"],
        }
        pattern_clusters = [
            {
                "cluster_id": "pc_1",
                "signature": "timeout_perf",
                "category": "performance",
                "mechanism": "timeout",
                "description": "Timeout occurred",
                "frequency": 10,
            }
        ]
        clustered_into_pairs = [("rc_shared", "pc_1", 0.9)]

        related = find_patterns_addressed_by_action_item(action_item, pattern_clusters, clustered_into_pairs)

        assert len(related) == 1
        assert related[0][0] == "pc_1"

    def test_category_match_link(self):
        """Test linking through category match plus text similarity."""
        action_item = {
            "action_item_id": "ai_1",
            "description": "Fix security authentication issue",  # Contains "authentication" for text match
            "category": "security",
            "status": "open",
            "linked_root_cause_ids": [],
            "linked_rc_categories": ["security"],
        }
        pattern_clusters = [
            {
                "cluster_id": "pc_1",
                "signature": "sec_auth",
                "category": "security",
                "mechanism": "auth",
                "description": "Authentication security failure",  # Contains "authentication" and "security"
                "frequency": 5,
            }
        ]
        clustered_into_pairs = []

        related = find_patterns_addressed_by_action_item(action_item, pattern_clusters, clustered_into_pairs)

        assert len(related) == 1
        assert related[0][0] == "pc_1"

    def test_limits_to_top_5(self):
        """Test that only top 5 matches are returned."""
        action_item = {
            "action_item_id": "ai_1",
            "description": "General action",
            "category": "general",
            "status": "open",
            "linked_root_cause_ids": [f"rc_{i}" for i in range(10)],
            "linked_rc_categories": ["general"],
        }
        pattern_clusters = [
            {
                "cluster_id": f"pc_{i}",
                "signature": f"general_{i}",
                "category": "general",
                "mechanism": "unknown",
                "description": f"General issue {i}",
                "frequency": 5,
            }
            for i in range(10)
        ]
        clustered_into_pairs = [(f"rc_{i}", f"pc_{i}", 0.9) for i in range(10)]

        related = find_patterns_addressed_by_action_item(action_item, pattern_clusters, clustered_into_pairs)

        assert len(related) <= 5


class TestCreateAddressesPatternRelationships:
    """Test ADDRESSES_PATTERN relationship creation."""

    def test_create_single_relationship(self):
        """Test creating one ADDRESSES_PATTERN relationship."""
        mock_tx = MagicMock()
        mock_record = {"rel_count": 1}
        mock_tx.run.return_value.single.return_value = mock_record

        matches = [("ai_test", "pc_test", 0.75)]
        count = create_addresses_pattern_relationships(mock_tx, matches, dry_run=False)

        assert count == 1
        mock_tx.run.assert_called_once()

    def test_dry_run_no_db_calls(self):
        """Test dry run mode doesn't make database calls."""
        mock_tx = MagicMock()

        matches = [("ai_test", "pc_test", 0.75)]
        count = create_addresses_pattern_relationships(mock_tx, matches, dry_run=True)

        assert count == 1
        mock_tx.run.assert_not_called()


class TestVerifyPatternLinks:
    """Test pattern link verification."""

    def test_verify_returns_expected_counts(self):
        """Test verification returns correct counts."""
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        mock_session.run.side_effect = [
            MagicMock(single=lambda: {"count": 25}),  # PatternCluster count
            MagicMock(single=lambda: {"count": 168}),  # RootCause count
            MagicMock(single=lambda: {"count": 298}),  # ActionItem count
            MagicMock(single=lambda: {"count": 40}),   # CLUSTERED_INTO count
            MagicMock(single=lambda: {"count": 60}),   # ADDRESSES_PATTERN count
            MagicMock(single=lambda: {"count": 5}),    # Orphaned count
            MagicMock(single=lambda: {"avg_score": 0.65}),  # Avg CLUSTERED_INTO score
            MagicMock(single=lambda: {"avg_score": 0.55}),  # Avg ADDRESSES_PATTERN score
            MagicMock(single=lambda: {"total": 168, "clustered": 150}),  # Coverage stats
        ]

        stats = verify_pattern_links(mock_driver)

        assert stats["pattern_clusters"] == 25
        assert stats["root_causes"] == 168
        assert stats["action_items"] == 298
        assert stats["clustered_into"] == 40
        assert stats["addresses_pattern"] == 60
        assert stats["orphaned_clusters"] == 5
        assert stats["avg_cluster_score"] == 0.65
        assert stats["avg_address_score"] == 0.55
        assert stats["cluster_coverage_pct"] == round(150 / 168 * 100, 1)


class TestGetNeo4jDriver:
    """Test Neo4j driver creation."""

    @patch("scripts.link_patterns.GraphDatabase.driver")
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

    @patch("scripts.link_patterns.GraphDatabase.driver")
    @patch.dict("os.environ", {}, clear=True)
    def test_driver_uses_defaults_when_no_env(self, mock_driver_class):
        """Test driver uses default values when env vars not set."""
        mock_driver = MagicMock()
        mock_driver_class.return_value = mock_driver

        driver = get_neo4j_driver()

        mock_driver_class.assert_called_once_with(
            "bolt://localhost:7687", auth=("neo4j", "changeme_neo4j_pass123")
        )


class TestMainIntegration:
    """Integration-style tests for the linking workflow."""

    def test_end_to_end_matching_workflow(self):
        """Test the full matching workflow with sample data."""
        # Sample pattern clusters
        pattern_clusters = [
            {
                "cluster_id": "pc_timeout",
                "signature": "timeout_performance",
                "category": "performance",
                "mechanism": "timeout",
                "description": "Connection timeout errors",
                "frequency": 15,
            },
            {
                "cluster_id": "pc_auth",
                "signature": "authentication_security",
                "category": "security",
                "mechanism": "authentication",
                "description": "Authentication failures",
                "frequency": 8,
            },
        ]

        # Sample root causes
        root_causes = [
            {
                "root_cause_id": "rc_1",
                "category": "performance",
                "mechanism": "timeout",
                "description": "Database connection timeout",
                "confidence": 0.9,
            },
            {
                "root_cause_id": "rc_2",
                "category": "security",
                "mechanism": "authentication",
                "description": "Invalid credentials provided",
                "confidence": 0.85,
            },
            {
                "root_cause_id": "rc_3",
                "category": "database",
                "mechanism": "query",
                "description": "Slow query execution",
                "confidence": 0.8,
            },
        ]

        # Find matches for each root cause
        clustered_into_pairs = []
        for rc in root_causes:
            matches = find_matching_pattern_clusters(rc, pattern_clusters, threshold=0.4)
            for pc_id, score in matches:
                clustered_into_pairs.append((rc["root_cause_id"], pc_id, score))

        # Timeout root cause should match timeout pattern
        timeout_matches = [(rid, cid, s) for rid, cid, s in clustered_into_pairs if cid == "pc_timeout"]
        assert any(rid == "rc_1" for rid, _, _ in timeout_matches)

        # Auth root cause should match auth pattern
        auth_matches = [(rid, cid, s) for rid, cid, s in clustered_into_pairs if cid == "pc_auth"]
        assert any(rid == "rc_2" for rid, _, _ in auth_matches)
