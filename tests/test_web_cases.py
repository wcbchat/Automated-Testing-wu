from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from playwright.sync_api import sync_playwright


def _now() -> str:
    return datetime.utcnow().isoformat()


def _append_log(logs: List[Dict[str, Any]], step: str, status: str, details: str = "") -> None:
    logs.append(
        {
            "timestamp": _now(),
            "step": step,
            "tool": "playwright",
            "status": status,
            "details": details,
        }
    )


def _looks_like_selector(target: str) -> bool:
    tokens = ("#", ".", "[", ">", "=", ":", "xpath=", "//", "text=", "css=")
    return any(token in target for token in tokens)


def _probe_visible_elements(page: Any) -> List[Dict[str, str]]:
    return page.evaluate(
        """
() => {
  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const list = [];
  const nodes = document.querySelectorAll('button, a, [role=\"button\"], [role=\"option\"], [role=\"tab\"], [role=\"menuitem\"], input, textarea, select, label, div, span');
  nodes.forEach((el) => {
    if (!isVisible(el)) return;
    const text = (el.innerText || el.textContent || el.value || '').trim().replace(/\\s+/g, ' ');
    if (!text || text.length > 120) return;
    const id = el.id ? `#${el.id}` : '';
    const cls = (el.className && typeof el.className === 'string') ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '';
    const role = el.getAttribute('role') || '';
    const name = el.getAttribute('name') || '';
    const dataTest = el.getAttribute('data-testid') || el.getAttribute('data-test') || '';
    list.push({
      text,
      selector: id || (name ? `${el.tagName.toLowerCase()}[name=\"${name}\"]` : '') || (dataTest ? `[data-testid=\"${dataTest}\"]` : '') || `${el.tagName.toLowerCase()}${cls}`,
      tag: el.tagName.toLowerCase(),
      role
    });
  });
  return list.slice(0, 300);
}
        """
    )


def _resolve_target_with_probe(page: Any, target: str) -> str:
    elements = _probe_visible_elements(page)
    query = target.strip().lower()
    if not query:
        return target

    for item in elements:
        if query == item["text"].strip().lower():
            return item["selector"] or item["text"]

    for item in elements:
        if query in item["text"].strip().lower():
            return item["selector"] or item["text"]

    return target


def _smart_click(page: Any, target: str, timeout_ms: int) -> None:
    target = (target or "").strip()
    if not target:
        raise ValueError("click 缺少目标")
    if _looks_like_selector(target):
        page.click(target, timeout=timeout_ms)
        return
    resolved = _resolve_target_with_probe(page, target)
    # 优先文本点击，失败后再尝试作为selector
    try:
        page.get_by_text(resolved, exact=False).first.click(timeout=timeout_ms)
        return
    except Exception:  # noqa: BLE001
        try:
            page.click(resolved, timeout=timeout_ms)
        except Exception:  # noqa: BLE001
            page.get_by_text(target, exact=False).first.click(timeout=timeout_ms)


def _smart_wait(page: Any, target: str, timeout_ms: int) -> None:
    target = (target or "").strip()
    if not target:
        raise ValueError("wait 缺少目标")
    if _looks_like_selector(target):
        page.wait_for_selector(target, timeout=timeout_ms)
        return
    resolved = _resolve_target_with_probe(page, target)
    try:
        page.get_by_text(resolved, exact=False).first.wait_for(timeout=timeout_ms)
        return
    except Exception:  # noqa: BLE001
        try:
            page.wait_for_selector(resolved, timeout=timeout_ms)
        except Exception:  # noqa: BLE001
            page.get_by_text(target, exact=False).first.wait_for(timeout=timeout_ms)


def _smart_get_text(page: Any, target: str, timeout_ms: int) -> str:
    target = (target or "").strip()
    if not target:
        return page.inner_text("body", timeout=timeout_ms)
    if _looks_like_selector(target):
        return page.inner_text(target, timeout=timeout_ms)
    resolved = _resolve_target_with_probe(page, target)
    try:
        return page.get_by_text(resolved, exact=False).first.inner_text(timeout=timeout_ms)
    except Exception:  # noqa: BLE001
        try:
            return page.inner_text(resolved, timeout=timeout_ms)
        except Exception:  # noqa: BLE001
            return page.inner_text("body", timeout=timeout_ms)


