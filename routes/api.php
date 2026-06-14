<?php

use App\Http\Controllers\AdminController;
use App\Http\Controllers\AiGenerationController;
use App\Http\Controllers\AiImageController;
use App\Http\Controllers\AiPatternController;
use App\Http\Controllers\AnnouncementController;
use App\Http\Controllers\AuthController;
use App\Http\Controllers\DesktopDeviceController;
use App\Http\Controllers\DesktopWatermarkController;
use App\Http\Controllers\FeedbackController;
use App\Http\Controllers\HealthController;
use App\Http\Controllers\InteractionController;
use App\Http\Controllers\KbVersionController;
use App\Http\Controllers\OrderController;
use App\Http\Controllers\PatternsPublicController;
use App\Http\Controllers\RulesController;
use App\Http\Controllers\SpreadsheetImageController;
use App\Http\Controllers\TableMergeController;
use App\Http\Controllers\TableTidyController;
use App\Http\Controllers\TrainingController;
use App\Http\Controllers\UserProfileController;
use Illuminate\Support\Facades\Route;

Route::get('/health', [HealthController::class, 'show']);
Route::get('/interaction-types', [InteractionController::class, 'index']);

Route::post('/auth/register', [AuthController::class, 'register']);
Route::post('/auth/login', [AuthController::class, 'login']);
Route::get('/me', [AuthController::class, 'me']);
Route::get('/usage', [AuthController::class, 'usage']);

Route::post('/training/submissions', [TrainingController::class, 'store']);
Route::post('/ai/images/upload', [AiImageController::class, 'upload']);
Route::post('/ai/generate', [AiGenerationController::class, 'generate']);
Route::get('/ai/models', [AiGenerationController::class, 'listModels']);
Route::post('/desktop/device/register', [DesktopDeviceController::class, 'register']);
Route::get('/desktop/device/status', [DesktopDeviceController::class, 'status']);
Route::post('/desktop/watermark/detect', [DesktopWatermarkController::class, 'detect']);
Route::post('/desktop/watermark/remove', [DesktopWatermarkController::class, 'remove']);
Route::post('/excel-automation/image-extract/plan', [SpreadsheetImageController::class, 'plan']);
Route::post('/excel-automation/table-merge/plan', [TableMergeController::class, 'plan']);
Route::post('/excel-automation/table-tidy/plan', [TableTidyController::class, 'plan']);
Route::post('/feedback', [FeedbackController::class, 'store']);
Route::get('/orders/mine', [OrderController::class, 'mine']);

Route::get('/rules', [RulesController::class, 'show']);
Route::get('/kb-version', [KbVersionController::class, 'show']);
Route::get('/patterns/manifest', [PatternsPublicController::class, 'manifest']);
Route::get('/patterns/all', [PatternsPublicController::class, 'all']);
Route::get('/patterns/{code}', [PatternsPublicController::class, 'show']);
Route::get('/announcements', [AnnouncementController::class, 'index']);

Route::get('/me/profile', [UserProfileController::class, 'show']);
Route::post('/me/nickname', [UserProfileController::class, 'updateNickname']);

Route::post('/admin/login', [AdminController::class, 'login']);
Route::post('/admin/logout', [AdminController::class, 'logout']);
Route::get('/admin/me', [AdminController::class, 'me']);
Route::get('/admin/stats', [AdminController::class, 'stats']);
Route::get('/admin/users', [AdminController::class, 'users']);
Route::post('/admin/users/update', [AdminController::class, 'updateUser']);
Route::post('/admin/quota/add', [AdminController::class, 'addQuota']);
Route::get('/admin/model', [AdminController::class, 'getModel']);
Route::post('/admin/model', [AdminController::class, 'saveModel']);
Route::post('/admin/model/test', [AdminController::class, 'testModel']);
Route::post('/admin/model/test-vision', [AdminController::class, 'testVisionModel']);
Route::post('/admin/aliyun/test', [AdminController::class, 'testAliyun']);
Route::get('/admin/jobs', [AdminController::class, 'jobs']);
Route::get('/admin/orders', [AdminController::class, 'orders']);
Route::post('/admin/orders', [AdminController::class, 'createOrder']);
Route::get('/admin/feedback', [AdminController::class, 'feedback']);
Route::get('/admin/feedback/{id}', [AdminController::class, 'feedbackDetail'])->whereNumber('id');
Route::post('/admin/feedback/{id}', [AdminController::class, 'updateFeedback'])->whereNumber('id');

Route::get('/admin/rules', [RulesController::class, 'index']);
Route::post('/admin/rules', [RulesController::class, 'store']);

Route::get('/admin/ai-patterns', [AiPatternController::class, 'index']);
Route::post('/admin/ai-patterns', [AiPatternController::class, 'store']);
Route::delete('/admin/ai-patterns/{id}', [AiPatternController::class, 'destroy'])->whereNumber('id');
Route::get('/admin/ai-patterns/preview', [AiPatternController::class, 'preview']);
Route::get('/admin/ai-patterns/diagnose', [AiPatternController::class, 'diagnose']);

Route::get('/admin/announcements', [AnnouncementController::class, 'adminList']);
Route::post('/admin/announcements', [AnnouncementController::class, 'adminStore']);
Route::delete('/admin/announcements/{id}', [AnnouncementController::class, 'adminDestroy'])->whereNumber('id');
