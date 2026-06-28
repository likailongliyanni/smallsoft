<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;

class SoftwareRelease extends Model
{
    protected $fillable = [
        'software_code',
        'software_name',
        'version',
        'platform',
        'file_name',
        'storage_path',
        'file_size',
        'sha256',
        'release_notes',
        'enabled',
        'downloads_count',
        'created_by',
        'published_at',
    ];

    protected $casts = [
        'enabled' => 'boolean',
        'file_size' => 'integer',
        'downloads_count' => 'integer',
        'published_at' => 'datetime',
    ];

    public function scopeActive(Builder $query): Builder
    {
        return $query->where('enabled', true);
    }
}
