<?php

namespace App\Http\Controllers;

use App\Models\Announcement;
use App\Services\TokenService;
use Illuminate\Http\Request;

class AnnouncementController extends Controller
{
    /**
     * GET /api/announcements
     * 公开接口：客户端公告栏滚动显示用
     */
    public function index(): array
    {
        $items = Announcement::active()
            ->orderBy('priority')
            ->orderByDesc('id')
            ->limit(20)
            ->get(['id', 'content', 'priority', 'created_at', 'expires_at']);

        return [
            'ok' => true,
            'count' => $items->count(),
            'items' => $items,
        ];
    }

    /** GET /api/admin/announcements */
    public function adminList(Request $request, TokenService $tokens): array
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '管理员未登录');

        $items = Announcement::query()
            ->orderByDesc('id')
            ->limit(200)
            ->get();
        return $this->ok(['items' => $items]);
    }

    /** POST /api/admin/announcements */
    public function adminStore(Request $request, TokenService $tokens): array
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '管理员未登录');

        $data = $request->validate([
            'id' => ['nullable', 'integer'],
            'content' => ['required', 'string', 'max:500'],
            'enabled' => ['nullable', 'boolean'],
            'priority' => ['nullable', 'integer', 'min:0', 'max:999'],
            'expires_at' => ['nullable', 'date'],
        ]);

        $payload = [
            'content' => $data['content'],
            'enabled' => (bool) ($data['enabled'] ?? true),
            'priority' => (int) ($data['priority'] ?? 50),
            'expires_at' => $data['expires_at'] ?? null,
        ];

        if (! empty($data['id'])) {
            $ann = Announcement::findOrFail($data['id']);
            $ann->update($payload);
        } else {
            $ann = Announcement::create($payload);
        }

        return $this->ok(['announcement' => $ann->fresh()]);
    }

    /** DELETE /api/admin/announcements/{id} */
    public function adminDestroy(Request $request, TokenService $tokens, int $id): array
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '管理员未登录');

        Announcement::where('id', $id)->delete();
        return $this->ok(['deleted' => $id]);
    }
}
