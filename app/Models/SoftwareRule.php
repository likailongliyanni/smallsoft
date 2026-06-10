<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class SoftwareRule extends Model
{
    protected $table = 'software_rules';

    protected $fillable = [
        'version',
        'is_active',
        'rules',
        'changelog',
    ];

    protected $casts = [
        'rules' => 'array',
        'is_active' => 'boolean',
    ];

    public static function active(): ?self
    {
        return self::query()->where('is_active', true)->latest('id')->first();
    }
}
