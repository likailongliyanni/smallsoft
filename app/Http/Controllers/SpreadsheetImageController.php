<?php

namespace App\Http\Controllers;

use App\Services\SpreadsheetImagePlanService;
use App\Services\TokenService;
use Illuminate\Http\Request;

class SpreadsheetImageController extends Controller
{
    public function plan(Request $request, TokenService $tokens, SpreadsheetImagePlanService $planner): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录后使用 AI 规则生成。');

        $data = $request->validate([
            'instruction' => ['required', 'string', 'max:4000'],
            'summary' => ['required', 'array'],
            'summary.file_name' => ['nullable', 'string', 'max:255'],
            'summary.sheets' => ['required', 'array', 'max:30'],
            'options' => ['nullable', 'array'],
        ]);

        return $this->ok($planner->makePlan(
            $data['summary'],
            trim((string) $data['instruction']),
            $data['options'] ?? [],
        ));
    }
}
