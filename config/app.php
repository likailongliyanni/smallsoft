<?php

return [
    'name' => env('APP_NAME', '好办法网页自动化平台'),
    'env' => env('APP_ENV', 'production'),
    'debug' => (bool) env('APP_DEBUG', false),
    'url' => env('APP_URL', 'https://tools.haobanfa.online'),
    'asset_url' => env('ASSET_URL'),
    'timezone' => 'Asia/Shanghai',
    'locale' => env('APP_LOCALE', 'zh_CN'),
    'fallback_locale' => env('APP_FALLBACK_LOCALE', 'zh_CN'),
    'faker_locale' => env('APP_FAKER_LOCALE', 'zh_CN'),
    'cipher' => 'AES-256-CBC',
    'key' => env('APP_KEY'),
    'previous_keys' => [
        ...array_filter(explode(',', env('APP_PREVIOUS_KEYS', ''))),
    ],
    'maintenance' => [
        'driver' => env('APP_MAINTENANCE_DRIVER', 'file'),
        'store' => env('APP_MAINTENANCE_STORE', 'database'),
    ],
];
