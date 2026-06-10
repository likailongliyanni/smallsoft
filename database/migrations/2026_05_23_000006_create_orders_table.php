<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('orders', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('order_no', 64)->unique();
            $table->string('plan_name', 80);
            $table->unsignedInteger('quota')->default(0);
            $table->unsignedInteger('amount_cents')->default(0);
            $table->string('status', 30)->default('pending')->index();
            $table->string('payment_channel', 40)->nullable();
            $table->string('payment_trade_no', 120)->nullable();
            $table->timestamp('paid_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('orders');
    }
};
