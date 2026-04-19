"""Base agent class — all pipeline agents inherit from this.

Adapted from PPTAgent's Agent class (pptagent/agent.py:55-232).
Simplified for our synchronous pipeline (no async needed).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from agents.protocol import AgentMessage, AgentRole, MessageType, PipelineState


@dataclass
class AgentTurn:
    """Record of one agent execution turn.

    Adapted from PPTAgent's Turn dataclass (agent.py:24-53).
    """
    turn_id: int
    agent_role: AgentRole
    input_summary: str
    output_summary: str
    retry_count: int = 0
    success: bool = True
    error: str | None = None


class BaseAgent(ABC):
    """Base class for all pipeline agents.

    Each agent has:
    - A role (AgentRole enum)
    - A process() method that reads/writes PipelineState
    - Turn history for debugging
    - Retry-with-feedback support (PPTAgent pattern)
    """

    def __init__(self, role: AgentRole, name: str) -> None:
        self.role = role
        self.name = name
        self._history: list[AgentTurn] = []
        self._turn_counter = 0

    @property
    def next_turn_id(self) -> int:
        self._turn_counter += 1
        return self._turn_counter

    @property
    def history(self) -> list[AgentTurn]:
        return sorted(self._history, key=lambda t: t.turn_id)

    @abstractmethod
    def process(self, state: PipelineState) -> PipelineState:
        """Execute this agent's role on the pipeline state.

        Args:
            state: Current pipeline state with all accumulated data.

        Returns:
            Updated pipeline state.
        """
        ...

    def record_turn(
        self,
        input_summary: str,
        output_summary: str,
        retry_count: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> AgentTurn:
        """Record an execution turn in history."""
        turn = AgentTurn(
            turn_id=self.next_turn_id,
            agent_role=self.role,
            input_summary=input_summary,
            output_summary=output_summary,
            retry_count=retry_count,
            success=success,
            error=error,
        )
        self._history.append(turn)
        return turn

    def send_message(
        self,
        state: PipelineState,
        receiver: AgentRole,
        msg_type: MessageType,
        payload: object,
    ) -> AgentMessage:
        """Send a message to another agent via the pipeline state."""
        msg = AgentMessage(
            sender=self.role,
            receiver=receiver,
            msg_type=msg_type,
            payload=payload,
        )
        state.log_message(msg)
        return msg

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(role={self.role.value}, name={self.name})"
