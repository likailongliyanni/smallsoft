<?php

namespace App\Http\Controllers;

use App\Models\SoftwareRelease;
use App\Services\TokenService;
use Illuminate\Http\Request;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use Symfony\Component\HttpFoundation\BinaryFileResponse;

class SoftwareReleaseController extends Controller
{
    private const ALLOWED_EXTENSIONS = ['exe', 'msi', 'zip', 'rar', '7z'];

    public function page()
    {
        $releases = SoftwareRelease::active()
            ->orderByDesc('published_at')
            ->orderByDesc('id')
            ->get()
            ->unique(fn (SoftwareRelease $release) => $release->software_code.'|'.$release->platform)
            ->values();

        return view('pages.download', ['softwareReleases' => $releases]);
    }

    public function index(): array
    {
        $items = SoftwareRelease::active()
            ->orderBy('software_name')
            ->orderByDesc('published_at')
            ->get()
            ->unique(fn (SoftwareRelease $release) => $release->software_code.'|'.$release->platform)
            ->values()
            ->map(fn (SoftwareRelease $release) => $this->payload($release));

        return $this->ok(['items' => $items]);
    }

    public function adminList(Request $request, TokenService $tokens): array
    {
        $this->requireAdmin($request, $tokens);

        $items = SoftwareRelease::query()
            ->orderBy('software_name')
            ->orderByDesc('published_at')
            ->orderByDesc('id')
            ->limit(500)
            ->get()
            ->map(fn (SoftwareRelease $release) => $this->payload($release));

        return $this->ok(['items' => $items]);
    }

    public function adminStore(Request $request, TokenService $tokens): array
    {
        $admin = $this->requireAdmin($request, $tokens);

        $data = $request->validate([
            'software_code' => ['required', 'string', 'max:60', 'regex:/^[a-z0-9][a-z0-9_-]*$/'],
            'software_name' => ['required', 'string', 'max:120'],
            'version' => ['required', 'string', 'max:40'],
            'platform' => ['required', 'string', 'in:windows-x64,windows-arm64,macos,linux'],
            'release_notes' => ['nullable', 'string', 'max:5000'],
            'enabled' => ['nullable', 'boolean'],
            'package' => [
                'required',
                'file',
                'max:614400',
                function (string $attribute, mixed $value, \Closure $fail): void {
                    if (! $value instanceof UploadedFile) {
                        $fail('请选择需要上传的安装包。');
                        return;
                    }

                    $extension = strtolower($value->getClientOriginalExtension());
                    if (! in_array($extension, self::ALLOWED_EXTENSIONS, true)) {
                        $fail('仅支持 exe、msi、zip、rar、7z 安装包。');
                    }
                },
            ],
        ]);

        /** @var UploadedFile $file */
        $file = $data['package'];
        $softwareCode = trim($data['software_code']);
        $extension = strtolower($file->getClientOriginalExtension());
        $storedName = Str::uuid().'.'.$extension;
        $storagePath = $file->storeAs('software-releases/'.$softwareCode, $storedName, 'local');

        abort_if(! $storagePath, 500, '安装包保存失败，请检查 storage 目录权限。');

        $absolutePath = Storage::disk('local')->path($storagePath);
        $enabled = $request->boolean('enabled', true);

        try {
            $release = DB::transaction(function () use (
                $admin,
                $data,
                $enabled,
                $file,
                $storagePath,
                $absolutePath,
                $softwareCode
            ): SoftwareRelease {
                if ($enabled) {
                    SoftwareRelease::query()
                        ->where('software_code', $softwareCode)
                        ->where('platform', $data['platform'])
                        ->where('enabled', true)
                        ->update(['enabled' => false]);
                }

                return SoftwareRelease::create([
                    'software_code' => $softwareCode,
                    'software_name' => trim($data['software_name']),
                    'version' => trim($data['version']),
                    'platform' => $data['platform'],
                    'file_name' => basename($file->getClientOriginalName()),
                    'storage_path' => $storagePath,
                    'file_size' => filesize($absolutePath),
                    'sha256' => hash_file('sha256', $absolutePath),
                    'release_notes' => trim((string) ($data['release_notes'] ?? '')) ?: null,
                    'enabled' => $enabled,
                    'created_by' => $admin->id,
                    'published_at' => $enabled ? now() : null,
                ]);
            });
        } catch (\Throwable $error) {
            Storage::disk('local')->delete($storagePath);
            throw $error;
        }

        return $this->ok(['release' => $this->payload($release)]);
    }

    public function adminActivate(
        Request $request,
        TokenService $tokens,
        SoftwareRelease $release
    ): array {
        $this->requireAdmin($request, $tokens);

        DB::transaction(function () use ($release): void {
            SoftwareRelease::query()
                ->where('software_code', $release->software_code)
                ->where('platform', $release->platform)
                ->where('id', '!=', $release->id)
                ->where('enabled', true)
                ->update(['enabled' => false]);

            $release->update([
                'enabled' => true,
                'published_at' => now(),
            ]);
        });

        return $this->ok(['release' => $this->payload($release->fresh())]);
    }

    public function adminDisable(
        Request $request,
        TokenService $tokens,
        SoftwareRelease $release
    ): array {
        $this->requireAdmin($request, $tokens);
        $release->update(['enabled' => false]);

        return $this->ok(['release' => $this->payload($release->fresh())]);
    }

    public function adminDestroy(
        Request $request,
        TokenService $tokens,
        SoftwareRelease $release
    ): array {
        $this->requireAdmin($request, $tokens);

        $path = $release->storage_path;
        $id = $release->id;
        $release->delete();
        Storage::disk('local')->delete($path);

        return $this->ok(['deleted' => $id]);
    }

    public function download(SoftwareRelease $release): BinaryFileResponse
    {
        abort_unless($release->enabled, 404);

        $disk = Storage::disk('local');
        abort_unless($disk->exists($release->storage_path), 404, '安装包文件不存在');

        $release->increment('downloads_count');

        return response()->download(
            $disk->path($release->storage_path),
            $release->file_name,
            ['Cache-Control' => 'private, no-store']
        );
    }

    private function payload(SoftwareRelease $release): array
    {
        return [
            'id' => $release->id,
            'software_code' => $release->software_code,
            'software_name' => $release->software_name,
            'version' => $release->version,
            'platform' => $release->platform,
            'file_name' => $release->file_name,
            'file_size' => $release->file_size,
            'file_size_text' => $this->formatBytes($release->file_size),
            'sha256' => $release->sha256,
            'release_notes' => $release->release_notes,
            'enabled' => $release->enabled,
            'downloads_count' => $release->downloads_count,
            'published_at' => $release->published_at,
            'created_at' => $release->created_at,
            'download_url' => $release->enabled
                ? route('software-releases.download', ['release' => $release->id])
                : null,
        ];
    }

    private function formatBytes(int $bytes): string
    {
        if ($bytes >= 1024 ** 3) {
            return number_format($bytes / (1024 ** 3), 2).' GB';
        }
        if ($bytes >= 1024 ** 2) {
            return number_format($bytes / (1024 ** 2), 2).' MB';
        }
        if ($bytes >= 1024) {
            return number_format($bytes / 1024, 2).' KB';
        }

        return $bytes.' B';
    }

    private function requireAdmin(Request $request, TokenService $tokens)
    {
        $admin = $tokens->adminFromRequest($request);
        abort_if(! $admin, 401, '管理员未登录');

        return $admin;
    }
}
