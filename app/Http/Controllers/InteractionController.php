<?php

namespace App\Http\Controllers;

use App\Services\AutomationFlowValidator;

class InteractionController extends Controller
{
    public function index(AutomationFlowValidator $validator): array
    {
        return $this->ok([
            'step_limits' => [
                'normal' => config('platform.normal_step_limit'),
                'advanced' => config('platform.advanced_step_limit'),
            ],
            'interaction_types' => $validator->interactionTypes(),
        ]);
    }
}
