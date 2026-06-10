<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class GenerationJob extends Model
{
    protected $fillable = [
        'user_id',
        'flow_name',
        'status',
        'step_count',
        'request_payload',
        'result_script',
        'reasoning_content',
        'error_message',
        'warnings',
        'used_provider',
        'used_model',
        'usage',
        'duration_ms',
    ];

    protected function casts(): array
    {
        return [
            'request_payload' => 'array',
            'warnings' => 'array',
            'usage' => 'array',
            'step_count' => 'integer',
            'duration_ms' => 'integer',
        ];
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
}
