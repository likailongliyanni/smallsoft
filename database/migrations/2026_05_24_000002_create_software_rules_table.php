<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('software_rules', function (Blueprint $table): void {
            $table->id();
            $table->string('version', 20)->unique();
            $table->boolean('is_active')->default(false)->index();
            $table->json('rules');
            $table->text('changelog')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('software_rules');
    }
};
