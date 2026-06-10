<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class User extends Model
{
    use HasFactory;

    protected $fillable = [
        'username',
        'name',
        'nickname',
        'nickname_edit_count',
        'email',
        'mobile',
        'password',
        'role',
        'status',
        'free_generations',
        'paid_generations',
        'last_login_at',
    ];

    protected $hidden = [
        'password',
    ];

    protected function casts(): array
    {
        return [
            'last_login_at' => 'datetime',
            'free_generations' => 'integer',
            'paid_generations' => 'integer',
        ];
    }

    public function tokens(): HasMany
    {
        return $this->hasMany(UserToken::class);
    }

    public function jobs(): HasMany
    {
        return $this->hasMany(GenerationJob::class);
    }

    public function availableGenerations(): int
    {
        return (int) $this->free_generations + (int) $this->paid_generations;
    }
}
