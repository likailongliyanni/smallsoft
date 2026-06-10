<?php

namespace App\Http\Controllers;

class HealthController extends Controller
{
    public function show(): array
    {
        return [
            'ok' => true,
            'version' => '0.2.0-laravel',
        ];
    }
}
