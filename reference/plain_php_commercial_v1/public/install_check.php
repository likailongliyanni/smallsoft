<?php
$checks = [
    'PHP >= 8.1' => version_compare(PHP_VERSION, '8.1.0', '>='),
    'PDO' => extension_loaded('pdo'),
    'PDO MySQL' => extension_loaded('pdo_mysql'),
    'cURL' => extension_loaded('curl'),
    'mbstring' => extension_loaded('mbstring'),
    'config/config.php exists' => is_file(__DIR__ . '/../config/config.php'),
    'storage writable' => is_writable(__DIR__ . '/../storage'),
];
header('Content-Type: text/html; charset=utf-8');
?>
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>安装检查</title>
  <link rel="stylesheet" href="/assets/styles.css">
</head>
<body>
  <main class="container section">
    <div class="panel">
      <h1 style="font-size:32px">网页自动化工作室 PHP 商业版安装检查</h1>
      <table>
        <thead><tr><th>项目</th><th>结果</th></tr></thead>
        <tbody>
        <?php foreach ($checks as $name => $ok): ?>
          <tr><td><?= htmlspecialchars($name) ?></td><td><?= $ok ? 'OK' : 'FAIL' ?></td></tr>
        <?php endforeach; ?>
        </tbody>
      </table>
      <p>全部 OK 后，建议删除或改名 install_check.php。</p>
    </div>
  </main>
</body>
</html>
