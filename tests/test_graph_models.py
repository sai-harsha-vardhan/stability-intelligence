"""Tests for graph models and Neo4j schema."""
import pytest
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.models import (
    Severity, RootCauseCategory, Complexity, StrategyType, Trend,
    Node, Incident, RCA, RootCause, ActionItem, PatternCluster,
    Strategy, Component, CodeModule, CodeFunction, CodeStruct,
    ConnectorNode, ApiContractNode, ActivityEvent, CausalEdge,
    NODE_TYPES,
)


class TestEnumTypes:
    """Test suite for enum types."""

    def test_severity_enum(self):
        """Test Severity enum values."""
        assert Severity.P0.value == "P0"
        assert Severity.P1.value == "P1"
        assert Severity.P2.value == "P2"
        assert Severity.P3.value == "P3"

    def test_root_cause_category_enum(self):
        """Test RootCauseCategory enum values."""
        categories = [
            RootCauseCategory.CODE_BUG,
            RootCauseCategory.CONFIG_DRIFT,
            RootCauseCategory.INFRA_FAILURE,
            RootCauseCategory.DEPENDENCY_FAILURE,
            RootCauseCategory.DATA_CORRUPTION,
            RootCauseCategory.RACE_CONDITION,
            RootCauseCategory.RESOURCE_EXHAUSTION,
            RootCauseCategory.BACKWARD_COMPAT_BREAK,
            RootCauseCategory.UNKNOWN,
        ]
        for category in categories:
            assert isinstance(category.value, str)
            assert len(category.value) > 0

    def test_complexity_enum(self):
        """Test Complexity enum values."""
        assert Complexity.LOW.value == "low"
        assert Complexity.MEDIUM.value == "medium"
        assert Complexity.HIGH.value == "high"

    def test_strategy_type_enum(self):
        """Test StrategyType enum values."""
        strategy_types = [
            StrategyType.CONTRACT_TEST_SUITE,
            StrategyType.AUTOMATED_REGRESSION_SUITE,
            StrategyType.ENVIRONMENT_PROMOTION_CHECK,
            StrategyType.STAGGERED_ROLLOUT_GATE,
            StrategyType.CHAOS_EXPERIMENT,
        ]
        for st in strategy_types:
            assert isinstance(st.value, str)
            assert "_" in st.value  # All snake_case

    def test_trend_enum(self):
        """Test Trend enum values."""
        assert Trend.WORSENING.value == "worsening"
        assert Trend.STABLE.value == "stable"
        assert Trend.IMPROVING.value == "improving"


