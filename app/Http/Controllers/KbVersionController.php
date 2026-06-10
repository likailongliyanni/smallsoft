<?php

namespace App\Http\Controllers;

use App\Services\KbVersionService;
use Illuminate\Http\Request;

/**
 * 经验库版本（公开接口，客户端首页用）
 */
class KbVersionController extends Controller
{
    public function show(Request $request, KbVersionService $kb): array
    {
        $meta = $kb->current();

        return [
            'ok' => true,
            'software_version' => config('app.software_version', '1.0.0'),
            'kb_version' => $meta['version'] ?? '1.0.0',
            'kb_updated_at' => $meta['updated_at'] ?? null,
            'kb_patterns_count' => $meta['count'] ?? 0,
            'kb_latest_change' => $meta['latest_change'] ?? null,
        ];
    }
}
