<?php

namespace App\Http\Controllers;

use App\Services\TableTidyPlanService;
use App\Services\TokenService;
use Illuminate\Http\Request;

/**
 * 通用脏 Excel 结构化：浏览器只上报本地算好的轻量摘要（表头候选 + 列形态统计 + 少量样例），
 * 后端用 AI 产出「目标结构 + 清洗策略」计划，真正整理在浏览器本地执行。
 */
class TableTidyController extends Controller
{
    public function plan(Request $request, TokenService $tokens, TableTidyPlanService $planner): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录后使用 AI 表格整理。');

        $data = $request->validate([
            'instruction' => ['nullable', 'string', 'max:4000'],
            'summary' => ['required', 'array'],
            'summary.sheet_name' => ['nullable', 'string', 'max:255'],
            'summary.regions' => ['required', 'array', 'min:1', 'max:30'],
            'summary.regions.*.columns' => ['required', 'array', 'max:200'],
        ]);

        return $this->ok($planner->makePlan(
            $data['summary'],
            trim((string) ($data['instruction'] ?? '')),
        ));
    }
}
