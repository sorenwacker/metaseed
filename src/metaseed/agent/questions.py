"""Question types for user clarification during extraction."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class QuestionType(StrEnum):
    """Types of clarification questions."""

    MAPPING = "mapping"  # Which column maps to which field?
    VALUE = "value"  # What is the value for this field?
    CONFIRMATION = "confirm"  # Is this mapping correct?
    CHOICE = "choice"  # Which of these options?


class Question(BaseModel):
    """A clarification question for the user."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: QuestionType
    entity: str
    field: str | None = None
    context: str  # What the agent found
    question_text: str  # Human-readable question
    options: list[str] | None = None  # For CHOICE type
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def mapping_question(
        cls,
        entity: str,
        field: str,
        source_columns: list[str],
        context: str,
    ) -> Question:
        """Create a mapping question."""
        return cls(
            type=QuestionType.MAPPING,
            entity=entity,
            field=field,
            context=context,
            question_text=f"Which column should map to '{field}'?",
            options=source_columns,
        )

    @classmethod
    def value_question(
        cls,
        entity: str,
        field: str,
        context: str,
    ) -> Question:
        """Create a value question."""
        return cls(
            type=QuestionType.VALUE,
            entity=entity,
            field=field,
            context=context,
            question_text=f"What is the value for '{field}'?",
        )

    @classmethod
    def confirmation_question(
        cls,
        entity: str,
        field: str,
        proposed_value: str,
        context: str,
    ) -> Question:
        """Create a confirmation question."""
        return cls(
            type=QuestionType.CONFIRMATION,
            entity=entity,
            field=field,
            context=context,
            question_text=f"Is '{proposed_value}' correct for '{field}'?",
            options=["Yes", "No"],
            metadata={"proposed_value": proposed_value},
        )

    @classmethod
    def choice_question(
        cls,
        entity: str,
        field: str | None,
        choices: list[str],
        context: str,
        question_text: str,
    ) -> Question:
        """Create a choice question."""
        return cls(
            type=QuestionType.CHOICE,
            entity=entity,
            field=field,
            context=context,
            question_text=question_text,
            options=choices,
        )


class Answer(BaseModel):
    """An answer to a clarification question."""

    question_id: str
    value: str  # The answer value
    selected_option: int | None = None  # Index if answering CHOICE/MAPPING
