<?php

return [
    'secret_id' => env('COS_SECRET_ID', ''),
    'secret_key' => env('COS_SECRET_KEY', ''),
    'bucket' => env('COS_BUCKET', ''),
    'region' => env('COS_REGION', ''),
    'prefix' => trim(env('COS_UPLOAD_PREFIX', 'automation-images'), '/'),
    'cdn_url' => rtrim(env('COS_CDN_URL', ''), '/'),
    'public_read' => env('COS_PUBLIC_READ', true),
];
