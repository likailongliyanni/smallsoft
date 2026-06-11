<?php

namespace App\Http\Controllers;

use App\Services\TableMergePlanService;
use App\Services\TokenService;
use Illuminate\Http\Request;

class TableMergeController extends Controller
{
    public function plan(Request $request, TokenService $tokens, TableMergePlanService $planner): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录后使用 AI 字段归类。');

        $data = $request->validate([
            'instruction' => ['nullable', 'string', 'max:4000'],
            'summary' => ['required', 'array'],
            'summary.files' => ['required', 'array', 'min:1', 'max:10'],
            'summary.files.*.file_name' => ['nullable', 'string', 'max:255'],
            'summary.files.*.sheets' => ['required', 'array', 'max:30'],
            'summary.template' => ['nullable', 'array'],
            'summary.template.file_name' => ['nullable', 'string', 'max:255'],
            'summary.template.fields' => ['nullable', 'array', 'max:100'],
        ]);

        return $this->ok($planner->makePlan(
            $data['summary'],
            trim((string) ($data['instruction'] ?? '')),
        ));
    }
}
