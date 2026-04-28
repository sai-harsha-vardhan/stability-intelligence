"""
Pydantic models for query parameter validation.

These models provide structured validation for FastAPI query parameters,
ensuring type safety and proper constraints before processing.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class IssueFilterParams(BaseModel):
    """Query parameters for issue filtering endpoint.

    Validated parameters for filtering issues by wave, status, label, or parent.
    All fields are optional - omit to skip that filter.
    """

    model_config = {"extra": "ignore"}

    wave: Literal["wave-1", "wave-2", "wave-3", "wave-4"] | None = Field(
        default=None,
        description="Wave label, e.g. wave-1",
    )
    status: str | None = Field(
        default=None,
        description="Exact status string",
        max_length=50,
    )
    label: str | None = Field(
        default=None,
        description="Any label to match",
        max_length=100,
    )
    parent: str | None = Field(
        default=None,
        description="Parent issue ID",
        max_length=100,
    )

    @field_validator("status")
    @classmethod
    def validate_status_not_empty(cls, v: str | None) -> str | None:
        """Ensure status is not empty string if provided."""
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Status cannot be empty string")
        return v

    @field_validator("label")
    @classmethod
    def validate_label_not_empty(cls, v: str | None) -> str | None:
        """Ensure label is not empty string if provided."""
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Label cannot be empty string")
        return v

    @field_validator("parent")
    @classmethod
    def validate_parent_not_empty(cls, v: str | None) -> str | None:
        """Ensure parent is not empty string if provided."""
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Parent cannot be empty string")
        return v


class RoutineAlertParams(BaseModel):
    """Query parameters for routine alerts endpoint.

    Controls sensitivity and thresholds for detecting stale routine executions.
    """

    model_config = {"extra": "ignore"}

    stale_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=10.0,
        description="How many intervals before considering a routine stale",
    )
    min_stale_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Minimum stale threshold in seconds (1 min to 24 hours)",
    )


class StatusTransitionRequest(BaseModel):
    """Request body for status transition validation.

    Validates a proposed status transition before applying it.
    """

    from_status: str = Field(
        ...,  # Required
        description="Current status of the issue",
        min_length=1,
        max_length=50,
    )
    to_status: str = Field(
        ...,  # Required
        description="Proposed new status",
        min_length=1,
        max_length=50,
    )

    @field_validator("from_status", "to_status")
    @classmethod
    def validate_status_not_whitespace_only(cls, v: str) -> str:
        """Ensure status values are not whitespace-only."""
        if not v.strip():
            raise ValueError("Status cannot be whitespace-only")
        return v.strip()
