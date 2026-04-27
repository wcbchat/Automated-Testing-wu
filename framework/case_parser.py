from __future__ import annotations

import re
from typing import Any, Dict, List

from framework.ai_parser import parse_step_with_ollama
from framework.models import StepInput, TestCaseInput


def _normalize(text: str) -> str:
    return text.replace("：", ":").replace("，", ",").strip().rstrip("。；;")


def _clean_business_sentence(text: str) -> str:
    s = _normalize(text)
    # 去掉编号前缀：1. / 1、 / 1) / （1）
    s = re.sub(r"^\s*[（(]?\d+[）)]?\s*[.、)\-]?\s*", "", s)
    # 去掉中文引号
    s = s.replace("“", "").replace("”", "").replace('"', "")
    return s.strip()


def _parse_text_step(text_step: str, context: Dict[str, str]) -> StepInput:
    raw = _clean_business_sentence(text_step)
    if not raw:
        raise ValueError("测试步骤不能为空")
    normalized = _normalize(raw)

    # 页面打开类
    if normalized.startswith("打开 "):
        return StepInput(action="goto", value=normalized.replace("打开 ", "", 1).strip())
    if normalized in {"打开首页", "进入首页", "访问首页"}:
        return StepInput(action="goto")

    # 登录类（支持“输入账号密码”“账号密码登录”“登陆系统”等）
    if any(word in normalized for word in ["登录", "登陆"]) and any(
        word in normalized for word in ["账号", "账户", "用户名", "密码"]
    ):
        return StepInput(action="login")
    if normalized in {"登录", "登陆", "点击登录", "提交登录"}:
        return StepInput(action="login")
    if any(word in normalized for word in ["输入账号密码", "填写账号密码", "输入用户名密码"]):
        return StepInput(action="login")
    if normalized in {"输入账号", "输入用户名", "填写账号", "填写用户名"}:
        return StepInput(action="fill", selector="input[name='username']", value=context.get("username", ""))
    if normalized in {"输入密码", "填写密码"}:
        return StepInput(action="fill", selector="input[name='password']", value=context.get("password", ""))

    # 操作类
    if normalized.startswith("点击 "):
        return StepInput(action="click", selector=normalized.replace("点击 ", "", 1).strip())
    m = re.match(r"^点击\s*(.+)$", normalized)
    if m:
        return StepInput(action="click", selector=m.group(1).strip())

    if normalized.startswith("等待 "):
        return StepInput(action="wait_for_selector", selector=normalized.replace("等待 ", "", 1).strip())
    m = re.match(r"^等待\s*(.+)$", normalized)
    if m:
        return StepInput(action="wait_for_selector", selector=m.group(1).strip())

    # 查看类语句：映射为等待目标可见（文本或选择器）
    if normalized.startswith("查看 "):
        return StepInput(action="wait_for_selector", selector=normalized.replace("查看 ", "", 1).strip())
    m = re.match(r"^查看\s*(.+)$", normalized)
    if m:
        return StepInput(action="wait_for_selector", selector=m.group(1).strip())

    # 选择类语句：先点击选择入口，再配合下一步断言/等待
    if normalized.startswith("选择 "):
        return StepInput(action="click", selector=normalized.replace("选择 ", "", 1).strip())
    m = re.match(r"^选择\s*(.+)$", normalized)
    if m:
        return StepInput(action="click", selector=m.group(1).strip())
    if normalized.startswith("勾选 "):
        return StepInput(action="click", selector=normalized.replace("勾选 ", "", 1).strip())
    m = re.match(r"^勾选\s*(.+)$", normalized)
    if m:
        return StepInput(action="click", selector=m.group(1).strip())

    # 业务语句：打开X弹窗 -> 点击X
    m = re.match(r"^打开\s*(.+?)\s*弹窗$", normalized)
    if m:
        return StepInput(action="click", selector=m.group(1).strip())
    # 业务语句：观察/检查/确认 ... -> 等待相关元素
    m = re.match(r"^(观察|检查|确认)\s*(.+)$", normalized)
    if m:
        target = m.group(2).replace("是否", "").replace("自动", "").replace("并", " ").strip()
        if target:
            return StepInput(action="wait_for_selector", selector=target)
    if normalized.startswith("断言地址包含 "):
        return StepInput(action="assert_url_contains", expected=normalized.replace("断言地址包含 ", "", 1).strip())
    if normalized.startswith("url包含 "):
        return StepInput(action="assert_url_contains", expected=normalized.replace("url包含 ", "", 1).strip())
    m = re.match(r"^(?:断言)?(?:地址|url)\s*包含\s*(.+)$", normalized, flags=re.IGNORECASE)
    if m:
        return StepInput(action="assert_url_contains", expected=m.group(1).strip())

    # 输入类：支持“输入 #id = value”、“输入用户名=xxx”、“输入密码=xxx”
    if normalized.startswith("输入 "):
        # 格式：输入 <selector> = <value>
        body = normalized.replace("输入 ", "", 1).strip()
        body = body.replace("：", "=").replace("为", "=")
        if "=" not in body:
            if "账号" in body or "用户名" in body:
                return StepInput(action="fill", selector="input[name='username']", value="")
            if "密码" in body:
                return StepInput(action="fill", selector="input[name='password']", value="")
            raise ValueError("输入步骤格式错误，示例：输入 #username = admin")
        selector, value = body.split("=", 1)
        selector = selector.strip()
        value = value.strip()
        if selector in {"用户名", "账号", "账户"}:
            selector = "input[name='username']"
        elif selector == "密码":
            selector = "input[name='password']"
        return StepInput(action="fill", selector=selector, value=value)

    # 支持“输入用户名=xxx / 输入密码=xxx / 输入用户名:xxx”（无空格）
    m = re.match(r"^输入\s*(用户名|账号|账户|密码)\s*[:=]\s*(.+)$", normalized)
    if m:
        key, value = m.group(1), m.group(2).strip()
        selector = "input[name='username']" if key in {"用户名", "账号", "账户"} else "input[name='password']"
        return StepInput(action="fill", selector=selector, value=value)

    # 支持“输入用户名 / 输入密码”（未给值时使用任务中的账号密码）
    m = re.match(r"^输入\s*(用户名|账号|账户|密码)$", normalized)
    if m:
        key = m.group(1)
        if key in {"用户名", "账号", "账户"}:
            return StepInput(action="fill", selector="input[name='username']", value=context.get("username", ""))
        return StepInput(action="fill", selector="input[name='password']", value=context.get("password", ""))

    # 支持“用户名=xxx”“密码=xxx”这种省略“输入”的写法
    m = re.match(r"^(用户名|账号|账户|密码)\s*[:=]\s*(.+)$", normalized)
    if m:
        key, value = m.group(1), m.group(2).strip()
        selector = "input[name='username']" if key in {"用户名", "账号", "账户"} else "input[name='password']"
        return StepInput(action="fill", selector=selector, value=value)

    # 断言类
    if normalized.startswith("断言文本 "):
        # 格式：断言文本 <selector> 包含 <text>
        body = normalized.replace("断言文本 ", "", 1).strip()
        token = " 包含 "
        if token not in body:
            raise ValueError("断言文本步骤格式错误，示例：断言文本 h1 包含 欢迎")
        selector, expected = body.split(token, 1)
        return StepInput(action="assert_text", selector=selector.strip(), expected=expected.strip())
    m = re.match(r"^断言文本包含\s*(.+)$", normalized)
    if m:
        return StepInput(action="assert_text", selector="body", expected=m.group(1).strip())

    ai_step = parse_step_with_ollama(raw, context)
    if ai_step:
        return ai_step

    raise ValueError(
        f"无法识别的步骤：{raw}。建议写法：输入账号密码 / 用户名=xxx / 密码=xxx / 点击模型选择框 / 查看可选模型 / 断言文本包含 xxx / 断言地址包含 dashboard"
    )


