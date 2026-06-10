<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Announcement extends Model
{
    protected $fillable = ['content', 'enabled', 'priority', 'expires_at'];
    protected $casts = [
        'enabled' => 'boolean',
        'expires_at' => 'datetime',
    ];

    public function scopeActive($q)
    {
        return $q->where('enabled', true)
            ->where(function ($q) {
                $q->whereNull('expires_at')->orWhere('expires_at', '>', now());
            });
    }
}
