<?php

namespace App\Http\Controllers;

use App\Services\StatsAnalysisService;
use App\Services\TokenService;
use Illuminate\Http\Request;

class StatsAnalysisController extends Controller
{
    public function plan(Request $request, TokenService $tokens, StatsAnalysisService $service): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录后使用 AI 智能分析。');

        $data = $request->validate([
            'instruction' => ['nullable', 'string', 'max:2000'],
            'summary' => ['required', 'array'],
            'summary.row_count' => ['nullable', 'integer', 'min:0'],
            'summary.columns' => ['required', 'array', 'min:1', 'max:200'],
            'summary.columns.*.name' => ['required', 'string', 'max:255'],
            'summary.columns.*.kind' => ['nullable', 'string', 'max:20'],
        ]);

        return $this->ok($service->makePlan(
            $data['summary'],
            trim((string) ($data['instruction'] ?? '')),
        ));
    }

    public function insight(Request $request, TokenService $tokens, StatsAnalysisService $service): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录后使用 AI 解读。');

        $data = $request->validate([
            'results' => ['required', 'array', 'min:1', 'max:40'],
            'results.*.dimension' => ['required', 'string', 'max:255'],
            'results.*.agg' => ['nullable', 'string', 'max:20'],
            'results.*.metric' => ['nullable', 'string', 'max:255'],
            'results.*.top' => ['nullable', 'array', 'max:50'],
        ]);

        return $this->ok($service->makeInsight($data['results']));
    }
}
