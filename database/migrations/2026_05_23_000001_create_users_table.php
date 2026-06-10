<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('users', function (Blueprint $table): void {
            $table->id();
            $table->string('username', 80)->unique();
            $table->string('name', 80)->nullable();
            $table->string('email', 120)->nullable()->index();
            $table->string('mobile', 40)->nullable()->index();
            $table->string('password');
            $table->string('role', 20)->default('user')->index();
            $table->string('status', 20)->default('active')->index();
            $table->unsignedInteger('free_generations')->default(1);
            $table->unsignedInteger('paid_generations')->default(0);
            $table->timestamp('last_login_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('users');
    }
};
