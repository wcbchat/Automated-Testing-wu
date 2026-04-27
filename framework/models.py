from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


class CaseStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class StepInput(BaseModel):
    action: str
    selector: Optional[str] = None
    value: Optional[str] = None
    expected: Optional[str] = None
    timeout_ms: int = 5000


class TestCaseInput(BaseModel):
    case_name: str
    precondition: str = ""
    test_steps: List[str] = Field(default_factory=list)
    expected_result: str
    steps: List[StepInput] = Field(default_factory=list)


class TaskCreateRequest(BaseModel):
    url: str
    username: str
    password: str
    test_cases: List[TestCaseInput] = Field(default_factory=list)


class StepLog(BaseModel):
    timestamp: str
    step: str
    tool: str
    status: str
    details: Optional[str] = None


class CaseResult(BaseModel):
    name: str
    status: CaseStatus
    expected: str
    actual: str
    error: Optional[str] = None


class TaskResult(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    case_results: List[CaseResult] = Field(default_factory=list)


class TaskRecord(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    status: TaskStatus = TaskStatus.QUEUED
    request: TaskCreateRequest
    logs: List[StepLog] = Field(default_factory=list)
    result: Optional[TaskResult] = None
    error: Optional[str] = None

    def append_log(
        self,
        step: str,
        tool: str,
        status: str,
        details: Optional[str] = None,
    ) -> None:
        self.logs.append(
            StepLog(
                timestamp=datetime.utcnow().isoformat(),
                step=step,
                tool=tool,
                status=status,
                details=details,
            )
        )


class TaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatus


class TaskDetailResponse(BaseModel):
    task_id: str
    status: TaskStatus
    logs: List[StepLog]
    result: Optional[TaskResult]
    error: Optional[str] = None


class SerializedTask(BaseModel):
    """Payload passed to pytest."""

    task_id: str
    url: str
    username: str
    password: str
    test_cases: List[Dict[str, Any]]
