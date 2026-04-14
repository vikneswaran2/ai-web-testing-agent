# agent/enhanced_graph.py

import logging
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from .enhanced_executor import EnhancedExecutor
from .enhanced_parser import EnhancedInstructionParser
from .reporter import Reporter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

_EMPTY_EXEC_RESULT: Dict[str, Any] = {
    "success": False,
    "logs": [],
    "screenshots": [],
    "video": None,
    "console_logs": [],
    "variables": {},
    "healing_stats": None,
    "error_stats": {},
}


def _failed_exec_result(error: Exception) -> Dict[str, Any]:
    """Return a fully-keyed execution result representing a fatal error."""
    result = dict(_EMPTY_EXEC_RESULT)
    result["logs"] = [f"[FATAL ERROR] {error}"]
    return result


def _failed_report_result(error: Exception) -> Dict[str, Any]:
    return {
        "html_report": None,
        "json_report": None,
        "pdf_report": None,
        "error": str(error),
    }


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class EnhancedBatchState(BaseModel):
    """State for enhanced batch processing."""

    instructions: List[str] = Field(default_factory=list)
    settings: Optional[Dict[str, Any]] = None
    parsed_sets: List[Any] = Field(default_factory=list)
    # Parallel list to parsed_sets: None entry = instruction failed to parse
    parse_errors: List[Optional[str]] = Field(default_factory=list)
    exec_results: List[Any] = Field(default_factory=list)
    reports: List[Any] = Field(default_factory=list)
    use_ai_parsing: bool = True


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_enhanced_batch_graph():
    """
    Build and compile the enhanced batch-processing graph.

    The compiled graph is safe for sequential invocations.  It is NOT safe
    for concurrent invocations because EnhancedInstructionParser and Reporter
    are instantiated fresh inside each node call — but EnhancedExecutor
    is also fresh per test, so no cross-test state leaks.

    Returns:
        A compiled LangGraph graph ready for `.invoke()`.
    """
    workflow = StateGraph(state_schema=EnhancedBatchState)

    # ------------------------------------------------------------------
    # Node: parse_batch
    # ------------------------------------------------------------------
    def parse_batch_node(state: EnhancedBatchState) -> Dict[str, Any]:
        """Parse all instructions using the enhanced parser."""
        # Fresh instance per invocation to avoid shared mutable state.
        parser = EnhancedInstructionParser()

        parsed_sets: List[Any] = []
        parse_errors: List[Optional[str]] = []

        for i, test in enumerate(state.instructions):
            parsed = None
            error_msg: Optional[str] = None

            # Try AI parsing first, fall back to pattern-based.
            for use_ai in ([True, False] if state.use_ai_parsing else [False]):
                try:
                    parsed = parser.parse(test, use_ai=use_ai)
                    break  # Success — stop trying
                except Exception as exc:
                    label = "AI" if use_ai else "pattern-based"
                    logger.warning(
                        "Instruction %d/%d: %s parsing failed: %s",
                        i + 1,
                        len(state.instructions),
                        label,
                        exc,
                    )
                    error_msg = str(exc)

            parsed_sets.append(parsed)       # None if both strategies failed
            parse_errors.append(error_msg if parsed is None else None)

        return {"parsed_sets": parsed_sets, "parse_errors": parse_errors}

    # ------------------------------------------------------------------
    # Node: execute_all
    # ------------------------------------------------------------------
    def execute_all_node(state: EnhancedBatchState) -> Dict[str, Any]:
        """Execute all parsed action sets."""
        exec_results: List[Any] = []

        for i, (actions, parse_error) in enumerate(
            zip(state.parsed_sets, state.parse_errors)
        ):
            logger.info(
                "[EXECUTING TEST %d/%d]", i + 1, len(state.parsed_sets)
            )

            # If parsing failed, emit a structured failure immediately.
            if actions is None:
                result = _failed_exec_result(
                    RuntimeError(f"Skipped — parse error: {parse_error}")
                )
                exec_results.append(result)
                continue

            # Fresh executor per test — no shared mutable state between tests.
            executor = EnhancedExecutor()
            try:
                result = executor.execute_actions(
                    actions, settings=state.settings
                )
            except Exception as exc:
                logger.exception("Test %d: unexpected execution error", i + 1)
                result = _failed_exec_result(exc)

            exec_results.append(result)

        return {"exec_results": exec_results}

    # ------------------------------------------------------------------
    # Node: generate_reports
    # ------------------------------------------------------------------
    def generate_reports_node(state: EnhancedBatchState) -> Dict[str, Any]:
        """Generate reports for all execution results."""
        # Fresh instance per invocation.
        reporter = Reporter()
        reports: List[Any] = []

        for i, result in enumerate(state.exec_results):
            test_id = f"ID-{i + 1:03d}"
            try:
                html, js, pdf = reporter.generate_report(result, test_id=test_id)
                reports.append(
                    {
                        "test_id": test_id,
                        "html_report": html,
                        "json_report": js,
                        "pdf_report": pdf,
                    }
                )
            except Exception as exc:
                logger.exception("Test %s: report generation failed", test_id)
                reports.append(
                    {"test_id": test_id, **_failed_report_result(exc)}
                )

        return {"reports": reports}

    # ------------------------------------------------------------------
    # Wire the graph
    # ------------------------------------------------------------------
    workflow.add_node("parse_batch", parse_batch_node)
    workflow.add_node("execute_all", execute_all_node)
    workflow.add_node("generate_reports", generate_reports_node)

    workflow.set_entry_point("parse_batch")
    workflow.add_edge("parse_batch", "execute_all")
    workflow.add_edge("execute_all", "generate_reports")
    workflow.add_edge("generate_reports", END)

    # compile() is required before the graph can be invoked.
    return workflow.compile()


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------

def build_batch_graph():
    """Alias for backward compatibility. Delegates to build_enhanced_batch_graph()."""
    return build_enhanced_batch_graph()