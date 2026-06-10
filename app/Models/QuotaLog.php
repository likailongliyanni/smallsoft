<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class QuotaLog extends Model
{
    protected $fillable = [
        'user_id',
        'admin_id',
        'change_value',
        'source',
        'note',
    ];

    protected function casts(): array
    {
        return [
            'change_value' => 'integer',
        ];
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
}
