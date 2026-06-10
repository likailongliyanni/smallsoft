<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>用户中心 | 网页自动化工作室</title>
  <link rel="stylesheet" href="/assets/styles.css">
</head>
<body>
  <header class="topbar">
    <nav class="nav">
      <a class="brand" href="/"><span class="mark">AI</span><span>网页自动化工作室</span></a>
      <div class="links">
        <a href="/">首页</a>
        <a href="/training.php">免费训练场</a>
      </div>
    </nav>
  </header>

  <main class="container two">
    <aside class="panel sticky">
      <h2>用户中心</h2>
      <p>商业化版本：用户注册后免费生成 1 次，后续购买次数。当前先支持管理员手动加次数。</p>
      <div id="userBox" class="status">未登录</div>
      <div class="actions">
        <button class="secondary" id="refreshMe">刷新账号</button>
        <button class="ghost" id="logoutBtn">退出</button>
      </div>
    </aside>

    <section>
      <div class="panel">
        <h2>登录 / 注册</h2>
        <div class="form-grid">
          <div>
            <h3>登录</h3>
            <label>用户名 <input id="loginUsername" autocomplete="username"></label>
            <label>密码 <input id="loginPassword" type="password" autocomplete="current-password"></label>
            <button id="loginBtn">登录</button>
          </div>
          <div>
            <h3>注册</h3>
            <label>用户名 <input id="regUsername" autocomplete="username"></label>
            <label>邮箱 <input id="regEmail" type="email"></label>
            <label>密码 <input id="regPassword" type="password" autocomplete="new-password"></label>
            <button id="registerBtn">注册并领取免费次数</button>
          </div>
        </div>
        <div id="authStatus" class="status" hidden></div>
      </div>

      <div class="panel" style="margin-top:18px">
        <h2>AI 生成测试</h2>
        <p>桌面软件后续会自动调用这个接口。网页里先保留测试入口，方便检查账号和次数逻辑。</p>
        <label>流程 JSON 文件
          <input id="workflowFile" type="file" accept=".json,application/json">
        </label>
        <label>或者粘贴流程 JSON
          <textarea id="workflowText" placeholder='{"url":"https://example.com","steps":[]}'></textarea>
        </label>
        <label>Excel 字段，用逗号分隔
          <input id="columnsText" value="商品名称,品牌,销售价,主图">
        </label>
        <button id="generateBtn">生成自动化脚本</button>
        <div id="generateStatus" class="status" hidden></div>
        <pre id="scriptOutput" class="codebox">生成结果会显示在这里。</pre>
      </div>
    </section>
  </main>

  <script src="/assets/app.js"></script>
  <script>
    async function refreshMe() {
      try {
        const data = await Api.call("me", { method: "GET" });
        const u = data.user;
        $("#userBox").textContent = `${u.username}，剩余：${u.remaining_generations}（免费 ${u.free_generations}，付费 ${u.paid_generations}）`;
      } catch (err) {
        $("#userBox").textContent = "未登录";
      }
    }

    $("#loginBtn").addEventListener("click", async () => {
      try {
        const data = await Api.call("auth.login", {
          method: "POST",
          body: JSON.stringify({ username: $("#loginUsername").value, password: $("#loginPassword").value })
        });
        Api.setUserToken(data.token);
        statusBox("#authStatus", "登录成功。");
        refreshMe();
      } catch (err) {
        statusBox("#authStatus", err.message, true);
      }
    });

    $("#registerBtn").addEventListener("click", async () => {
      try {
        const data = await Api.call("auth.register", {
          method: "POST",
          body: JSON.stringify({ username: $("#regUsername").value, email: $("#regEmail").value, password: $("#regPassword").value })
        });
        Api.setUserToken(data.token);
        statusBox("#authStatus", "注册成功，已领取免费生成次数。");
        refreshMe();
      } catch (err) {
        statusBox("#authStatus", err.message, true);
      }
    });

    $("#logoutBtn").addEventListener("click", () => {
      Api.setUserToken("");
      refreshMe();
    });
    $("#refreshMe").addEventListener("click", refreshMe);

    $("#workflowFile").addEventListener("change", async (event) => {
      const file = event.target.files[0];
      if (file) $("#workflowText").value = await fileText(file);
    });

    $("#generateBtn").addEventListener("click", async () => {
      try {
        const workflow = JSON.parse($("#workflowText").value || "{}");
        const columns = $("#columnsText").value.split(",").map(v => v.trim()).filter(Boolean);
        const data = await Api.call("ai.generate", {
          method: "POST",
          body: JSON.stringify({ workflow, excel_schema: { columns } })
        });
        statusBox("#generateStatus", data.mock ? `模型未配置，返回占位脚本，任务：${data.job_id}` : `生成成功，任务：${data.job_id}`);
        $("#scriptOutput").textContent = data.script;
        refreshMe();
      } catch (err) {
        statusBox("#generateStatus", err.message, true);
      }
    });

    refreshMe();
  </script>
</body>
</html>
