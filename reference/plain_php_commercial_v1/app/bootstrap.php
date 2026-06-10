<?php
declare(strict_types=1);

date_default_timezone_set('Asia/Shanghai');

$configPath = __DIR__ . '/../config/config.php';
if (!is_file($configPath)) {
    $configPath = __DIR__ . '/../config/config.sample.php';
}
$APP_CONFIG = require $configPath;

require_once __DIR__ . '/HttpException.php';
require_once __DIR__ . '/helpers.php';
require_once __DIR__ . '/Database.php';
require_once __DIR__ . '/AiService.php';
