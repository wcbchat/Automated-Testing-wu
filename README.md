# Pytest 页面功能自动化测试框架 第一版 bin哥初试

该框架用于页面功能测试，支持：

- 多条测试任务输入（异步入队）
- 任务状态：`queued`（排队中）、`running`（执行中）、`finished`、`failed`
- 结构化日志：时间、步骤、调用工具（Playwright/Pytest/Queue）
- 测试结果：按预期对比，输出成功/失败

## 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

## 2. 启动服务

```bash
uvicorn app:app --reload --port 8000
```

## 3. 提交测试任务

```bash
curl -X POST "http://127.0.0.1:8000/tasks" ^
  -H "Content-Type: application/json" ^
  -d "@sample_task.json"
```

返回示例：

```json
{
  "task_id": "f20c8a3d-xxxx-xxxx-xxxx-7bcd9e5f6b1c",
  "status": "queued"
}
```

## 4. 查询任务状态与结果

```bash
curl "http://127.0.0.1:8000/tasks/f20c8a3d-xxxx-xxxx-xxxx-7bcd9e5f6b1c"
```

响应中包含：

- `status`：排队中/执行中/完成/失败
- `logs`：每一步日志（`timestamp`、`step`、`tool`、`status`、`details`）
- `result`：总数、通过数、失败数、每个用例的预期与实际

## 5. 输入字段说明

任务输入 JSON 结构：

- `url`：测试目标页面 URL
- `username` / `password`：登录凭据
- `test_cases`：可输入多个测试用例
  - `case_name`：用例名称
  - `precondition`：前置条件
  - `test_steps`：测试步骤（文本数组）
  - `expected_result`：预期结果

`test_steps` 文本支持示例：

- `打开首页`
- `打开 https://example.com/login`
- `登录`
- `输入 #username = admin`
- `点击 #submitBtn`
- `等待 h1`
- `断言文本 h1 包含 欢迎`
- `断言地址包含 dashboard`

## 6. 免费智能体兜底解析（推荐）

当步骤写得很口语（例如：`输入账号`、`输入用户名密码`）时，可开启本地免费智能体兜底。

### 安装 Ollama（免费、本地）

- 官网：[https://ollama.com](https://ollama.com)
- 拉取模型（推荐）：

```bash
ollama pull qwen2.5:7b-instruct
```

### 启用智能体解析

Windows PowerShell：

```powershell
$env:ENABLE_AI_PARSER="1"
$env:OLLAMA_MODEL="qwen2.5:7b-instruct"
$env:OLLAMA_URL="http://127.0.0.1:11434"
uvicorn app:app --reload --port 8000
```

说明：

- 规则解析优先，智能体作为兜底；
- 未开启时保持纯规则模式；
- 本地推理，无需API Key。

## 7. 目录结构

```text
.
├── app.py
├── framework
│   ├── ai_parser.py
│   ├── executor.py
│   ├── models.py
│   └── queue_manager.py
├── tests
│   ├── conftest.py
│   └── test_web_cases.py
└── sample_task.json
```