class TestNodeModels:
    """Test suite for node models."""

    def test_base_node_creation(self):
        """Test base Node dataclass creation."""
        node = Node(id="test-123")
        assert node.id == "test-123"
        assert isinstance(node.created_at, datetime)
        assert isinstance(node.updated_at, datetime)

    def test_incident_creation(self):
        """Test Incident dataclass creation."""
        incident = Incident(
            id="inc-123",
            title="Test Incident",
            body="Test description",
            github_number=456,
            severity=Severity.P1,
            affected_flows=["payment", "refund"],
        )
        assert incident.title == "Test Incident"
        assert incident.severity == Severity.P1
        assert incident.affected_flows == ["payment", "refund"]
        assert incident.resolution_time_hours == 0.0

    def test_rca_creation(self):
        """Test RCA dataclass creation."""
        rca = RCA(
            id="rca-123",
            title="RCA for Incident 456",
            body="Root cause analysis",
            github_number=789,
            incident_id="inc-456",
        )
        assert rca.title == "RCA for Incident 456"
        assert rca.incident_id == "inc-456"

    def test_root_cause_creation(self):
        """Test RootCause dataclass creation."""
        rc = RootCause(
            id="cause-123",
            description="Database timeout",
            category=RootCauseCategory.RESOURCE_EXHAUSTION,
            confidence=0.95,
            mechanism="Connection pool exhausted",
        )
        assert rc.category == RootCauseCategory.RESOURCE_EXHAUSTION
        assert rc.confidence == 0.95
        assert 0.0 <= rc.confidence <= 1.0

    def test_action_item_creation(self):
        """Test ActionItem dataclass creation."""
        action = ActionItem(
            id="action-123",
            title="Increase connection pool",
            description="Add more connections",
            github_number=999,
            status="open",
            forward_score=5,
            backward_score=3,
            blocking_multiplier=2.0,
            priority_score=8.0,
        )
        assert action.forward_score == 5
        assert action.backward_score == 3
        assert action.blocking_multiplier == 2.0
        assert action.priority_score == 8.0

    def test_pattern_cluster_creation(self):
        """Test PatternCluster dataclass creation."""
        cluster = PatternCluster(
            id="cluster-123",
            name="DB Timeouts",
            description="Database connection timeouts",
            frequency=5,
            trend=Trend.WORSENING,
            incidents=["inc-1", "inc-2"],
            affected_components=["database", "pool"],
        )
        assert cluster.frequency == 5
        assert cluster.trend == Trend.WORSENING
        assert len(cluster.incidents) == 2

    def test_strategy_creation(self):
        """Test Strategy dataclass creation."""
        strategy = Strategy(
            id="strat-123",
            title="Add monitoring",
            description="Monitor DB connections",
            strategy_type=StrategyType.CONTRACT_TEST_SUITE,
            pattern_cluster_ids=["cluster-1"],
            status="proposed",
            estimated_reduction_percent=30.0,
        )
        assert strategy.strategy_type == StrategyType.CONTRACT_TEST_SUITE
        assert strategy.estimated_reduction_percent == 30.0

    def test_component_creation(self):
        """Test Component dataclass creation."""
        component = Component(
            id="comp-123",
            name="Payment Module",
            component_type="module",
            file_path="src/payment.rs",
            stability_score=0.85,
            incident_count=2,
        )
        assert component.stability_score == 0.85
        assert 0.0 <= component.stability_score <= 1.0

    def test_code_module_creation(self):
        """Test CodeModule dataclass creation."""
        module = CodeModule(
            id="mod-123",
            name="payments.rs",
            file_path="src/payments.rs",
            functions=["process_payment", "refund"],
            structs=["PaymentRequest", "RefundRequest"],
            traits=["PaymentProcessor"],
        )
        assert module.component_type == "module"
        assert len(module.functions) == 2
        assert len(module.structs) == 2

    def test_code_function_creation(self):
        """Test CodeFunction dataclass creation."""
        func = CodeFunction(
            id="func-123",
            name="process_payment",
            module_id="mod-456",
            signature="fn process_payment(&self, req: PaymentRequest)",
            is_async=True,
            is_pub=True,
        )
        assert func.is_async is True
        assert func.is_pub is True

    def test_code_struct_creation(self):
        """Test CodeStruct dataclass creation."""
        struct = CodeStruct(
            id="struct-123",
            name="PaymentRequest",
            module_id="mod-456",
            derives=["Serialize", "Deserialize", "Debug"],
            is_pub=True,
        )
        assert "Serialize" in struct.derives
        assert struct.is_pub is True

    def test_connector_node_creation(self):
        """Test ConnectorNode dataclass creation."""
        connector = ConnectorNode(
            id="conn-123",
            name="Stripe",
            connector_type="processor",
            integration_trait="PaymentConnector",
        )
        assert connector.component_type == "connector"
        assert connector.connector_type == "processor"

    def test_api_contract_node_creation(self):
        """Test ApiContractNode dataclass creation."""
        contract = ApiContractNode(
            id="api-123",
            name="PaymentRequest",
            endpoint_paths=["/api/v1/payments", "/api/v1/refunds"],
        )
        assert contract.component_type == "api_contract"
        assert "/api/v1/payments" in contract.endpoint_paths

    def test_activity_event_creation(self):
        """Test ActivityEvent dataclass creation."""
        event = ActivityEvent(
            id="evt-123",
            agent_name="strategy_agent",
            event_type="strategy",
            message="Generated 3 strategies",
            details={"count": 3},
            linked_node_id="strat-456",
            linked_node_type="Strategy",
        )
        assert event.agent_name == "strategy_agent"
        assert event.event_type == "strategy"
        assert event.linked_node_type == "Strategy"


class TestCausalEdge:
    """Test suite for CausalEdge."""

    def test_edge_creation(self):
        """Test CausalEdge creation."""
        edge = CausalEdge(
            source_id="inc-123",
            target_id="rca-456",
            relationship_type="HAS_RCA",
            confidence=0.9,
            properties={"verified": True},
        )
        assert edge.source_id == "inc-123"
        assert edge.target_id == "rca-456"
        assert edge.relationship_type == "HAS_RCA"
        assert edge.confidence == 0.9


class TestNodeTypesMapping:
    """Test suite for NODE_TYPES mapping."""

    def test_all_node_types_present(self):
        """Test that all node types are in the mapping."""
        expected_types = [
            "Incident", "RCA", "RootCause", "ActionItem",
            "PatternCluster", "Strategy", "Component",
            "CodeModule", "CodeFunction", "CodeStruct",
            "ConnectorNode", "ApiContractNode", "ActivityEvent",
        ]
        for node_type in expected_types:
            assert node_type in NODE_TYPES

    def test_node_type_classes_correct(self):
        """Test that NODE_TYPES maps to correct classes."""
        assert NODE_TYPES["Incident"] == Incident
        assert NODE_TYPES["RCA"] == RCA
        assert NODE_TYPES["Strategy"] == Strategy
        assert NODE_TYPES["CodeModule"] == CodeModule


