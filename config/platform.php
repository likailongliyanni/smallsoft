<?php

return [
    'free_generations' => (int) env('PLATFORM_FREE_GENERATIONS', 20),
    // 智能截图软件新软件编号首次登记赠送的免费图片处理额度（张）。
    'snap_saver_default_quota' => (int) env('SNAP_SAVER_DEFAULT_QUOTA', 10),
    // AI档案管理按设备编号建立积分账户，新设备默认赠送30积分。
    'aidoc_default_quota' => (int) env('AIDOC_DEFAULT_POINTS', 30),
    'aidoc_overdraft_limit' => (int) env('AIDOC_OVERDRAFT_LIMIT', 20),
    'aidoc_contact_wechat' => (string) env('AIDOC_CONTACT_WECHAT', '18033086531'),
    'aidoc_point_packages' => [
        ['points' => 50, 'standard_price' => null, 'launch_price' => 2.99, 'once_per_device' => true],
        ['points' => 200, 'standard_price' => 29.9, 'launch_price' => 9.9, 'once_per_device' => false],
        ['points' => 500, 'standard_price' => 79.9, 'launch_price' => 19.9, 'once_per_device' => false],
        ['points' => 1000, 'standard_price' => 159.9, 'launch_price' => 29.9, 'once_per_device' => false],
    ],
    'aidoc_billing_rules' => [
        'JPG、PNG等图片识别：每张1积分',
        'PDF、Word识别：每页1积分',
        'AI智能查找或连续追问：每次成功回答1积分',
        '合同生成：按最终页数每页2积分',
        '任务处理失败、未找到资料或仅进行限制提醒：不扣积分',
    ],
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
    // AI 图片描述（PDF 排版用）是否扣额度。默认 false=免费期：不扣额度只记调用日志；
    // 将来要收费时把 DOC_DESCRIBE_CHARGE 设为 true 即按 1 次/张扣费，前端无需改动。
    'doc_describe_charge' => filter_var(env('DOC_DESCRIBE_CHARGE', false), FILTER_VALIDATE_BOOLEAN),
];
