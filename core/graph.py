"""LangGraph orchestration: Planner → Worker → Synthesizer → Critic (with optional loop)."""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from core.state import ResearchState
from agents.planner import planner_node
from agents.worker import worker_node
from agents.synthesizer import synthesizer_node
from agents.critic import critic_node
from config import settings

logger = logging.getLogger(__name__)


def _should_continue(state: ResearchState) -> Literal["planner", "__end__"]:
    """Route from critic: loop back or end."""
    critique = state.get("critique")
    if critique and critique.needs_refinement:
        iteration = state.get("iteration", 1)
        max_iterations = state.get("max_iterations", 3)
        if iteration < max_iterations:
            logger.info("Routing back to planner (iteration %s/%s)", iteration, max_iterations)
            return "planner"
    return "__end__"


def build_graph() -> StateGraph:
    """Build the research agent StateGraph."""
    graph = StateGraph(ResearchState)
    graph.add_node("planner", planner_node)
    graph.add_node("worker", worker_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("critic", critic_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "worker")
    graph.add_edge("worker", "synthesizer")
    graph.add_edge("synthesizer", "critic")
    graph.add_conditional_edges("critic", _should_continue, {"planner": "planner", "__end__": END})
    return graph


async def create_runnable(checkpointer: AsyncSqliteSaver | None = None):
    """Compile graph with optional checkpoint persistence."""
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer) if checkpointer else graph.compile()


async def get_checkpointer() -> AsyncSqliteSaver:
    """Create async SQLite checkpointer for state persistence."""
    return AsyncSqliteSaver.from_conn_string(settings.sqlite_checkpoint_path)
