<?php

namespace App\Http\Controllers;

use App\Models\Order;
use App\Services\TokenService;
use Illuminate\Http\Request;

class OrderController extends Controller
{
    public function mine(Request $request, TokenService $tokens): array
    {
        $user = $tokens->userFromRequest($request);
        abort_if(! $user, 401, '请先登录');

        $orders = Order::where('user_id', $user->id)
            ->latest('id')
            ->limit(50)
            ->get();

        return $this->ok(['orders' => $orders->toArray()]);
    }
}