def _split_compound_step(text_step: str) -> List[str]:
    """
    支持把一行复合语句拆成多步：
    例如：输入账号密码并点击登录按钮
    """
    normalized = _normalize(text_step)
    parts = re.split(r"\s*(?:然后|并且|并|且|后|再)\s*", normalized)
    return [p for p in parts if p]


def _auto_append_assertion(steps: List[StepInput], expected: str) -> List[StepInput]:
    """
    若用户未写断言，则根据预期结果自动补充验证步骤。
    """
    if any(step.action in {"assert_text", "assert_url_contains"} for step in steps):
        return steps

    expected_norm = _clean_business_sentence(expected)
    if not expected_norm:
        return steps

    # URL类断言：如“跳转到dashboard/地址包含dashboard”
    url_hit = re.search(r"(?:跳转|地址|url).*(?:包含|到)\s*([A-Za-z0-9_./-]+)", expected_norm, re.IGNORECASE)
    if url_hit:
        steps.append(StepInput(action="assert_url_contains", expected=url_hit.group(1)))
        return steps

    # 文本类断言：优先提取引号中的关键值，例如 “MJ V7”
    quoted = re.findall(r"[\"“”]?([A-Za-z0-9][A-Za-z0-9 _.-]{1,40})[\"“”]?", expected_norm)
    for item in quoted:
        token = item.strip()
        if token and any(ch.isalpha() for ch in token):
            steps.append(StepInput(action="assert_text", selector="body", expected=token))
            return steps

    # 文本类断言：提取“显示...为X”的 X
    display_hit = re.search(r"(?:显示|为)\s*([A-Za-z0-9 _.-]{2,40})$", expected_norm)
    if display_hit:
        steps.append(StepInput(action="assert_text", selector="body", expected=display_hit.group(1).strip()))
        return steps

    # 文本类断言：默认断言 body 包含预期结果
    steps.append(StepInput(action="assert_text", selector="body", expected=expected_norm))
    return steps


def build_serialized_cases(cases: List[TestCaseInput], context: Dict[str, str]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for case in cases:
        if case.steps:
            steps = case.steps[:]
        else:
            parsed_steps: List[StepInput] = []
            for input_step in case.test_steps:
                for segment in _split_compound_step(input_step):
                    parsed_steps.append(_parse_text_step(segment, context))
            steps = parsed_steps

        steps = _auto_append_assertion(steps, case.expected_result)

        serialized.append(
            {
                "name": case.case_name,
                "precondition": case.precondition,
                "expected": case.expected_result,
                "steps": [step.model_dump() for step in steps],
            }
        )
    return serialized
