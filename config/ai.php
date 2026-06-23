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

    // 通过 config 读取，保证 `php artisan config:cache` 之后服务里仍能拿到 Key
    // （配置缓存生效时 .env 不再加载，运行时 env() 一律返回 null）。
    'dashscope_api_key' => env('DASHSCOPE_API_KEY', env('ALIYUN_API_KEY', '')),

    // 图片修复（去水印/去广告/白底上图）走阿里云百炼万相图像编辑模型。
    // wan2.7-image 与旧的 qwen-image-2.0 用同一个 multimodal-generation 同步端点、
    // 同样的 input.messages（图+文）结构，切换只需改模型名；注意万相不支持
    // negative_prompt / prompt_extend 参数。同样走 config 以兼容 config:cache。
    'image_repair' => [
        'model' => env('ALIYUN_IMAGE_REPAIR_MODEL', env('DASHSCOPE_IMAGE_REPAIR_MODEL', 'wan2.7-image')),
        'size' => env('ALIYUN_IMAGE_REPAIR_SIZE', ''),
    ],

    // AI 商品主视觉 / 电商场景重构（多图参考重新生成电商图）。
    // model 留空则复用 image_repair 模型；百炼上线更强的多图融合/编辑模型后，
    // 在后台 ModelConfig(purpose=scene_reconstruct) 或这里改个模型名即可，无需改代码。
    // size 留空则按用户选的比例自动给（1:1→1024*1024 等）。
    'scene_reconstruct' => [
        'model' => env('ALIYUN_SCENE_MODEL', ''),
        'size' => env('ALIYUN_SCENE_SIZE', ''),
    ],
];
