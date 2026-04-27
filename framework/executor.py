from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

from framework.models import SerializedTask, StepLog, TaskResult


BASE_DIR = Path(__file__).resolve().parent.parent
TMP_DIR = BASE_DIR / ".tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)


def run_pytest_task(payload: SerializedTask) -> Tuple[TaskResult, List[StepLog], str | None]:
    """
    Execute one queued task by invoking pytest as a subprocess.
    """
    task_file = TMP_DIR / f"{payload.task_id}_task.json"
    result_file = TMP_DIR / f"{payload.task_id}_result.json"

    task_file.write_text(payload.model_dump_json(indent=2), encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(BASE_DIR / "tests" / "test_web_cases.py"),
        "-q",
        "--task-file",
        str(task_file),
        "--result-file",
        str(result_file),
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if not result_file.exists():
        stdout = proc.stdout if proc.stdout is not None else "<empty>"
        stderr = proc.stderr if proc.stderr is not None else "<empty>"
        return (
            TaskResult(total=0, passed=0, failed=0, case_results=[]),
            [],
            f"pytest未生成结果文件，returncode={proc.returncode}，cmd={' '.join(cmd)}\nstdout={stdout}\nstderr={stderr}",
        )

    result_data = json.loads(result_file.read_text(encoding="utf-8"))
    result = TaskResult.model_validate(result_data)
    logs = [StepLog.model_validate(item) for item in result_data.get("logs", [])]

    if proc.returncode != 0 and result.failed == 0:
        return result, logs, f"pytest返回非0：stdout={proc.stdout}\nstderr={proc.stderr}"

    return result, logs, None
