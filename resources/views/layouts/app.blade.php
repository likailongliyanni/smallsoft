<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>@yield('title', '好办法浏览器自动化')</title>
    <meta name="description" content="好办法自动化帮你批量完成网页后台重复操作，适合发货、调价、上传资料、维护商品信息和填写网页表单。">
    <link rel="stylesheet" href="/assets/styles.css?v={{ time() }}">
    <script defer src="/assets/app.js?v={{ time() }}"></script>
</head>
<body data-page="@yield('page', 'home')">
    @if(!View::hasSection('hide-nav'))
    <header class="site-header">
        <a class="brand" href="/">
            <span class="brand-mark">好</span>
            <span>好办法自动化</span>
        </a>
        <nav class="site-nav">
            <a href="#features">功能</a>
            <a href="#pricing">价格</a>
            <a href="/tutorial">📖 教程</a>
            <a href="#contact">联系</a>
        </nav>
    </header>
    @endif

    <main>
        @yield('content')
    </main>

    <footer class="site-footer">
        <span>&copy; {{ date('Y') }} 好办法自动化</span>
    </footer>
</body>
</html>
