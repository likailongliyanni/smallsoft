<?php

use Illuminate\Support\Facades\Artisan;

Artisan::command('platform:status', function (): void {
    $this->info('WebAuto platform is installed.');
})->purpose('Show platform installation status');
