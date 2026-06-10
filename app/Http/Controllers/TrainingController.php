<?php

namespace App\Http\Controllers;

use App\Models\TrainingSubmission;
use App\Services\TokenService;
use Illuminate\Http\Request;
use Illuminate\Support\Str;

class TrainingController extends Controller
{
    public function store(Request $request, TokenService $tokens): array
    {
        $data = $request->validate([
            'title' => ['required', 'string', 'max:120'],
            'payload' => ['nullable'],
            'image' => ['nullable', 'image', 'max:2048'],
        ]);

        $payload = $data['payload'] ?? null;
        if (is_string($payload) && $payload !== '') {
            $decoded = json_decode($payload, true);
            $payload = json_last_error() === JSON_ERROR_NONE ? $decoded : ['raw' => $payload];
        }

        $imagePath = null;
        if ($request->hasFile('image')) {
            $dir = storage_path('app/private/training_uploads');
            if (! is_dir($dir)) {
                mkdir($dir, 0755, true);
            }

            $file = $request->file('image');
            $name = Str::uuid().'.'.$file->getClientOriginalExtension();
            $file->move($dir, $name);
            $imagePath = 'training_uploads/'.$name;
        }

        $user = $tokens->userFromRequest($request);
        $submission = TrainingSubmission::create([
            'user_id' => $user?->id,
            'title' => $data['title'],
            'payload' => is_array($payload) ? $payload : null,
            'image_path' => $imagePath,
            'ip' => $request->ip(),
            'user_agent' => substr((string) $request->userAgent(), 0, 255),
        ]);

        return $this->ok(['submission_id' => $submission->id]);
    }
}
