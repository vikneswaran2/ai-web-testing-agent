# agent/graph.py

from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from typing import Any, Optional

from .parser import InstructionParser
from .executor import Executor
from .reporter import Reporter


class SingleState(BaseModel):
    instruction: str = ""
    actions: Optional[Any] = None
    exec_result: Optional[Any] = None
    report: Optional[Any] = None
    error: Optional[str] = None


def build_graph():

    workflow = StateGraph(state_schema=SingleState)

    parser = InstructionParser()
    executor = Executor()
    reporter = Reporter()

    def parse_node(state: SingleState) -> dict:
        try:
            actions = parser.parse(state.instruction)
            return {"actions": actions}
        except Exception as e:
            return {"error": f"Parse error: {str(e)}"}

    def execute_node(state: SingleState) -> dict:
        if state.error:
            return {}  # Skip execution if a prior error occurred
        try:
            exec_result = executor.execute_actions(state.actions)
            return {"exec_result": exec_result}
        except Exception as e:
            return {"error": f"Execution error: {str(e)}"}

    def report_node(state: SingleState) -> dict:
        if state.error:
            return {"report": {"status": "failed", "reason": state.error}}
        try:
            report = reporter.generate_report(state.exec_result, test_id="single_test")
            return {"report": report}
        except Exception as e:
            return {"report": {"status": "failed", "reason": f"Report error: {str(e)}"}}

    workflow.add_node("parse", parse_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("report", report_node)

    workflow.set_entry_point("parse")
    workflow.add_edge("parse", "execute")
    workflow.add_edge("execute", "report")
    workflow.add_edge("report", END)

    return workflow.compile()  # Compile the graph before returning