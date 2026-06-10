<?php

return [
    'default_provider' => env('AI_PROVIDER', 'aliyun'),
    'providers' => [
        'aliyun' => [
            'name' => 'Aliyun Bailian / Qwen',
            'base_url' => env('ALIYUN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
            'model' => env('ALIYUN_MODEL', 'qwen3-coder-next'),
            'api_key_env' => 'DASHSCOPE_API_KEY',
            'thinking_enabled' => false,
            'reasoning_effort' => 'medium',
            'presets' => [
                'Vision strong' => 'qwen3.6-plus',
                'Vision low cost' => 'qwen3.6-flash',
                'Script strong' => 'qwen3-coder-next',
                'General strong' => 'qwen3.6-plus',
            ],
        ],
        'deepseek' => [
            'name' => 'DeepSeek',
            'base_url' => env('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
            'model' => env('DEEPSEEK_MODEL', 'deepseek-v4-pro'),
            'thinking_enabled' => filter_var(env('DEEPSEEK_THINKING_ENABLED', true), FILTER_VALIDATE_BOOLEAN),
            'reasoning_effort' => env('DEEPSEEK_REASONING_EFFORT', 'high'),
        ],
        'openai-compatible' => [
            'name' => 'OpenAI Compatible',
            'base_url' => env('OPENAI_COMPATIBLE_BASE_URL'),
            'model' => env('OPENAI_COMPATIBLE_MODEL'),
        ],
    ],
    'defaults' => [
        'vision' => [
            'provider' => 'aliyun',
            'base_url' => env('ALIYUN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
            'model' => env('ALIYUN_VISION_MODEL', 'qwen3.6-plus'),
            'temperature' => 0.1,
            'max_tokens' => 2048,
            'request_timeout' => 120,
        ],
        'script' => [
            'provider' => 'aliyun',
            'base_url' => env('ALIYUN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
            'model' => env('ALIYUN_SCRIPT_MODEL', 'qwen3-coder-next'),
            'temperature' => 0.1,
            'max_tokens' => 8192,
            'request_timeout' => 180,
        ],
    ],
    'temperature' => (float) env('AI_TEMPERATURE', 0.2),
    'max_tokens' => (int) env('AI_MAX_TOKENS', 8192),
    'request_timeout' => (int) env('AI_REQUEST_TIMEOUT', 180),
];
