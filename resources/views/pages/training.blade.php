@extends('layouts.app')

@section('title', '免费训练场 - 好办法网页自动化平台')
@section('page', 'training')

@section('content')
<section class="page-title">
    <p class="eyebrow">免费训练场</p>
    <h1>用一个标准练习页面教用户登记流程</h1>
    <p>这里用于收集训练样例和教程反馈。图片会在浏览器端压缩到 400px 以内，再提交到后台。</p>
</section>

<section class="workspace">
    <div class="panel">
        <h2>练习表单</h2>
        <form id="trainingForm" class="form">
            <label>
                练习标题
                <input name="title" value="商品资料提交练习" required>
            </label>
            <label>
                练习数据 JSON
                <textarea name="payload" rows="9">{
  "product_name": "示例商品",
  "price": "99.00",
  "category": "默认分类",
  "image_field": "主图"
}</textarea>
            </label>
            <label>
                上传演示图片
                <input name="image" type="file" accept="image/*">
            </label>
            <button class="button primary" type="submit">提交训练样例</button>
        </form>
        <pre id="trainingResult" class="result-box"></pre>
    </div>

    <div class="panel">
        <h2>教程要点</h2>
        <div class="check-list">
            <p><strong>文本输入：</strong>先点击输入框，再登记文本输入，并填写字段名称。</p>
            <p><strong>普通按钮：</strong>点击后登记为单击，不需要字段名称。</p>
            <p><strong>文件上传：</strong>登记文件上传类型，并填写字段名称，例如主图、详情图。</p>
            <p><strong>安全验证：</strong>验证码、短信、滑块不绕过，登记为人工处理点。</p>
        </div>
    </div>
</section>
@endsection
