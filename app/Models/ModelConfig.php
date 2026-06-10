<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class ModelConfig extends Model
{
    protected $fillable = [
        'purpose',
        'provider',
        'base_url',
        'model',
        'api_key_encrypted',
        'system_prompt',
        'enabled',
        'temperature',
        'max_tokens',
        'thinking_enabled',
        'reasoning_effort',
        'request_timeout',
        'last_tested_at',
        'last_test_status',
        'last_test_message',
        'last_usage',
    ];

    protected function casts(): array
    {
        return [
            'enabled' => 'boolean',
            'temperature' => 'float',
            'max_tokens' => 'integer',
            'thinking_enabled' => 'boolean',
            'request_timeout' => 'integer',
            'last_tested_at' => 'datetime',
            'last_usage' => 'array',
        ];
    }
}