def _run_step(page: Any, step: Dict[str, Any], creds: Dict[str, str], logs: List[Dict[str, Any]]) -> None:
    action = step["action"]
    selector = step.get("selector")
    value = step.get("value", "")
    timeout_ms = int(step.get("timeout_ms", 5000))

    _append_log(logs, f"action={action}", "running", f"selector={selector}")

    if action == "goto":
        target = value or creds["url"]
        page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
    elif action == "fill":
        page.fill(selector, value, timeout=timeout_ms)
    elif action == "click":
        _smart_click(page, selector or value, timeout_ms)
    elif action == "wait_for_selector":
        _smart_wait(page, selector or value, timeout_ms)
    elif action == "assert_text":
        text = _smart_get_text(page, selector, timeout_ms)
        assert step.get("expected", "") in text, f"文本断言失败，actual={text}"
    elif action == "assert_url_contains":
        current = page.url
        assert step.get("expected", "") in current, f"URL断言失败，actual={current}"
    elif action == "login":
        user_selector = step.get("user_selector", "input[name='username']")
        pass_selector = step.get("pass_selector", "input[name='password']")
        submit_selector = step.get("submit_selector", "button[type='submit']")
        page.fill(user_selector, creds["username"], timeout=timeout_ms)
        page.fill(pass_selector, creds["password"], timeout=timeout_ms)
        page.click(submit_selector, timeout=timeout_ms)
    else:
        raise ValueError(f"不支持的action: {action}")

    _append_log(logs, f"action={action}", "success")


def test_run_all_cases(task_payload: Dict[str, Any], result_file: Path) -> None:
    cases = task_payload.get("test_cases", [])
    creds = {
        "url": task_payload["url"],
        "username": task_payload["username"],
        "password": task_payload["password"],
    }

    all_logs: List[Dict[str, Any]] = []
    case_results: List[Dict[str, Any]] = []
    passed = 0
    failed = 0

    try:
        with sync_playwright() as p:
            chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
            if os.path.exists(chrome_path):
                browser = p.chromium.launch(executable_path=chrome_path, headless=True)
                _append_log(all_logs, "browser_launch", "success", "使用本地Chrome启动")
            else:
                browser = p.chromium.launch(headless=True)
                _append_log(all_logs, "browser_launch", "success", "使用Playwright内置Chromium启动")

            context = browser.new_context()

            for case in cases:
                name = case.get("name", "unnamed")
                steps = case.get("steps", [])
                expected = case.get("expected", "all steps should pass")
                precondition = case.get("precondition", "")
                page = context.new_page()
                case_actual = "passed"
                case_error = None

                _append_log(all_logs, f"case_start={name}", "running")
                if precondition:
                    _append_log(all_logs, f"前置条件={precondition}", "running")
                try:
                    for step in steps:
                        _run_step(page, step, creds, all_logs)
                    passed += 1
                    status = "passed"
                    case_actual = "all assertions passed"
                    _append_log(all_logs, f"case_end={name}", "success")
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    status = "failed"
                    case_actual = "failed on assertion or step"
                    case_error = str(exc)
                    _append_log(all_logs, f"case_end={name}", "failed", str(exc))
                finally:
                    page.close()

                case_results.append(
                    {
                        "name": name,
                        "status": status,
                        "expected": expected,
                        "actual": case_actual,
                        "error": case_error,
                    }
                )

            context.close()
            browser.close()
    except Exception as exc:  # noqa: BLE001
        failed = len(cases)
        passed = 0
        _append_log(all_logs, "framework_error", "failed", str(exc))
        case_results = [
            {
                "name": case.get("name", "unnamed"),
                "status": "failed",
                "expected": case.get("expected", "all steps should pass"),
                "actual": "framework execution failed",
                "error": str(exc),
            }
            for case in cases
        ]

    output = {
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "case_results": case_results,
        "logs": all_logs,
    }
    result_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    if failed > 0:
        raise AssertionError(f"存在失败用例: failed={failed}")
