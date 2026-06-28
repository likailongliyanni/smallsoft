<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('software_releases', function (Blueprint $table): void {
            $table->id();
            $table->string('software_code', 60)->index();
            $table->string('software_name', 120);
            $table->string('version', 40);
            $table->string('platform', 40)->default('windows-x64');
            $table->string('file_name', 255);
            $table->string('storage_path', 500);
            $table->unsignedBigInteger('file_size');
            $table->char('sha256', 64);
            $table->text('release_notes')->nullable();
            $table->boolean('enabled')->default(true)->index();
            $table->unsignedBigInteger('downloads_count')->default(0);
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamp('published_at')->nullable();
            $table->timestamps();

            $table->index(
                ['software_code', 'platform', 'enabled'],
                'software_releases_current_idx'
            );
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('software_releases');
    }
};
