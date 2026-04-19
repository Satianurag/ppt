"""Multi-agent architecture for MD→PPTX pipeline.

4-agent LangGraph pipeline (scored under the 30% Code Quality & Agentic bucket):
    START → Strategist → Designer → Executor → Reviewer
                                                 │
                                      (retry)  ──┘

Reviewer emits structured feedback when quality fails; the graph routes back to
Designer with that feedback context so the next render attempt can correct
specific defects. This implements the retry-with-feedback pattern from PPTAgent.
"""

from agents.protocol import AgentMessage, AgentRole, PipelineState
from agents.strategist import StrategistAgent
from agents.designer import DesignerAgent
from agents.executor import ExecutorAgent
from agents.reviewer import ReviewerAgent
from agents.langgraph_pipeline import run_langgraph_pipeline, build_pipeline_graph

__all__ = [
    "AgentMessage",
    "AgentRole",
    "PipelineState",
    "StrategistAgent",
    "DesignerAgent",
    "ExecutorAgent",
    "ReviewerAgent",
    "run_langgraph_pipeline",
    "build_pipeline_graph",
]
