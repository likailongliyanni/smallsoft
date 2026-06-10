<?php

namespace App\Http\Controllers;

use App\Services\CosUploadService;
use App\Services\TokenService;
use Illuminate\Http\Request;

class AiImageController extends Controller
{
    public function upload(Request $request, TokenService $tokens, CosUploadService $cos): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录');

        $data = $request->validate([
            'image' => ['required', 'file', 'mimes:jpg,jpeg,png,webp', 'max:8192'],
            'flow_name' => ['nullable', 'string', 'max:120'],
            'step_index' => ['nullable', 'integer', 'min:1', 'max:999'],
        ]);

        $uploaded = $cos->uploadAutomationImage(
            $request->file('image'),
            (int) $user->id,
            (string) ($data['flow_name'] ?? ''),
            isset($data['step_index']) ? (int) $data['step_index'] : null,
        );

        return $this->ok(['image' => $uploaded]);
    }
}
