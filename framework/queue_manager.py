from __future__ import annotations

import asyncio
from typing import Dict

from framework.case_parser import build_serialized_cases
from framework.executor import run_pytest_task
from framework.models import (
    SerializedTask,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskDetailResponse,
    TaskRecord,
    TaskResult,
    TaskStatus,
)


class TaskQueueManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._tasks: Dict[str, TaskRecord] = {}
        self._worker: asyncio.Task | None = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run_worker(), name="pytest-task-worker")

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    def create_task(self, request: TaskCreateRequest) -> TaskCreateResponse:
        task = TaskRecord(request=request)
        task.append_log("任务已入队", "queue", "queued")
        self._tasks[task.task_id] = task
        self._queue.put_nowait(task.task_id)
        return TaskCreateResponse(task_id=task.task_id, status=task.status)

    def list_tasks(self) -> Dict[str, TaskRecord]:
        return self._tasks

    def get_task(self, task_id: str) -> TaskDetailResponse:
        if task_id not in self._tasks:
            raise KeyError(task_id)
        task = self._tasks[task_id]
        return TaskDetailResponse(
            task_id=task.task_id,
            status=task.status,
            logs=task.logs,
            result=task.result,
            error=task.error,
        )

    async def _run_worker(self) -> None:
        while True:
            task_id = await self._queue.get()
            task = self._tasks[task_id]
            task.status = TaskStatus.RUNNING
            task.append_log("开始执行任务", "pytest", "running")
            try:
                payload = SerializedTask(
                    task_id=task.task_id,
                    url=task.request.url,
                    username=task.request.username,
                    password=task.request.password,
                    test_cases=build_serialized_cases(
                        task.request.test_cases,
                        {
                            "url": task.request.url,
                            "username": task.request.username,
                            "password": task.request.password,
                        },
                    ),
                )
                result, logs, error = await asyncio.to_thread(run_pytest_task, payload)
                task.result = result
                task.logs.extend(logs)
                task.status = TaskStatus.FAILED if error or result.failed > 0 else TaskStatus.FINISHED
                if error:
                    task.error = error
                    task.append_log("任务执行异常", "pytest", "failed", error)
                else:
                    task.append_log(
                        "任务执行完成",
                        "pytest",
                        "success" if result.failed == 0 else "failed",
                        f"passed={result.passed}, failed={result.failed}",
                    )
            except Exception as exc:  # noqa: BLE001
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                task.result = TaskResult(total=0, passed=0, failed=0, case_results=[])
                task.append_log("任务运行崩溃", "worker", "failed", str(exc))
            finally:
                self._queue.task_done()
