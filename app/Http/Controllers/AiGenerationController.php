<?php

namespace App\Http\Controllers;

use App\Services\AliyunAiService;
use App\Services\AutomationFlowValidator;
use App\Services\TokenService;
use Illuminate\Http\Request;

class AiGenerationController extends Controller
{
    public function generate(
        Request $request,
        TokenService $tokens,
        AutomationFlowValidator $validator,
        AliyunAiService $aliyun
    ): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录');

        $data = $request->validate([
            'flow_name' => ['required', 'string', 'max:120'],
            'mode' => ['nullable', 'string', 'in:normal,advanced'],
            'format' => ['nullable', 'string', 'in:json_dsl_v1,python_v1'],
            'category' => ['nullable', 'string', 'in:browser,excel,word,ps,pdf,jst'],
            'model_key' => ['nullable', 'string', 'in:code,balanced,strong,fast,vision'],
            'steps' => ['required', 'array', 'min:1'],
            'steps.*' => ['array'],
            'template_fields' => ['nullable', 'array'],
            'images' => ['nullable', 'array', 'max:20'],
            'notes' => ['nullable', 'string', 'max:6000'],
            // 多次录制融合（v2.0+ 新增）
            'multi_session' => ['nullable', 'boolean'],
            'session_count' => ['nullable', 'integer', 'min:2', 'max:10'],
            'sessions' => ['nullable', 'array', 'max:10'],
            'sessions.*' => ['array'],
            'sessions.*.session_index' => ['nullable', 'integer'],
            'sessions.*.step_count' => ['nullable', 'integer'],
            'sessions.*.steps' => ['nullable', 'array'],
        ]);

        $mode = $data['mode'] ?? 'normal';
        $limit = $mode === 'advanced'
            ? config('platform.advanced_step_limit')
            : config('platform.normal_step_limit');

        $data = $validator->normalize($data, $limit);

        $modelKey = $data['model_key'] ?? AliyunAiService::DEFAULT_KEY;
        $job = $aliyun->generate($user, $data, $modelKey);

        return $this->ok([
            'job' => [
                'id' => $job->id,
                'status' => $job->status,
                'flow_name' => $job->flow_name,
                'step_count' => $job->step_count,
                'result_script' => $job->result_script,
                'reasoning_content' => $job->reasoning_content,
                'error_message' => $job->error_message,
                'warnings' => $job->warnings,
                'used_provider' => $job->used_provider,
                'used_model' => $job->used_model,
                'usage' => $job->usage,
                'duration_ms' => $job->duration_ms,
            ],
        ]);
    }

    public function listModels(AliyunAiService $aliyun): array
    {
        return $this->ok([
            'models' => $aliyun->listModels(),
            'default' => AliyunAiService::DEFAULT_KEY,
        ]);
    }
}
