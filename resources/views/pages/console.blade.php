@extends('layouts.app')

@section('title', '用户控制台 - 好办法网页自动化平台')
@section('page', 'console')

@section('content')
<section class="page-title">
    <p class="eyebrow">用户控制台</p>
    <h1>提交录制流程，生成批量自动化脚本</h1>
    <p>这里模拟软件端调用后台。正式软件可以直接调用同一套 API。</p>
</section>

<section class="workspace two-col">
    <div class="panel">
        <h2>账号</h2>
        <div class="tabs">
            <button class="tab active" data-user-tab="login">登录</button>
            <button class="tab" data-user-tab="register">注册</button>
        </div>
        <form id="loginForm" class="form">
            <label>账号<input name="username" required></label>
            <label>密码<input name="password" type="password" required></label>
            <button class="button primary" type="submit">登录</button>
        </form>
        <form id="registerForm" class="form hidden">
            <label>账号<input name="username" required></label>
            <label>密码<input name="password" type="password" required minlength="6"></label>
            <label>昵称<input name="name"></label>
            <button class="button primary" type="submit">注册并领取免费次数</button>
        </form>
        <div id="userBox" class="status-box">未登录</div>
    </div>

    <div class="panel">
        <h2>AI 脚本生成</h2>
        <form id="generateForm" class="form">
            <label>流程名称<input name="flow_name" value="商品资料批量提交"></label>
            <label>
                模式
                <select name="mode">
                    <option value="normal">普通模式 20 步</option>
                    <option value="advanced">高级模式 30 步</option>
                </select>
            </label>
            <label>
                录制流程 JSON
                <textarea name="payload" rows="18">{
  "steps": [
    {
      "order": 1,
      "event": "click",
      "interaction_type": "text_input",
      "field_name": "商品名称",
      "xpath": "//input[@name='product_name']",
      "description": "点击商品名称输入框"
    },
    {
      "order": 2,
      "event": "input",
      "interaction_type": "text_input",
      "field_name": "商品名称",
      "xpath": "//input[@name='product_name']",
      "description": "从表格字段输入商品名称"
    },
    {
      "order": 3,
      "event": "click",
      "interaction_type": "single_click",
      "xpath": "//button[contains(., '提交')]",
      "description": "点击提交按钮"
    }
  ],
  "template_fields": [
    {"field_name": "商品名称", "type": "text", "required": true}
  ],
  "notes": "登录和验证码由人工完成后继续运行。"
}</textarea>
            </label>
            <button class="button primary" type="submit">生成脚本</button>
        </form>
        <pre id="generateResult" class="result-box tall"></pre>
    </div>
</section>
@endsection
