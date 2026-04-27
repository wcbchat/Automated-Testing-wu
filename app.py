from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from framework.models import TaskCreateRequest
from framework.queue_manager import TaskQueueManager


manager = TaskQueueManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    manager.start()
    yield
    await manager.stop()


app = FastAPI(title="Pytest Web Test Framework", lifespan=lifespan)


@app.get("/", include_in_schema=False)
async def root():
    return HTMLResponse(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>页面功能测试平台</title>
  <style>
    body { font-family: "Microsoft YaHei", Arial, sans-serif; margin: 20px; max-width: 980px; }
    h1 { margin-bottom: 6px; }
    .hint { color: #666; margin-top: 0; }
    textarea { width: 100%; min-height: 90px; font-family: Consolas, monospace; }
    input[type=text], input[type=password] { width: 100%; padding: 8px; box-sizing: border-box; margin-bottom: 8px; }
    button { margin-top: 10px; margin-right: 8px; padding: 8px 12px; cursor: pointer; }
    .card { border: 1px solid #ddd; padding: 12px; margin-top: 14px; border-radius: 8px; }
    .case-item { border: 1px dashed #bbb; border-radius: 8px; padding: 10px; margin-top: 10px; background: #fcfcfc; }
    .case-item h4 { margin: 0 0 8px 0; }
    pre { background: #f8f8f8; padding: 10px; overflow: auto; border-radius: 6px; }
  </style>
</head>
<body>
  <h1>页面功能自动测试（Pytest）</h1>
  <p class="hint">提交任务后可查看：排队中 / 执行中 / 完成 / 失败，及步骤日志和结果对比。已支持“规则+智能体兜底”步骤解析。</p>

  <div class="card">
    <h3>1) 提交测试任务（表单）</h3>
    <label>网站 URL</label>
    <input id="urlInput" type="text" value="https://example.com/login" placeholder="请输入测试网站URL" />
    <label>登录用户名</label>
    <input id="usernameInput" type="text" value="demo_user" placeholder="请输入登录用户名" />
    <label>登录密码</label>
    <input id="passwordInput" type="password" value="demo_pass" placeholder="请输入登录密码" />

    <div id="caseList"></div>

    <div>
      <button onclick="addCase()">新增用例</button>
      <button onclick="submitTask()">提交任务</button>
      <button onclick="loadTasks()">刷新任务列表</button>
      <a href="/docs" target="_blank">打开接口文档</a>
    </div>
    <p class="hint">步骤支持自然语句：打开首页 / 输入账号密码 / 输入用户名=admin / 点击模型选择框 / 等待生成结果 / 断言文本包含 成功 / 断言地址包含 dashboard。每行一步。</p>
    <div>
      <button onclick="previewPayload()">预览提交JSON</button>
    </div>
    <pre id="payloadPreview">预览JSON会显示在这里</pre>
    <pre id="submitResult">提交结果会显示在这里</pre>
  </div>

  <div class="card">
    <h3>2) 查询任务详情</h3>
    <input id="taskIdInput" type="text" placeholder="请输入 task_id" />
    <div>
      <button onclick="queryTask()">查询任务</button>
    </div>
    <pre id="taskDetail">任务详情会显示在这里</pre>
  </div>

  <div class="card">
    <h3>3) 任务列表</h3>
    <pre id="taskList">任务列表会显示在这里</pre>
  </div>

  <script>
    const statusMap = {
      queued: "排队中",
      running: "执行中",
      finished: "完成",
      failed: "失败"
    };
    let caseIndex = 0;

    function toChineseStatus(value) {
      return statusMap[value] || value;
    }

    function createCaseHTML(index, data = {}) {
      const caseName = data.case_name || `用例${index + 1}`;
      const precondition = data.precondition || "";
      const expected = data.expected_result || "";
      const steps = (data.test_steps || []).join("\\n");
      return `
        <div class="case-item" data-index="${index}">
          <h4>测试用例 #${index + 1}</h4>
          <label>用例名称</label>
          <input type="text" class="case-name" value="${caseName}" placeholder="请输入用例名称" />
          <label>前置条件</label>
          <input type="text" class="case-precondition" value="${precondition}" placeholder="请输入前置条件" />
          <label>测试步骤（每行一步）</label>
          <textarea class="case-steps" placeholder="例如：\\n打开首页\\n输入 #username = admin\\n点击 #submitBtn">${steps}</textarea>
          <label>预期结果</label>
          <input type="text" class="case-expected" value="${expected}" placeholder="请输入预期结果" />
          <button type="button" onclick="removeCase(this)">删除此用例</button>
        </div>
      `;
    }

    function addCase(data = {}) {
      const wrap = document.getElementById("caseList");
      const html = createCaseHTML(caseIndex, data);
      wrap.insertAdjacentHTML("beforeend", html);
      caseIndex += 1;
    }

    function removeCase(btn) {
      const item = btn.closest(".case-item");
      if (item) item.remove();
      refreshCaseTitle();
    }

    function refreshCaseTitle() {
      const items = Array.from(document.querySelectorAll(".case-item"));
      items.forEach((el, idx) => {
        const h4 = el.querySelector("h4");
        h4.textContent = `测试用例 #${idx + 1}`;
      });
    }

    function collectPayload() {
      const url = document.getElementById("urlInput").value.trim();
      const username = document.getElementById("usernameInput").value.trim();
      const password = document.getElementById("passwordInput").value;
      const items = Array.from(document.querySelectorAll(".case-item"));

      if (!url) throw new Error("网站URL不能为空");
      if (!username) throw new Error("登录用户名不能为空");
      if (!password) throw new Error("登录密码不能为空");
      if (!items.length) throw new Error("请至少添加1条测试用例");

      const test_cases = items.map((item, idx) => {
        const case_name = item.querySelector(".case-name").value.trim();
        const precondition = item.querySelector(".case-precondition").value.trim();
        const stepsRaw = item.querySelector(".case-steps").value;
        const expected_result = item.querySelector(".case-expected").value.trim();
        const test_steps = stepsRaw.split("\\n").map(s => s.trim()).filter(Boolean);

        if (!case_name) throw new Error(`第${idx + 1}条用例缺少用例名称`);
        if (!expected_result) throw new Error(`第${idx + 1}条用例缺少预期结果`);
        if (!test_steps.length) throw new Error(`第${idx + 1}条用例至少需要1个测试步骤`);

        return { case_name, precondition, test_steps, expected_result };
      });

      return { url, username, password, test_cases };
    }

    function previewPayload() {
      const payloadPreview = document.getElementById("payloadPreview");
      try {
        const payload = collectPayload();
        payloadPreview.textContent = JSON.stringify(payload, null, 2);
      } catch (e) {
        payloadPreview.textContent = "校验失败: " + e.message;
      }
    }

    async function submitTask() {
      const submitResult = document.getElementById("submitResult");
      try {
        const payload = collectPayload();
        const resp = await fetch("/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (data.status) data.status_cn = toChineseStatus(data.status);
        submitResult.textContent = JSON.stringify(data, null, 2);
        if (data.task_id) document.getElementById("taskIdInput").value = data.task_id;
        loadTasks();
      } catch (e) {
        submitResult.textContent = "提交失败: " + e.message;
      }
    }

    async function queryTask() {
      const taskId = document.getElementById("taskIdInput").value.trim();
      const taskDetail = document.getElementById("taskDetail");
      if (!taskId) {
        taskDetail.textContent = "请先输入 task_id";
        return;
      }
      try {
        const resp = await fetch(`/tasks/${taskId}`);
        const data = await resp.json();
        if (data.status) data.status_cn = toChineseStatus(data.status);
        taskDetail.textContent = JSON.stringify(data, null, 2);
      } catch (e) {
        taskDetail.textContent = "查询失败: " + e.message;
      }
    }

    async function loadTasks() {
      const taskList = document.getElementById("taskList");
      try {
        const resp = await fetch("/tasks");
        const data = await resp.json();
        const rows = (data.tasks || []).map(t => ({
          ...t,
          status_cn: toChineseStatus(t.status)
        }));
        taskList.textContent = JSON.stringify(rows, null, 2);
      } catch (e) {
        taskList.textContent = "加载失败: " + e.message;
      }
    }

    addCase({
      case_name: "登录成功后进入首页",
      precondition: "账号已开通且可登录",
      test_steps: ["打开首页", "输入 #username = demo_user", "输入 #password = demo_pass", "点击 #submitBtn", "断言地址包含 dashboard"],
      expected_result: "系统跳转到 dashboard 页面"
    });
    loadTasks();
  </script>
</body>
</html>
        """
    )


@app.post("/tasks")
async def create_task(payload: TaskCreateRequest):
    return manager.create_task(payload)


@app.get("/tasks")
async def list_tasks():
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "status": t.status,
                "created_at": t.created_at,
            }
            for t in manager.list_tasks().values()
        ]
    }


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    try:
        return manager.get_task(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found") from None
