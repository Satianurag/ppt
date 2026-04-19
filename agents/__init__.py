"""Multi-agent architecture for MD→PPTX pipeline.

5-agent system (30% of hackathon score — Code Quality & Agentic):
  Coordinator → Strategist → Designer → Executor → Reviewer

Orchestration modes:
  1. CoordinatorAgent — pure-Python orchestration with retry loop
  2. LangGraph StateGraph — graph-based orchestration with conditional edges

Each agent has a clear role, communicates via structured AgentMessage objects,
and follows the retry-with-feedback pattern from PPTAgent.
"""

from agents.protocol import AgentMessage, AgentRole, PipelineState
from agents.coordinator import CoordinatorAgent
from agents.strategist import StrategistAgent
from agents.designer import DesignerAgent
from agents.executor import ExecutorAgent
from agents.reviewer import ReviewerAgent
from agents.langgraph_pipeline import run_langgraph_pipeline, build_pipeline_graph

__all__ = [
    "AgentMessage",
    "AgentRole",
    "PipelineState",
    "CoordinatorAgent",
    "StrategistAgent",
    "DesignerAgent",
    "ExecutorAgent",
    "ReviewerAgent",
    "run_langgraph_pipeline",
    "build_pipeline_graph",
]
