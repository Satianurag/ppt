"""Agent communication protocol — structured messages between agents.

Inspired by PPTAgent's Turn-based conversation + PPT Master's role separation.
Each agent sends/receives AgentMessage objects with typed payloads.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime, timezone

if TYPE_CHECKING:
    from step1.models import ContentInventory
    from step2.slide_plan_models import PresentationPlan
    from step3.content_models import PresentationContent


class AgentRole(str, Enum):
    """Agent roles in the pipeline."""
    COORDINATOR = "coordinator"
    STRATEGIST = "strategist"
    DESIGNER = "designer"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"


class MessageType(str, Enum):
    """Types of inter-agent messages."""
    REQUEST = "request"
    RESPONSE = "response"
    FEEDBACK = "feedback"
    ERROR = "error"
    STATUS = "status"


@dataclass
class AgentMessage:
    """Structured message passed between agents.

    Follows PPTAgent's retry-with-feedback pattern where downstream agents
    can send feedback messages upstream to trigger retries.
    """
    sender: AgentRole
    receiver: AgentRole
    msg_type: MessageType
    payload: Any
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    turn_id: int = 0
    retry_count: int = 0

    def as_feedback(self, feedback_text: str) -> "AgentMessage":
        """Create a feedback message back to the sender."""
        return AgentMessage(
            sender=self.receiver,
            receiver=self.sender,
            msg_type=MessageType.FEEDBACK,
            payload={"original": self.payload, "feedback": feedback_text},
            turn_id=self.turn_id,
            retry_count=self.retry_count + 1,
        )


@dataclass
class PipelineState:
    """Shared state passed through the multi-agent pipeline.

    Each agent reads from and writes to this state object,
    enabling transparent communication without tight coupling.
    """
    # Input
    markdown_path: str = ""
    template_path: str = ""
    output_dir: str = "./output"
    output_path: str = ""
    presenter: str = ""
    presentation_date: str = ""

    # Step 1 output (Strategist)
    inventory: ContentInventory | None = None
    slide_plan: PresentationPlan | None = None

    # Step 2 output (Designer)
    presentation_content: PresentationContent | None = None

    # Step 3 output (Executor)
    pptx_path: str | None = None
    render_issues: list[str] = field(default_factory=list)

    # Step 4 output (Reviewer)
    quality_score: float = 0.0
    quality_report: str = ""
    review_passed: bool = False
    review_feedback: str = ""

    # Pipeline metadata
    messages: list[AgentMessage] = field(default_factory=list)
    total_retries: int = 0
    max_retries: int = 2

    def log_message(self, msg: AgentMessage) -> None:
        """Record a message in the pipeline history."""
        self.messages.append(msg)

    def get_messages_for(self, role: AgentRole) -> list[AgentMessage]:
        """Get all messages sent to a specific agent."""
        return [m for m in self.messages if m.receiver == role]
