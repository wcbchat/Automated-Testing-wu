from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from framework.models import StepInput


ALLOWED_ACTIONS = {
    "goto",
    "login",
    "fill",
    "click",
    "wait_for_selector",
    "assert_text",
    "assert_url_contains",
}


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def parse_step_with_ollama(raw_step: str, context: Dict[str, str]) -> Optional[StepInput]:
    """
    Optional LLM fallback parser.
    Enable with env: ENABLE_AI_PARSER=1
    Default endpoint/model: http://127.0.0.1:11434, qwen2.5:7b-instruct
    """
    if os.getenv("ENABLE_AI_PARSER", "0") != "1":
        return None

    base_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

    system_prompt = (
        "你是网页自动化步骤解析器。"
        "把中文测试步骤转换为一个JSON对象，只返回JSON。"
        "字段只允许: action, selector, value, expected, timeout_ms, "
        "user_selector, pass_selector, submit_selector。"
        "action必须是: goto/login/fill/click/wait_for_selector/assert_text/assert_url_contains。"
    )
    user_prompt = {
        "step": raw_step,
        "context": context,
        "examples": [
            {"input": "输入账号密码", "output": {"action": "login"}},
            {"input": "输入账号", "output": {"action": "fill", "selector": "input[name='username']", "value": context.get("username", "")}},
            {"input": "输入密码", "output": {"action": "fill", "selector": "input[name='password']", "value": context.get("password", "")}},
            {"input": "断言地址包含 dashboard", "output": {"action": "assert_url_contains", "expected": "dashboard"}},
        ],
    }

    payload = {
        "model": model,
        "prompt": f"{system_prompt}\n\n{json.dumps(user_prompt, ensure_ascii=False)}",
        "stream": False,
    }

    req = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    response_text = body.get("response", "")
    data = _extract_json_object(response_text)
    if not data:
        return None

    action = data.get("action")
    if action not in ALLOWED_ACTIONS:
        return None

    try:
        return StepInput.model_validate(data)
    except Exception:  # noqa: BLE001
        return None
