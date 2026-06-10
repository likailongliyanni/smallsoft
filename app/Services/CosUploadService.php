<?php

namespace App\Services;

use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;
use RuntimeException;

class CosUploadService
{
    public function uploadAutomationImage(UploadedFile $file, int $userId, string $flowName = '', ?int $stepIndex = null): array
    {
        $secretId = (string) config('cos.secret_id');
        $secretKey = (string) config('cos.secret_key');
        $bucket = (string) config('cos.bucket');
        $region = (string) config('cos.region');

        if ($secretId === '' || $secretKey === '' || $bucket === '' || $region === '') {
            throw new RuntimeException('COS 未配置，请检查 COS_SECRET_ID / COS_SECRET_KEY / COS_BUCKET / COS_REGION');
        }

        $ext = strtolower($file->getClientOriginalExtension() ?: 'jpg');
        if (! in_array($ext, ['jpg', 'jpeg', 'png', 'webp'], true)) {
            $ext = 'jpg';
        }

        $prefix = trim((string) config('cos.prefix'), '/');
        $safeFlow = Str::slug(Str::limit($flowName !== '' ? $flowName : 'flow', 48, ''), '_');
        if ($safeFlow === '') {
            $safeFlow = 'flow';
        }

        $key = implode('/', array_filter([
            $prefix,
            now()->format('Ymd'),
            'user_'.$userId,
            $safeFlow,
            ($stepIndex ? sprintf('step_%03d_', $stepIndex) : '').Str::uuid().'.'.$ext,
        ]));

        $host = "{$bucket}.cos.{$region}.myqcloud.com";
        $path = '/'.$this->encodePath($key);
        $url = "https://{$host}{$path}";
        $body = file_get_contents($file->getRealPath());
        if ($body === false) {
            throw new RuntimeException('读取上传图片失败');
        }

        $mime = $file->getMimeType() ?: 'image/jpeg';
        $auth = $this->authorization('put', $path, $host, $secretId, $secretKey);

        $response = Http::withHeaders([
            'Authorization' => $auth,
            'Host' => $host,
            'Content-Type' => $mime,
        ])->withBody($body, $mime)->put($url);

        if (! $response->successful()) {
            throw new RuntimeException('COS 上传失败：HTTP '.$response->status().' '.$response->body());
        }

        $publicUrl = rtrim((string) config('cos.cdn_url'), '/');
        if ($publicUrl !== '') {
            $publicUrl .= '/'.$this->encodePath($key);
        } else {
            $publicUrl = $url;
        }

        return [
            'key' => $key,
            'url' => $publicUrl,
            'size' => strlen($body),
            'mime' => $mime,
        ];
    }

    private function authorization(string $method, string $path, string $host, string $secretId, string $secretKey): string
    {
        $start = time() - 60;
        $end = $start + 3600;
        $keyTime = $start.';'.$end;
        $signKey = hash_hmac('sha1', $keyTime, $secretKey);

        $httpMethod = strtolower($method);
        $httpUri = $path;
        $httpParameters = '';
        $httpHeaders = 'host='.rawurlencode(strtolower($host));
        $signedHeaders = 'host';
        $signedParameters = '';

        $httpString = $httpMethod."\n".$httpUri."\n".$httpParameters."\n".$httpHeaders."\n";
        $stringToSign = "sha1\n".$keyTime."\n".sha1($httpString)."\n";
        $signature = hash_hmac('sha1', $stringToSign, $signKey);

        return 'q-sign-algorithm=sha1'
            .'&q-ak='.$secretId
            .'&q-sign-time='.$keyTime
            .'&q-key-time='.$keyTime
            .'&q-header-list='.$signedHeaders
            .'&q-url-param-list='.$signedParameters
            .'&q-signature='.$signature;
    }

    private function encodePath(string $key): string
    {
        return implode('/', array_map('rawurlencode', explode('/', $key)));
    }
}
