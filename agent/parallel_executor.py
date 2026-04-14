# agent/parallel_executor.py

from typing import Any, Optional
from .executor import Executor


class ParallelExecutor:
    """
    Windows-safe: run tests sequentially.
    Parallel Playwright is NOT supported on Windows.
    """

    def __init__(self):
        self.executor = Executor()

    def run_parallel(
        self,
        list_of_actions_sets: list[list[Any]],
        settings: Optional[Any] = None
    ) -> list[dict]:
        results = []

        for i, actions in enumerate(list_of_actions_sets):
            try:
                result = self.executor.execute_actions(actions, settings=settings)
                results.append({"status": "success", "result": result})
            except Exception as e:
                results.append({
                    "status": "failed",
                    "index": i,
                    "reason": str(e)
                })

        return results