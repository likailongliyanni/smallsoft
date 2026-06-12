<?php

return [
    'free_generations' => (int) env('PLATFORM_FREE_GENERATIONS', 20),
    'snap_saver_default_quota' => (int) env('SNAP_SAVER_DEFAULT_QUOTA', 50),
    'normal_step_limit' => (int) env('PLATFORM_NORMAL_STEP_LIMIT', 50),
    'advanced_step_limit' => (int) env('PLATFORM_ADVANCED_STEP_LIMIT', 80),
    'user_token_days' => (int) env('USER_TOKEN_DAYS', 30),
    'admin_token_days' => (int) env('ADMIN_TOKEN_DAYS', 7),
    'allow_local_fallback' => filter_var(env('AI_ALLOW_LOCAL_FALLBACK', true), FILTER_VALIDATE_BOOLEAN),
];
