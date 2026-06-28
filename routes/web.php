<?php

use App\Http\Controllers\SoftwareReleaseController;
use Illuminate\Support\Facades\Route;

Route::view('/', 'pages.index')->name('home');
Route::view('/snap-saver', 'pages.snap-saver')->name('snap-saver');
Route::view('/admin', 'pages.admin')->name('admin');
Route::get('/download', [SoftwareReleaseController::class, 'page'])->name('download');
Route::get('/downloads/software/{release}', [SoftwareReleaseController::class, 'download'])
    ->whereNumber('release')
    ->name('software-releases.download');
Route::view('/tutorial', 'pages.tutorial')->name('tutorial');
Route::view('/control-lab', 'pages.control-lab')->name('control-lab');
Route::view('/excel-automation', 'pages.excel-automation')->name('excel-automation');
Route::view('/testpages.PHP', 'pages.control-lab')->name('testpages');
Route::redirect('/testpages.php', '/testpages.PHP');

Route::redirect('/login', '/');
Route::redirect('/register', '/');
Route::redirect('/account', '/');
Route::redirect('/console', '/');
Route::redirect('/training', '/');