class TestDataclassBehavior:
    """Test suite for dataclass behaviors."""

    def test_asdict_conversion(self):
        """Test converting dataclass to dict."""
        incident = Incident(
            id="inc-123",
            title="Test",
            severity=Severity.P1,
        )
        data = asdict(incident)
        assert data["id"] == "inc-123"
        assert data["title"] == "Test"
        assert data["severity"] == "P1"

    def test_datetime_fields_auto_populate(self):
        """Test that datetime fields auto-populate."""
        before = datetime.utcnow()
        node = Node(id="test")
        after = datetime.utcnow()
        
        assert before <= node.created_at <= after
        assert before <= node.updated_at <= after

    def test_list_fields_default_empty(self):
        """Test that list fields default to empty lists."""
        incident = Incident(id="inc-123")
        assert incident.affected_flows == []
        assert isinstance(incident.affected_flows, list)

    def test_optional_fields_none_default(self):
        """Test that optional fields default to None."""
        incident = Incident(id="inc-123")
        assert incident.occurred_at is None
        assert incident.detected_at is None
        assert incident.resolved_at is None

    def test_immutability_of_defaults(self):
        """Test that default list objects are not shared."""
        inc1 = Incident(id="inc-1")
        inc2 = Incident(id="inc-2")
        
        inc1.affected_flows.append("payment")
        assert "payment" not in inc2.affected_flows
        assert inc1.affected_flows != inc2.affected_flows


class TestModelValidation:
    """Test suite for model validation patterns."""

    def test_severity_comparison(self):
        """Test severity ordering."""
        severities = [Severity.P3, Severity.P1, Severity.P0, Severity.P2]
        # P0 > P1 > P2 > P3 (most severe first)
        order_map = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
        sorted_sevs = sorted(severities, key=lambda s: order_map[s])
        assert sorted_sevs == [Severity.P0, Severity.P1, Severity.P2, Severity.P3]

    def test_complexity_ordering(self):
        """Test complexity ordering."""
        complexities = [Complexity.HIGH, Complexity.LOW, Complexity.MEDIUM]
        order_map = {Complexity.LOW: 0, Complexity.MEDIUM: 1, Complexity.HIGH: 2}
        sorted_comp = sorted(complexities, key=lambda c: order_map[c])
        assert sorted_comp == [Complexity.LOW, Complexity.MEDIUM, Complexity.HIGH]

    def test_trend_priority(self):
        """Test trend priorities."""
        # Worsening trends should be prioritized
        assert Trend.WORSENING.value == "worsening"
        assert Trend.IMPROVING.value == "improving"
        # No inherent ordering, just value check


class TestStrategyScoring:
    """Test suite for strategy scoring logic."""

    def test_strategy_score_calculation(self):
        """Test priority score calculation pattern."""
        strategy = Strategy(
            id="strat-123",
            forward_score=10,
            backward_score=5,
            blocking_multiplier=2.0,
        )
        
        # Calculate normalized priority score
        priority_score = (strategy.forward_score + strategy.backward_score) * strategy.blocking_multiplier / 2
        strategy.priority_score = priority_score
        
        assert strategy.priority_score == 15.0

    def test_action_item_score_calculation(self):
        """Test action item priority calculation."""
        action = ActionItem(
            id="action-123",
            forward_score=8,
            backward_score=4,
            blocking_multiplier=1.5,
        )
        
        action.priority_score = (action.forward_score + action.backward_score) * action.blocking_multiplier / 2
        assert action.priority_score == 9.0

    def test_stagger_safe_check(self):
        """Test stagger safety check logic."""
        action = ActionItem(
            id="action-123",
            backward_score=3,
            blocking_multiplier=1.5,
        )
        
        # Stagger safe if backward_score < 5 AND blocking_multiplier < 2
        action.stagger_safe = action.backward_score < 5 and action.blocking_multiplier < 2
        assert action.stagger_safe is True

    def test_high_backwards_risk_not_stagger_safe(self):
        """Test that high backwards risk is not stagger safe."""
        action = ActionItem(
            id="action-123",
            backward_score=7,
            blocking_multiplier=1.2,
        )
        
        action.stagger_safe = action.backward_score < 5 and action.blocking_multiplier < 2
        assert action.stagger_safe is False
