<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Order extends Model
{
    protected $fillable = [
        'user_id',
        'order_no',
        'plan_name',
        'quota',
        'amount_cents',
        'status',
        'payment_channel',
        'payment_trade_no',
        'paid_at',
    ];

    protected function casts(): array
    {
        return [
            'quota' => 'integer',
            'amount_cents' => 'integer',
            'paid_at' => 'datetime',
        ];
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
}
