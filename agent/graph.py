"""LangGraph StateGraph wiring for the research agent."""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent.state import ResearchState
from agent.nodes.planner import planner_node
from agent.nodes.worker import worker_node
from agent.nodes.synthesizer import synthesizer_node
from agent.nodes.critic import critic_node
from config import settings

logger = logging.getLogger(__name__)


def _should_continue(state: ResearchState) -> Literal["planner", "__end__"]:
    """
    Route from the critic node.

    If the critique says refinement is needed AND we haven't hit max iterations,
    loop back to planner. Otherwise, end the graph.
    """
    critique = state.get("critique")
    if critique and critique.needs_refinement:
        iteration = state.get("iteration", 1)
        max_iterations = state.get("max_iterations", 3)
        if iteration < max_iterations:
            logger.info(f"Routing back to planner (iteration {iteration}/{max_iterations})")
            return "planner"
    return "__end__"


def build_graph() -> StateGraph:
    """
    Build the research agent graph.

    Flow:
        planner -> worker -> synthesizer -> critic
        critic -> planner (if needs refinement & under max iterations)
        critic -> END (otherwise)
    """
    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("planner", planner_node)
    graph.add_node("worker", worker_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("critic", critic_node)

    # Set entry point
    graph.set_entry_point("planner")

    # Define edges
    # Planner -> Worker (sequential, worker handles all sub-queries from the plan)
    graph.add_edge("planner", "worker")

    # Worker -> Synthesizer
    graph.add_edge("worker", "synthesizer")

    # Synthesizer -> Critic
    graph.add_edge("synthesizer", "critic")

    # Critic -> conditional: back to planner or end
    graph.add_conditional_edges(
        "critic",
        _should_continue,
        {
            "planner": "planner",
            "__end__": END,
        },
    )

    return graph


async def create_runnable(checkpointer: AsyncSqliteSaver | None = None):
    """
    Compile the graph into a runnable with optional checkpoint persistence.
    """
    graph = build_graph()

    if checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)
    else:
        compiled = graph.compile()

    return compiled


async def get_checkpointer() -> AsyncSqliteSaver:
    """Create an async SQLite checkpointer for state persistence."""
    return AsyncSqliteSaver.from_conn_string(settings.sqlite_checkpoint_path)
