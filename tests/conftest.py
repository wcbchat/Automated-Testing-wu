from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from playwright.sync_api import sync_playwright, Page, Browser


# ====================== 你原本的代码（完全保留）======================
def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--task-file", action="store", default=None, help="Task json file path")
    parser.addoption("--result-file", action="store", default=None, help="Result json file path")


@pytest.fixture(scope="session")
def task_payload(pytestconfig: pytest.Config) -> Dict[str, Any]:
    task_file = pytestconfig.getoption("--task-file")
    if not task_file:
        pytest.skip("missing --task-file")
    return json.loads(Path(task_file).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def result_file(pytestconfig: pytest.Config) -> Path:
    value = pytestconfig.getoption("--result-file")
    if not value:
        pytest.skip("missing --result-file")
    return Path(value)


# ====================== 新增：Playwright 自动化核心 fixture ======================
@pytest.fixture(scope="session")
def browser() -> Browser:
    """
    全局浏览器实例（会话级别）
    自动启动 → 测试运行 → 自动关闭
    """
    with sync_playwright() as p:
        # ====================== 关键：使用你本地已有的 Chrome，不用再下载！======================
        browser = p.chromium.launch(
            executable_path="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            headless=False,  # 显示浏览器窗口
            args=["--start-maximized"]  # 启动时最大化窗口
        )
        yield browser
        browser.close()


@pytest.fixture(scope="function")
def page(browser: Browser) -> Page:
    """
    每个测试用例独立页面
    自动创建 → 用例执行 → 自动关闭
    """
    page = browser.new_page()
    # 基础超时设置
    page.set_default_timeout(30000)
    yield page
    page.close()


# ====================== 新增：百度网站通用夹具（你要测的网站）======================
@pytest.fixture(scope="function")
def baidu_page(page: Page) -> Page:
    """
    直接打开百度首页的 fixture
    你的用例可以直接用 baidu_page 而不用自己写 page.goto
    """
    page.goto("https://www.baidu.com")
    page.wait_for_load_state("domcontentloaded")
    return page