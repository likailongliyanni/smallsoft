<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class FeedbackLog extends Model
{
    protected $fillable = [
        'user_id',
        'category',
        'flow_name',
        'source',
        'content',
        'error_message',
        'template_path',
        'meta',
        'contact',
        'status',
    ];

    protected $casts = [
        'meta' => 'array',
    ];

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
}
