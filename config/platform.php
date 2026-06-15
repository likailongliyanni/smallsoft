<?php

return [
    'free_generations' => (int) env('PLATFORM_FREE_GENERATIONS', 20),
    // 智能截图软件新软件编号首次登记赠送的免费图片处理额度（张）。
    'snap_saver_default_quota' => (int) env('SNAP_SAVER_DEFAULT_QUOTA', 10),
    // 充值套餐价目表（单一来源）：amount_cents=价格(分)，quota=可处理张数。
    // 后台「调整额度」面板会按此渲染快捷按钮，客户付多少就点哪一档。
    'snap_saver_packages' => [
        ['amount_cents' => 990, 'quota' => 20],
        ['amount_cents' => 2000, 'quota' => 50],
        ['amount_cents' => 3000, 'quota' => 80],
        ['amount_cents' => 5000, 'quota' => 150],
        ['amount_cents' => 10000, 'quota' => 400],
    ],
    'normal_step_limit' => (int) env('PLATFORM_NORMAL_STEP_LIMIT', 50),
    'advanced_step_limit' => (int) env('PLATFORM_ADVANCED_STEP_LIMIT', 80),
    'user_token_days' => (int) env('USER_TOKEN_DAYS', 30),
    'admin_token_days' => (int) env('ADMIN_TOKEN_DAYS', 7),
    'allow_local_fallback' => filter_var(env('AI_ALLOW_LOCAL_FALLBACK', true), FILTER_VALIDATE_BOOLEAN),
];
