@extends('layouts.app')

@section('title', '好办法自动化 - 你操作一遍，软件批量替你操作')
@section('page', 'home')

@section('content')

<section class="hero">
    <div class="hero-badge">网页后台批量操作助手</div>
    <h1>你操作一遍<br>软件批量替你操作</h1>
    <p>发货、调价、上传资料、维护商品信息、填写网页表单<br>凡是需要一条一条重复点击和填写的工作，都可以交给软件批量完成</p>
    <div class="hero-actions">
        <a class="btn" href="/download">免费试用</a>
        <a class="btn btn-outline" href="/excel-automation">在线 EXCEL 工具</a>
    </div>
</section>

<section id="excel-tools" class="features">
    <h2>在线 EXCEL 工具 · 打开网页就能用</h2>
    <div class="feat-grid">
        <div class="feat">
            <div class="feat-ico">▧</div>
            <h3>图片提取</h3>
            <p>从 Excel 批量提取内嵌图片，AI 理解你的要求，按 69码 / 货号自动命名、分文件夹打包下载</p>
        </div>
        <div class="feat">
            <div class="feat-ico">⊞</div>
            <h3>表格整理</h3>
            <p>多个原始表合并成规范表，「品名 / 名称 / 商品名称」这类写法不一的字段 AI 自动归类，人工确认后一键合并</p>
        </div>
        <div class="feat">
            <div class="feat-ico">＋</div>
            <h3>更多功能陆续上线</h3>
            <p>数据清洗、智能分类、批量翻译等小工具持续更新。表格文件全程在浏览器本地处理，不上传服务器</p>
        </div>
    </div>
    <div class="excel-tools-cta">
        <a class="btn" href="/excel-automation">立即在线使用</a>
    </div>
</section>

<section id="features" class="features">
    <h2>它能帮你做什么</h2>
    <div class="feat-grid">
        <div class="feat">
            <div class="feat-ico">&#9654;</div>
            <h3>批量发货</h3>
            <p>按表格里的手机号、订单信息、快递单号，在网页后台一条一条自动查询和提交</p>
        </div>
        <div class="feat">
            <div class="feat-ico">&#9783;</div>
            <h3>批量调价</h3>
            <p>把要修改的商品和价格整理到表格里，软件按行打开、填写、保存</p>
        </div>
        <div class="feat">
            <div class="feat-ico">&#9733;</div>
            <h3>批量上传资料</h3>
            <p>适合商品图片、商品信息、附件资料等需要反复上传和提交的后台工作</p>
        </div>
        <div class="feat">
            <div class="feat-ico">&#9789;</div>
            <h3>维护商品信息</h3>
            <p>商品标题、规格、库存、分类、备注等资料，可以按表格批量录入或修改</p>
        </div>
        <div class="feat">
            <div class="feat-ico">&#9881;</div>
            <h3>填写网页表单</h3>
            <p>公司后台、ERP、店铺后台里的重复录入、查询、复制、提交，都能减少手工操作</p>
        </div>
        <div class="feat">
            <div class="feat-ico">&#9740;</div>
            <h3>特殊情况可接手</h3>
            <p>遇到页面不一样、需要判断、临时弹窗等情况，你可以手动处理，处理完继续跑</p>
        </div>
    </div>
</section>

<section class="features">
    <h2>使用方式很简单</h2>
    <div class="feat-grid">
        <div class="feat">
            <div class="feat-ico">1</div>
            <h3>先正常操作一遍</h3>
            <p>像平时工作一样，在网页后台完成一条示范操作，不需要写代码，也不用搭流程</p>
        </div>
        <div class="feat">
            <div class="feat-ico">2</div>
            <h3>把数据填进表格</h3>
            <p>手机号、订单号、价格、图片路径、商品资料等批量数据，整理到表格里</p>
        </div>
        <div class="feat">
            <div class="feat-ico">3</div>
            <h3>点击开始批量执行</h3>
            <p>软件按表格一行一行操作网页，标准步骤自动完成，特殊情况你再接手</p>
        </div>
    </div>
</section>

<section id="pricing" class="pricing">
    <h2>试用 &amp; 购买</h2>
    <p class="pricing-sub">适合发货、调价、商品资料维护、网页表单录入等重复工作</p>
    <div class="price-grid">
        <div class="price-card">
            <h3>🎁 免费试用</h3>
            <div class="price-tag">新用户赠送</div>
            <ul>
                <li>20 次自动化任务生成</li>
                <li>支持批量网页操作</li>
                <li>支持表格数据批量执行</li>
                <li>支持人工接手后继续</li>
            </ul>
            <a class="btn" href="/download">立即下载</a>
        </div>
        <div class="price-card hot">
            <div class="hot-tag">付费用户</div>
            <h3>💬 联系作者</h3>
            <div class="price-tag">按需购买额度</div>
            <ul>
                <li>免费次数用完后</li>
                <li>可购买更多生成次数</li>
                <li>支持复杂网页后台场景</li>
                <li>可沟通企业内部使用</li>
            </ul>
            <a class="btn btn-outline" href="#contact">联系咨询</a>
        </div>
    </div>
</section>

<section id="contact" class="contact">
    <h2>联系购买</h2>
    <p>添加微信好友，备注「自动化」，咨询试用、购买额度或企业使用</p>
    <div class="contact-card">
        <div class="contact-row"><span>微信号</span><strong>18033086531</strong></div>
        <div class="contact-row"><span>手机号</span><strong>18033086531</strong></div>
    </div>
    <p class="small-text">工作时间 10 分钟内回复，非工作时间 24 小时内回复</p>
</section>

@endsection
