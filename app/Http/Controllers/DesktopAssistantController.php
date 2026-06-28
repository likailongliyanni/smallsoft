<?php

namespace App\Http\Controllers;

use App\Services\DocumentAssistantService;
use App\Services\TokenService;
use Illuminate\Http\Request;
use Throwable;

class DesktopAssistantController extends Controller
{
    public function chat(Request $request, TokenService $tokens, DocumentAssistantService $assistant): array
    {
        @set_time_limit(180);

        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登记软件编号');
        abort_if($user->software_code !== 'aidoc', 403, '当前软件编号不能使用 AI 档案秘书。');

        $data = $request->validate([
            'message' => ['required', 'string', 'max:2000'],
            'need_organize' => ['nullable', 'boolean'],
            'use_watermark' => ['nullable', 'boolean'],
            'watermark_text' => ['nullable', 'string', 'max:100'],
            'training_notes' => ['nullable', 'array', 'max:8'],
            'training_notes.*.id' => ['required', 'integer', 'min:1'],
            'training_notes.*.title' => ['required', 'string', 'max:100'],
            'training_notes.*.trigger_keywords' => ['nullable', 'string', 'max:500'],
            'training_notes.*.instruction' => ['required', 'string', 'max:12000'],
            'template_pool' => ['nullable', 'array', 'max:16'],
            'template_pool.*.id' => ['required', 'integer', 'min:1'],
            'template_pool.*.source_document_id' => ['nullable', 'integer', 'min:0'],
            'template_pool.*.name' => ['required', 'string', 'max:100'],
            'template_pool.*.document_type' => ['required', 'string', 'max:80'],
            'template_pool.*.type_label' => ['nullable', 'string', 'max:100'],
            'template_pool.*.source_file_name' => ['nullable', 'string', 'max:255'],
            'template_pool.*.summary' => ['nullable', 'string', 'max:500'],
            'template_pool.*.status' => ['nullable', 'string', 'max:30'],
            'template_pool.*.variables' => ['nullable', 'array', 'max:50'],
            'template_pool.*.template_text' => ['required', 'string', 'max:18000'],
            'history' => ['nullable', 'array', 'max:20'],
            'history.*.role' => ['required', 'string', 'in:user,assistant'],
            'history.*.content' => ['required', 'string', 'max:3000'],
            'inventory' => ['required', 'array', 'max:400'],
            'inventory.*.id' => ['required', 'integer', 'min:1'],
            'inventory.*.file_name' => ['nullable', 'string', 'max:255'],
            'inventory.*.document_type' => ['nullable', 'string', 'max:80'],
            'inventory.*.type_label' => ['nullable', 'string', 'max:100'],
            'inventory.*.company' => ['nullable', 'string', 'max:200'],
            'inventory.*.brand' => ['nullable', 'string', 'max:150'],
            'inventory.*.issued_at' => ['nullable', 'string', 'max:40'],
            'inventory.*.expires_at' => ['nullable', 'string', 'max:40'],
            'inventory.*.scope' => ['nullable', 'string', 'max:500'],
        ]);

        try {
            return $this->ok($assistant->chat(
                trim($data['message']),
                array_values($data['history'] ?? []),
                array_values($data['inventory']),
                [
                    'need_organize' => (bool) ($data['need_organize'] ?? false),
                    'use_watermark' => (bool) ($data['use_watermark'] ?? false),
                    'watermark_text' => trim((string) ($data['watermark_text'] ?? '')),
                    'training_notes' => array_values($data['training_notes'] ?? []),
                    'template_pool' => array_values($data['template_pool'] ?? []),
                ],
            ));
        } catch (Throwable $e) {
            abort(422, $e->getMessage());
        }
    }
}
