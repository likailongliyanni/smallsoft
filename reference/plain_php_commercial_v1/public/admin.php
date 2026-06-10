<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>内部管理 | 网页自动化工作室</title>
  <link rel="stylesheet" href="/assets/styles.css">
</head>
<body>
  <header class="topbar">
    <nav class="nav">
      <a class="brand" href="/"><span class="mark">AI</span><span>网页自动化工作室</span></a>
      <div class="links">
        <a href="/">首页</a>
        <a href="/console.php">用户中心</a>
      </div>
    </nav>
  </header>

  <main class="container two">
    <aside class="panel sticky">
      <div class="eyebrow">内部管理</div>
      <h2>管理员登录</h2>
      <p>后台不在公开页面展示，直接访问本页并输入 config.php 里的管理员口令。</p>
      <label>后台口令
        <input id="adminPassword" type="password">
      </label>
      <div class="actions">
        <button id="adminLogin">登录后台</button>
        <button class="ghost" id="adminLogout">退出</button>
      </div>
      <div id="adminStatus" class="status" hidden></div>
    </aside>

    <section>
      <div class="stat-row">
        <div class="panel stat"><span>总用户</span><strong id="statUsers">0</strong></div>
        <div class="panel stat"><span>正常用户</span><strong id="statActiveUsers">0</strong></div>
        <div class="panel stat"><span>生成任务</span><strong id="statJobs">0</strong></div>
        <div class="panel stat"><span>已付订单</span><strong id="statOrders">0</strong></div>
      </div>

      <div class="panel" style="margin-top:18px">
        <h2>API / 大模型配置</h2>
        <p>支持 OpenAI-compatible Chat Completions。软件端不保存模型 key。</p>
        <form id="modelForm" class="form-grid">
          <label>Provider <input id="provider" value="openai-compatible"></label>
          <label>Model <input id="modelName" placeholder="例如：gpt-4.1、qwen-plus、deepseek-chat"></label>
          <label class="full">Base URL <input id="baseUrl" placeholder="例如：https://api.openai.com/v1"></label>
          <label class="full">API Key <input id="apiKey" type="password" placeholder="已保存时留空不会覆盖"></label>
          <div class="full inline">
            <input id="clearApiKey" type="checkbox">
            <label for="clearApiKey" style="display:inline;margin:0">清除已保存的 API Key</label>
          </div>
          <div class="full actions">
            <button type="submit">保存配置</button>
            <button type="button" class="secondary" id="testModel">测试模型接口</button>
          </div>
        </form>
        <div id="modelStatus" class="status" hidden></div>
      </div>

      <div class="panel" style="margin-top:18px">
        <div class="table-head">
          <div>
            <h2>用户管理</h2>
            <p>查看用户、调整次数、禁用账号。正式支付接入前，可以先人工收款后加次数。</p>
          </div>
          <div class="search-row">
            <input id="userQuery" placeholder="搜索用户名或邮箱">
            <button id="loadUsers" type="button">查询</button>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th><th>用户名</th><th>邮箱</th><th>状态</th><th>剩余次数</th><th>任务</th><th>注册时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody id="usersBody"></tbody>
          </table>
        </div>
      </div>

      <div class="panel" id="userEditor" style="margin-top:18px" hidden>
        <h2>调整用户</h2>
        <form id="userForm" class="form-grid">
          <input id="editUserId" type="hidden">
          <label>用户名 <input id="editUsername" disabled></label>
          <label>邮箱 <input id="editEmail"></label>
          <label>免费次数 <input id="editFree" type="number" min="0"></label>
          <label>付费次数 <input id="editPaid" type="number" min="0"></label>
          <label>状态
            <select id="editStatus">
              <option value="active">正常</option>
              <option value="disabled">禁用</option>
            </select>
          </label>
          <label class="full">备注 <textarea id="editNote"></textarea></label>
          <div class="full actions">
            <button type="submit">保存用户</button>
            <button class="secondary" type="button" id="createPaidOrder">人工收款并加次数</button>
            <button class="ghost" type="button" id="cancelEdit">取消</button>
          </div>
        </form>
        <div id="userStatus" class="status" hidden></div>
      </div>

      <div class="panel" style="margin-top:18px">
        <div class="table-head">
          <div>
            <h2>最近生成任务</h2>
            <p>排查模型失败、用户消耗、脚本生成情况。</p>
          </div>
          <button id="loadJobs" type="button" class="secondary">刷新任务</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>ID</th><th>用户</th><th>状态</th><th>网址</th><th>扣次</th><th>脚本大小</th><th>时间</th><th>错误</th></tr></thead>
            <tbody id="jobsBody"></tbody>
          </table>
        </div>
      </div>

      <div class="panel" style="margin-top:18px">
        <div class="table-head">
          <div>
            <h2>订单记录</h2>
            <p>当前支持后台人工创建已付订单并加次数，后续接微信/支付宝。</p>
          </div>
          <button id="loadOrders" type="button" class="secondary">刷新订单</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>订单号</th><th>用户</th><th>套餐</th><th>金额</th><th>次数</th><th>状态</th><th>时间</th></tr></thead>
            <tbody id="ordersBody"></tbody>
          </table>
        </div>
      </div>
    </section>
  </main>

  <script src="/assets/app.js"></script>
  <script>
    function fmt(v) { return v === null || v === undefined || v === "" ? "-" : String(v); }
    function statusName(v) { return v === "disabled" ? "禁用" : "正常"; }
    function money(cents) { return (Number(cents || 0) / 100).toFixed(2); }

    async function adminCall(action, options = {}) {
      return await Api.call(action, { ...options, admin: true });
    }

    async function loadDashboard() {
      const [stats, model, users, jobs, orders] = await Promise.all([
        adminCall("admin.stats"),
        adminCall("admin.model.get"),
        adminCall(`admin.users&query=${encodeURIComponent($("#userQuery").value || "")}`),
        adminCall("admin.jobs"),
        adminCall("admin.orders")
      ]);
      $("#statUsers").textContent = stats.users;
      $("#statActiveUsers").textContent = stats.active_users;
      $("#statJobs").textContent = stats.generation_jobs;
      $("#statOrders").textContent = stats.paid_orders;
      $("#provider").value = model.provider || "openai-compatible";
      $("#baseUrl").value = model.base_url || "";
      $("#modelName").value = model.model_name || "";
      $("#apiKey").placeholder = model.api_key_set ? "已保存，留空不覆盖" : "尚未配置";
      renderUsers(users.users || []);
      renderJobs(jobs.jobs || []);
      renderOrders(orders.orders || []);
    }

    function renderUsers(users) {
      const body = $("#usersBody");
      body.innerHTML = "";
      if (!users.length) {
        body.innerHTML = `<tr><td colspan="8">暂无用户</td></tr>`;
        return;
      }
      for (const user of users) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${user.id}</td>
          <td>${fmt(user.username)}</td>
          <td>${fmt(user.email)}</td>
          <td><span class="badge ${user.status === "disabled" ? "danger" : ""}">${statusName(user.status)}</span></td>
          <td>${user.remaining_generations}（免 ${user.free_generations} / 付 ${user.paid_generations}）</td>
          <td>${user.job_count || 0}</td>
          <td>${fmt(user.created_at)}</td>
          <td><button class="secondary small" type="button">调整</button></td>
        `;
        tr.querySelector("button").addEventListener("click", () => editUser(user));
        body.appendChild(tr);
      }
    }

    function renderJobs(jobs) {
      const body = $("#jobsBody");
      body.innerHTML = "";
      if (!jobs.length) {
        body.innerHTML = `<tr><td colspan="8">暂无任务</td></tr>`;
        return;
      }
      for (const job of jobs) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${job.id}</td><td>${fmt(job.username)}</td><td><span class="badge">${job.status}</span></td>
          <td>${fmt(job.target_url)}</td><td>${job.quota_consumed ? "是" : "否"}</td>
          <td>${job.script_size || 0}</td><td>${fmt(job.created_at)}</td><td class="error-text">${fmt(job.error)}</td>
        `;
        body.appendChild(tr);
      }
    }

    function renderOrders(orders) {
      const body = $("#ordersBody");
      body.innerHTML = "";
      if (!orders.length) {
        body.innerHTML = `<tr><td colspan="7">暂无订单</td></tr>`;
        return;
      }
      for (const order of orders) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${order.order_no}</td><td>${fmt(order.username)}</td><td>${fmt(order.plan_name)}</td>
          <td>${money(order.amount_cents)}</td><td>${order.generation_count}</td>
          <td><span class="badge">${order.status}</span></td><td>${fmt(order.created_at)}</td>
        `;
        body.appendChild(tr);
      }
    }

    function editUser(user) {
      $("#userEditor").hidden = false;
      $("#editUserId").value = user.id;
      $("#editUsername").value = user.username || "";
      $("#editEmail").value = user.email || "";
      $("#editFree").value = user.free_generations || 0;
      $("#editPaid").value = user.paid_generations || 0;
      $("#editStatus").value = user.status || "active";
      $("#editNote").value = user.note || "";
      $("#userStatus").hidden = true;
      $("#userEditor").scrollIntoView({ behavior: "smooth", block: "start" });
    }

    $("#adminLogin").addEventListener("click", async () => {
      try {
        const data = await Api.call("admin.login", {
          method: "POST",
          body: JSON.stringify({ password: $("#adminPassword").value })
        });
        Api.setAdminToken(data.token);
        $("#adminPassword").value = "";
        statusBox("#adminStatus", "管理员登录成功。");
        loadDashboard();
      } catch (err) {
        statusBox("#adminStatus", err.message, true);
      }
    });

    $("#adminLogout").addEventListener("click", async () => {
      try { if (Api.adminToken) await adminCall("admin.logout", { method: "POST" }); } catch (_) {}
      Api.setAdminToken("");
      statusBox("#adminStatus", "已退出后台。");
    });

    $("#modelForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await adminCall("admin.model.save", {
          method: "POST",
          body: JSON.stringify({
            provider: $("#provider").value,
            base_url: $("#baseUrl").value,
            model_name: $("#modelName").value,
            api_key: $("#apiKey").value,
            clear_api_key: $("#clearApiKey").checked
          })
        });
        $("#apiKey").value = "";
        $("#clearApiKey").checked = false;
        statusBox("#modelStatus", "模型配置已保存。");
        loadDashboard();
      } catch (err) {
        statusBox("#modelStatus", err.message, true);
      }
    });

    $("#testModel").addEventListener("click", async () => {
      try {
        const data = await adminCall("admin.model.test", { method: "POST" });
        statusBox("#modelStatus", `模型接口正常：${data.message}`);
      } catch (err) {
        statusBox("#modelStatus", err.message, true);
      }
    });

    $("#loadUsers").addEventListener("click", async () => {
      try {
        const data = await adminCall(`admin.users&query=${encodeURIComponent($("#userQuery").value || "")}`);
        renderUsers(data.users || []);
      } catch (err) {
        statusBox("#adminStatus", err.message, true);
      }
    });

    $("#loadJobs").addEventListener("click", async () => {
      try { renderJobs((await adminCall("admin.jobs")).jobs || []); } catch (err) { statusBox("#adminStatus", err.message, true); }
    });
    $("#loadOrders").addEventListener("click", async () => {
      try { renderOrders((await adminCall("admin.orders")).orders || []); } catch (err) { statusBox("#adminStatus", err.message, true); }
    });

    $("#userForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await adminCall("admin.user.update", {
          method: "POST",
          body: JSON.stringify({
            user_id: Number($("#editUserId").value),
            email: $("#editEmail").value,
            free_generations: Number($("#editFree").value || 0),
            paid_generations: Number($("#editPaid").value || 0),
            status: $("#editStatus").value,
            note: $("#editNote").value
          })
        });
        statusBox("#userStatus", "用户已保存。");
        loadDashboard();
      } catch (err) {
        statusBox("#userStatus", err.message, true);
      }
    });

    $("#createPaidOrder").addEventListener("click", async () => {
      const userId = Number($("#editUserId").value);
      const count = Number(prompt("增加多少次付费生成次数？", "10") || 0);
      if (!userId || count <= 0) return;
      const amountYuan = Number(prompt("实收金额，单位元：", "99") || 0);
      try {
        await adminCall("admin.order.create", {
          method: "POST",
          body: JSON.stringify({
            user_id: userId,
            plan_name: "人工加次数",
            amount_cents: Math.round(amountYuan * 100),
            generation_count: count,
            status: "paid",
            payment_method: "manual",
            note: "管理员后台人工加次数"
          })
        });
        statusBox("#userStatus", "订单已创建，次数已增加。");
        loadDashboard();
      } catch (err) {
        statusBox("#userStatus", err.message, true);
      }
    });

    $("#cancelEdit").addEventListener("click", () => $("#userEditor").hidden = true);
    if (Api.adminToken) loadDashboard().catch(() => Api.setAdminToken(""));
  </script>
</body>
</html>
