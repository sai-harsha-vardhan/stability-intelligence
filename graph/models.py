"""Graph node type dataclasses for Stability Intelligence System."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class Severity(str, Enum):
    """Incident severity levels."""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class RootCauseCategory(str, Enum):
    """Root cause categories."""
    CODE_BUG = "code_bug"
    CONFIG_DRIFT = "config_drift"
    INFRA_FAILURE = "infra_failure"
    DEPENDENCY_FAILURE = "dependency_failure"
    DATA_CORRUPTION = "data_corruption"
    RACE_CONDITION = "race_condition"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    BACKWARD_COMPAT_BREAK = "backward_compat_break"
    UNKNOWN = "unknown"


class Complexity(str, Enum):
    """Implementation complexity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StrategyType(str, Enum):
    """Strategy types for preventing patterns."""
    CONTRACT_TEST_SUITE = "contract_test_suite"
    AUTOMATED_REGRESSION_SUITE = "automated_regression_suite"
    ENVIRONMENT_PROMOTION_CHECK = "environment_promotion_check"
    STAGGERED_ROLLOUT_GATE = "staggered_rollout_gate"
    CHAOS_EXPERIMENT = "chaos_experiment"


class Trend(str, Enum):
    """Trend direction for pattern clusters."""
    WORSENING = "worsening"
    STABLE = "stable"
    IMPROVING = "improving"


@dataclass
class Node:
    """Base node class."""
    id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Incident(Node):
    """Production incident record."""
    title: str = ""
    body: str = ""
    raw_body: str = ""
    github_number: int = 0
    severity: Severity = Severity.P3
    occurred_at: Optional[datetime] = None
    detected_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_time_hours: float = 0.0
    affected_flows: List[str] = field(default_factory=list)
    merchant_impact: str = ""


@dataclass
class RCA(Node):
    """Root Cause Analysis document."""
    title: str = ""
    body: str = ""
    github_number: int = 0
    incident_id: Optional[str] = None


@dataclass
class RootCause(Node):
    """Root cause entity."""
    description: str = ""
    category: RootCauseCategory = RootCauseCategory.UNKNOWN
    confidence: float = 0.0
    mechanism: str = ""


@dataclass
class ActionItem(Node):
    """Action item to prevent future incidents."""
    title: str = ""
    description: str = ""
    github_number: int = 0
    status: str = "open"  # open, resolved, deferred
    resolved_at: Optional[datetime] = None
    assignee: str = ""
    implementation_complexity: Complexity = Complexity.MEDIUM
    backward_compat_risk: bool = False
    backward_compat_explanation: str = ""
    
    # Scoring fields
    forward_score: int = 0
    backward_score: int = 0
    blocking_multiplier: float = 1.0
    priority_score: float = 0.0
    stagger_safe: bool = False
    stagger_sequence: str = ""
    
    # Feedback fields
    effective: Optional[bool] = None
    effectiveness_checked_at: Optional[datetime] = None


@dataclass
class PatternCluster(Node):
    """Cluster of related root causes."""
    name: str = ""
    description: str = ""
    frequency: int = 0
    trend: Trend = Trend.STABLE
    incidents: List[str] = field(default_factory=list)
    affected_components: List[str] = field(default_factory=list)


@dataclass
class Strategy(Node):
    """Generated systemic strategy."""
    title: str = ""
    description: str = ""
    strategy_type: StrategyType = StrategyType.CONTRACT_TEST_SUITE
    pattern_cluster_ids: List[str] = field(default_factory=list)
    status: str = "proposed"  # proposed, implemented
    implemented_at: Optional[datetime] = None
    estimated_reduction_percent: float = 0.0
    
    # Scoring fields
    forward_score: int = 0
    backward_score: int = 0
    blocking_multiplier: float = 1.0
    priority_score: float = 0.0
    implementation_complexity: Complexity = Complexity.MEDIUM
    
    # Feedback fields
    effective: Optional[bool] = None
    effectiveness_checked_at: Optional[datetime] = None


@dataclass
class Component(Node):
    """Software component (module, connector, etc.)."""
    name: str = ""
    component_type: str = "module"  # module, connector, api_contract, trait
    file_path: str = ""
    stability_score: float = 1.0  # 0.0-1.0, higher is better
    incident_count: int = 0


@dataclass
class CodeModule(Component):
    """Parsed Rust module."""
    component_type: str = "module"
    functions: List[str] = field(default_factory=list)
    structs: List[str] = field(default_factory=list)
    traits: List[str] = field(default_factory=list)


@dataclass
class CodeFunction(Node):
    """Parsed function from Rust code."""
    name: str = ""
    module_id: str = ""
    signature: str = ""
    is_async: bool = False
    is_pub: bool = False


@dataclass
class CodeStruct(Node):
    """Parsed struct from Rust code."""
    name: str = ""
    module_id: str = ""
    derives: List[str] = field(default_factory=list)
    is_pub: bool = False


@dataclass
class ConnectorNode(Component):
    """Payment connector implementation."""
    component_type: str = "connector"
    connector_type: str = ""  # processor, acquirer, etc.
    integration_trait: str = ""


@dataclass
class ApiContractNode(Component):
    """API contract struct (with Serialize/Deserialize)."""
    component_type: str = "api_contract"
    endpoint_paths: List[str] = field(default_factory=list)


@dataclass
class ActivityEvent(Node):
    """Log entry for agent activity."""
    agent_name: str = ""
    event_type: str = ""  # ingestion, pattern, impact, strategy, feedback
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    linked_node_id: Optional[str] = None
    linked_node_type: Optional[str] = None


@dataclass
class CausalEdge:
    """Relationship between nodes."""
    source_id: str
    target_id: str
    relationship_type: str
    confidence: float = 1.0
    properties: Dict[str, Any] = field(default_factory=dict)


# Node type to class mapping
NODE_TYPES = {
    "Incident": Incident,
    "RCA": RCA,
    "RootCause": RootCause,
    "ActionItem": ActionItem,
    "PatternCluster": PatternCluster,
    "Strategy": Strategy,
    "Component": Component,
    "CodeModule": CodeModule,
    "CodeFunction": CodeFunction,
    "CodeStruct": CodeStruct,
    "ConnectorNode": ConnectorNode,
    "ApiContractNode": ApiContractNode,
    "ActivityEvent": ActivityEvent,
}
