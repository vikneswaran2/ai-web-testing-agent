# agent/graph.py

import logging
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from .reporter import Reporter

# ---------------------------------------------------------------------------
# Conditional imports with capability flag
# ---------------------------------------------------------------------------

try:
    from .enhanced_parser import EnhancedInstructionParser as InstructionParser
    _PARSER_SUPPORTS_AI = True
except ImportError:
    from .parser import InstructionParser          # type: ignore[assignment]
    _PARSER_SUPPORTS_AI = False

try:
    from .enhanced_executor import EnhancedExecutor as Executor
except ImportError:
    from .executor import Executor                 # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result helpers (mirrors enhanced_graph.py for consistency)
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

class BatchState(BaseModel):
    """State passed between LangGraph nodes."""

    instructions: List[str] = Field(default_factory=list)
    settings: Optional[Dict[str, Any]] = None
    parsed_sets: List[Any] = Field(default_factory=list)
    parse_errors: List[Optional[str]] = Field(default_factory=list)
    exec_results: List[Any] = Field(default_factory=list)
    reports: List[Any] = Field(default_factory=list)
    use_ai_parsing: bool = True


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_batch_graph():
    """
    Build and compile the batch-processing graph.

    Returns a compiled LangGraph graph ready for `.invoke()`.
    """
    workflow = StateGraph(state_schema=BatchState)

    # ------------------------------------------------------------------
    # Node: parse_batch
    # ------------------------------------------------------------------
    def parse_batch_node(state: BatchState) -> Dict[str, Any]:
        # Fresh parser per invocation — no shared mutable state.
        parser = InstructionParser()

        parsed_sets: List[Any] = []
        parse_errors: List[Optional[str]] = []

        for i, test in enumerate(state.instructions):
            parsed = None
            error_msg: Optional[str] = None

            # Build the list of strategies to attempt
            if _PARSER_SUPPORTS_AI and state.use_ai_parsing:
                strategies = [True, False]   # AI first, pattern fallback
            else:
                strategies = [False]         # Pattern only

            for use_ai in strategies:
                try:
                    if _PARSER_SUPPORTS_AI:
                        parsed = parser.parse(test, use_ai=use_ai)
                    else:
                        parsed = parser.parse(test)
                    break
                except Exception as exc:
                    label = "AI" if use_ai else "pattern-based"
                    logger.warning(
                        "Instruction %d/%d: %s parsing failed: %s",
                        i + 1, len(state.instructions), label, exc,
                    )
                    error_msg = str(exc)

            parsed_sets.append(parsed)
            parse_errors.append(error_msg if parsed is None else None)

        return {"parsed_sets": parsed_sets, "parse_errors": parse_errors}

    # ------------------------------------------------------------------
    # Node: execute_all
    # ------------------------------------------------------------------
    def execute_all_node(state: BatchState) -> Dict[str, Any]:
        exec_results: List[Any] = []

        for i, (actions, parse_error) in enumerate(
            zip(state.parsed_sets, state.parse_errors)
        ):
            logger.info("[EXECUTING TEST %d/%d]", i + 1, len(state.parsed_sets))

            if actions is None:
                exec_results.append(
                    _failed_exec_result(
                        RuntimeError(f"Skipped — parse error: {parse_error}")
                    )
                )
                continue

            executor = Executor()
            try:
                result = executor.execute_actions(actions, settings=state.settings)
            except Exception as exc:
                logger.exception("Test %d: unexpected execution error", i + 1)
                result = _failed_exec_result(exc)

            exec_results.append(result)

        return {"exec_results": exec_results}

    # ------------------------------------------------------------------
    # Node: generate_reports
    # ------------------------------------------------------------------
    def generate_reports_node(state: BatchState) -> Dict[str, Any]:
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
                reports.append({"test_id": test_id, **_failed_report_result(exc)})

        return {"reports": reports}

    # ------------------------------------------------------------------
    # Wire and compile
    # ------------------------------------------------------------------
    workflow.add_node("parse_batch", parse_batch_node)
    workflow.add_node("execute_all", execute_all_node)
    workflow.add_node("generate_reports", generate_reports_node)

    workflow.set_entry_point("parse_batch")
    workflow.add_edge("parse_batch", "execute_all")
    workflow.add_edge("execute_all", "generate_reports")
    workflow.add_edge("generate_reports", END)

    return workflow.compile()