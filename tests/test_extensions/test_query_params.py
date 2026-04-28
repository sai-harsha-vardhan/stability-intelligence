"""
Tests for extensions.api.query_params module.

These tests validate Pydantic models for query parameter validation
across the Paperclip Governance Extensions API endpoints.
"""

import pytest
from pydantic import ValidationError

from extensions.api.query_params import (
    IssueFilterParams,
    RoutineAlertParams,
    StatusTransitionRequest,
)


class TestIssueFilterParams:
    """Tests for IssueFilterParams query parameter model."""

    def test_empty_params_valid(self):
        """Test that all optional fields can be None."""
        params = IssueFilterParams()
        assert params.wave is None
        assert params.status is None
        assert params.label is None
        assert params.parent is None

    def test_valid_wave_values(self):
        """Test all valid wave enum values."""
        for wave in ["wave-1", "wave-2", "wave-3", "wave-4"]:
            params = IssueFilterParams(wave=wave)
            assert params.wave == wave

    def test_invalid_wave_raises_error(self):
        """Test that invalid wave value raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            IssueFilterParams(wave="invalid-wave")
        
        error_msg = str(exc_info.value)
        assert "wave" in error_msg

    def test_valid_status(self):
        """Test valid status string."""
        params = IssueFilterParams(status="in_progress")
        assert params.status == "in_progress"

    def test_empty_status_raises_error(self):
        """Test that empty status string raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            IssueFilterParams(status="")
        
        assert "empty" in str(exc_info.value).lower()

    def test_status_with_max_length(self):
        """Test status at max length boundary."""
        long_status = "a" * 50
        params = IssueFilterParams(status=long_status)
        assert params.status == long_status

    def test_status_exceeds_max_length(self):
        """Test status exceeding max length raises error."""
        with pytest.raises(ValidationError) as exc_info:
            IssueFilterParams(status="a" * 51)
        
        assert "50" in str(exc_info.value)

    def test_valid_label(self):
        """Test valid label string."""
        params = IssueFilterParams(label="priority/critical")
        assert params.label == "priority/critical"

    def test_empty_label_raises_error(self):
        """Test that empty label string raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            IssueFilterParams(label="")
        
        assert "empty" in str(exc_info.value).lower()

    def test_valid_parent(self):
        """Test valid parent ID."""
        params = IssueFilterParams(parent="issue-123")
        assert params.parent == "issue-123"

    def test_empty_parent_raises_error(self):
        """Test that empty parent string raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            IssueFilterParams(parent="")
        
        assert "empty" in str(exc_info.value).lower()

    def test_combined_params(self):
        """Test multiple parameters together."""
        params = IssueFilterParams(
            wave="wave-1",
            status="in_progress",
            label="priority/high",
            parent="issue-parent"
        )
        assert params.wave == "wave-1"
        assert params.status == "in_progress"
        assert params.label == "priority/high"
        assert params.parent == "issue-parent"

    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored (model_config.extra='ignore')."""
        params = IssueFilterParams(
            wave="wave-1",
            unknown_field="should_be_ignored"
        )
        assert params.wave == "wave-1"
        assert not hasattr(params, "unknown_field")


class TestRoutineAlertParams:
    """Tests for RoutineAlertParams query parameter model."""

    def test_default_values(self):
        """Test default parameter values."""
        params = RoutineAlertParams()
        assert params.stale_multiplier == 2.0
        assert params.min_stale_seconds == 3600

    def test_valid_stale_multiplier(self):
        """Test valid stale multiplier values."""
        params = RoutineAlertParams(stale_multiplier=3.5)
        assert params.stale_multiplier == 3.5

    def test_stale_multiplier_at_minimum(self):
        """Test stale multiplier at minimum boundary (1.0)."""
        params = RoutineAlertParams(stale_multiplier=1.0)
        assert params.stale_multiplier == 1.0

    def test_stale_multiplier_at_maximum(self):
        """Test stale multiplier at maximum boundary (10.0)."""
        params = RoutineAlertParams(stale_multiplier=10.0)
        assert params.stale_multiplier == 10.0

    def test_stale_multiplier_below_minimum(self):
        """Test stale multiplier below minimum raises error."""
        with pytest.raises(ValidationError) as exc_info:
            RoutineAlertParams(stale_multiplier=0.5)
        
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_stale_multiplier_above_maximum(self):
        """Test stale multiplier above maximum raises error."""
        with pytest.raises(ValidationError) as exc_info:
            RoutineAlertParams(stale_multiplier=15.0)
        
        assert "less than or equal to 10" in str(exc_info.value)

    def test_valid_min_stale_seconds(self):
        """Test valid min_stale_seconds values."""
        params = RoutineAlertParams(min_stale_seconds=7200)
        assert params.min_stale_seconds == 7200

    def test_min_stale_seconds_at_minimum(self):
        """Test min_stale_seconds at minimum boundary (60)."""
        params = RoutineAlertParams(min_stale_seconds=60)
        assert params.min_stale_seconds == 60

    def test_min_stale_seconds_at_maximum(self):
        """Test min_stale_seconds at maximum boundary (86400)."""
        params = RoutineAlertParams(min_stale_seconds=86400)
        assert params.min_stale_seconds == 86400

    def test_min_stale_seconds_below_minimum(self):
        """Test min_stale_seconds below minimum raises error."""
        with pytest.raises(ValidationError) as exc_info:
            RoutineAlertParams(min_stale_seconds=30)
        
        assert "greater than or equal to 60" in str(exc_info.value)

    def test_min_stale_seconds_above_maximum(self):
        """Test min_stale_seconds above maximum raises error."""
        with pytest.raises(ValidationError) as exc_info:
            RoutineAlertParams(min_stale_seconds=100000)
        
        assert "less than or equal to 86400" in str(exc_info.value)

    def test_combined_params(self):
        """Test both parameters together."""
        params = RoutineAlertParams(stale_multiplier=3.0, min_stale_seconds=1800)
        assert params.stale_multiplier == 3.0
        assert params.min_stale_seconds == 1800

    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        params = RoutineAlertParams(
            stale_multiplier=3.0,
            unknown_param="ignored"
        )
        assert params.stale_multiplier == 3.0
        assert not hasattr(params, "unknown_param")


class TestStatusTransitionRequest:
    """Tests for StatusTransitionRequest body parameter model."""

    def test_valid_transition(self):
        """Test valid status transition request."""
        request = StatusTransitionRequest(
            from_status="in_progress",
            to_status="done"
        )
        assert request.from_status == "in_progress"
        assert request.to_status == "done"

    def test_both_fields_required(self):
        """Test that both fields are required."""
        with pytest.raises(ValidationError) as exc_info:
            StatusTransitionRequest(from_status="in_progress")
        
        assert "to_status" in str(exc_info.value)

    def test_empty_from_status(self):
        """Test empty from_status raises error."""
        with pytest.raises(ValidationError) as exc_info:
            StatusTransitionRequest(from_status="", to_status="done")
        
        error_msg = str(exc_info.value).lower()
        assert "at least 1 character" in error_msg or "whitespace" in error_msg or "empty" in error_msg

    def test_empty_to_status(self):
        """Test empty to_status raises error."""
        with pytest.raises(ValidationError) as exc_info:
            StatusTransitionRequest(from_status="in_progress", to_status="")
        
        error_msg = str(exc_info.value).lower()
        assert "at least 1 character" in error_msg or "whitespace" in error_msg or "empty" in error_msg

    def test_whitespace_only_from_status(self):
        """Test whitespace-only from_status raises error."""
        with pytest.raises(ValidationError) as exc_info:
            StatusTransitionRequest(from_status="   ", to_status="done")
        
        assert "whitespace" in str(exc_info.value).lower()

    def test_whitespace_only_to_status(self):
        """Test whitespace-only to_status raises error."""
        with pytest.raises(ValidationError) as exc_info:
            StatusTransitionRequest(from_status="in_progress", to_status="   ")
        
        assert "whitespace" in str(exc_info.value).lower()

    def test_from_status_trimmed(self):
        """Test that from_status is trimmed of whitespace."""
        request = StatusTransitionRequest(
            from_status="  in_progress  ",
            to_status="done"
        )
        assert request.from_status == "in_progress"

    def test_to_status_trimmed(self):
        """Test that to_status is trimmed of whitespace."""
        request = StatusTransitionRequest(
            from_status="in_progress",
            to_status="  done  "
        )
        assert request.to_status == "done"

    def test_status_max_length(self):
        """Test status at max length boundary."""
        long_status = "a" * 50
        request = StatusTransitionRequest(
            from_status=long_status,
            to_status="done"
        )
        assert request.from_status == long_status

    def test_status_exceeds_max_length(self):
        """Test status exceeding max length raises error."""
        with pytest.raises(ValidationError) as exc_info:
            StatusTransitionRequest(
                from_status="a" * 51,
                to_status="done"
            )
        
        assert "50" in str(exc_info.value)

    def test_various_status_values(self):
        """Test various valid status values."""
        statuses = [
            ("todo", "in_progress"),
            ("in_progress", "in_review"),
            ("in_review", "done"),
            ("blocked", "in_progress"),
            ("backlog", "todo"),
        ]
        
        for from_s, to_s in statuses:
            request = StatusTransitionRequest(from_status=from_s, to_status=to_s)
            assert request.from_status == from_s
            assert request.to_status == to_s
