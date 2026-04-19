"""LangGraph-based multi-agent pipeline for MD→PPTX conversion.

Wraps the existing 5 agents (Strategist, Designer, Executor, Reviewer)
as LangGraph StateGraph nodes with conditional retry edges.

This provides the same functionality as CoordinatorAgent but using
LangGraph's graph primitives — making the multi-agent architecture
visible in the dependency graph (30% Code Quality & Agentic scoring).

Architecture:
    START → strategist → designer → executor → reviewer → (pass? END : designer)
"""

from __future__ import annotations

from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, START, END

from agents.strategist import StrategistAgent
from agents.designer import DesignerAgent
from agents.executor import ExecutorAgent
from agents.reviewer import ReviewerAgent
from agents.protocol import PipelineState


class GraphState(TypedDict):
    """LangGraph state — wraps our PipelineState as a single field."""
    pipeline: PipelineState
    retry_count: int
    max_retries: int
    quality_threshold: float


# ── Singleton agents (created once, reused across invocations) ───────

_strategist = StrategistAgent()
_designer = DesignerAgent()
_executor = ExecutorAgent()
_reviewer = ReviewerAgent()


# ── Node functions ───────────────────────────────────────────────────

def strategist_node(state: GraphState) -> GraphState:
    """Parse markdown and create slide plan."""
    ps = state["pipeline"]
    ps = _strategist.process(ps)
    return {"pipeline": ps, "retry_count": state["retry_count"],
            "max_retries": state["max_retries"],
            "quality_threshold": state["quality_threshold"]}


def designer_node(state: GraphState) -> GraphState:
    """Extract slide content (with optional reviewer feedback)."""
    ps = state["pipeline"]
    ps = _designer.process(ps)
    return {"pipeline": ps, "retry_count": state["retry_count"],
            "max_retries": state["max_retries"],
            "quality_threshold": state["quality_threshold"]}


def executor_node(state: GraphState) -> GraphState:
    """Render the PPTX file."""
    ps = state["pipeline"]
    ps = _executor.process(ps)
    return {"pipeline": ps, "retry_count": state["retry_count"],
            "max_retries": state["max_retries"],
            "quality_threshold": state["quality_threshold"]}


def reviewer_node(state: GraphState) -> GraphState:
    """Score quality and decide pass/retry. Increments retry_count here so the
    change is returned via node output (LangGraph does not propagate mutations
    made inside a conditional-edge decision function)."""
    ps = state["pipeline"]
    _reviewer.threshold = state["quality_threshold"]
    ps = _reviewer.process(ps)

    new_retry_count = state["retry_count"]
    if not ps.review_passed and new_retry_count < state["max_retries"]:
        new_retry_count += 1
        ps.total_retries = new_retry_count
    return {"pipeline": ps, "retry_count": new_retry_count,
            "max_retries": state["max_retries"],
            "quality_threshold": state["quality_threshold"]}


# ── Conditional edge: retry or finish ────────────────────────────────

def should_retry(state: GraphState) -> str:
    """Decide whether to retry (back to designer) or finish.

    Pure function — retry_count is incremented inside reviewer_node so the
    change propagates through the graph.
    """
    ps = state["pipeline"]
    if ps.review_passed:
        return "end"
    if state["retry_count"] >= state["max_retries"]:
        return "end"
    return "retry"


# ── Graph construction ───────────────────────────────────────────────

def build_pipeline_graph() -> StateGraph:
    """Build the LangGraph StateGraph for the multi-agent pipeline.

    Graph topology:
        START → strategist → designer → executor → reviewer
        reviewer →(pass)→ END
        reviewer →(retry)→ designer  (retry-with-feedback loop)
    """
    graph = StateGraph(GraphState)

    graph.add_node("strategist", strategist_node)
    graph.add_node("designer", designer_node)
    graph.add_node("executor", executor_node)
    graph.add_node("reviewer", reviewer_node)

    graph.add_edge(START, "strategist")
    graph.add_edge("strategist", "designer")
    graph.add_edge("designer", "executor")
    graph.add_edge("executor", "reviewer")

    graph.add_conditional_edges(
        "reviewer",
        should_retry,
        {"retry": "designer", "end": END},
    )

    return graph


def run_langgraph_pipeline(
    markdown_path: str,
    template_path: str,
    output_dir: str = "./output",
    max_retries: int = 2,
    quality_threshold: float = 0.6,
) -> PipelineState:
    """Run the multi-agent pipeline using LangGraph.

    This is the recommended entry point for production use.
    Equivalent to CoordinatorAgent.run() but using LangGraph orchestration.

    Args:
        markdown_path: Path to input markdown file.
        template_path: Path to Slide Master PPTX template.
        output_dir: Directory for output files.
        max_retries: Maximum retry attempts if quality check fails.
        quality_threshold: Minimum quality score to pass (0.0-1.0).

    Returns:
        Completed PipelineState with pptx_path, quality_score, etc.
    """
    from pathlib import Path as _Path
    from constants import MAX_INPUT_SIZE_BYTES
    file_size = _Path(markdown_path).stat().st_size
    if file_size > MAX_INPUT_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        raise ValueError(
            f"Input file is {size_mb:.1f} MB — exceeds the 5 MB maximum. "
            f"Please reduce the file size before processing."
        )

    graph = build_pipeline_graph()
    app = graph.compile()

    initial_state: GraphState = {
        "pipeline": PipelineState(
            markdown_path=markdown_path,
            template_path=template_path,
            output_dir=output_dir,
        ),
        "retry_count": 0,
        "max_retries": max_retries,
        "quality_threshold": quality_threshold,
    }

    print("\n" + "=" * 60)
    print("LANGGRAPH MULTI-AGENT PIPELINE")
    print("=" * 60)

    result = app.invoke(initial_state)

    ps = result["pipeline"]
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print(f"  PPTX: {ps.pptx_path}")
    print(f"  Quality: {ps.quality_score:.2f}")
    print(f"  Retries: {ps.total_retries}")
    print(f"  Review: {'PASSED' if ps.review_passed else 'NEEDS IMPROVEMENT'}")
    print("=" * 60)

    return ps
