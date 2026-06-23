<?php

namespace App\Http\Controllers;

use App\Services\TablePivotPlanService;
use App\Services\TokenService;
use Illuminate\Http\Request;

/**
 * 智能统计（透视汇总）：浏览器只上报本地算好的列摘要（表头 + 值形态 + 样例），
 * 后端用 AI 产出「透视计划」（维度 / 度量 / 筛选 / 时间粒度），真正统计在浏览器本地执行。
 */
class TablePivotController extends Controller
{
    public function plan(Request $request, TokenService $tokens, TablePivotPlanService $planner): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录后使用 AI 智能统计。');

        $data = $request->validate([
            'instruction' => ['nullable', 'string', 'max:4000'],
            'summary' => ['required', 'array'],
            'summary.sheet_name' => ['nullable', 'string', 'max:255'],
            'summary.columns' => ['required', 'array', 'min:1', 'max:200'],
        ]);

        return $this->ok($planner->makePlan(
            $data['summary'],
            trim((string) ($data['instruction'] ?? '')),
        ));
    }
}
