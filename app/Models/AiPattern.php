<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class AiPattern extends Model
{
    protected $table = 'ai_patterns';

    protected $fillable = [
        'code',
        'category',
        'title',
        'content',
        'enabled',
        'priority',
        'changelog',
    ];

    protected $casts = [
        'enabled' => 'boolean',
        'priority' => 'integer',
    ];
}
