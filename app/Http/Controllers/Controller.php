<?php

namespace App\Http\Controllers;

abstract class Controller
{
    protected function ok(array $data = []): array
    {
        return ['ok' => true] + $data;
    }
}
