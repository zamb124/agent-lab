"""REST-зеркало команд `frontend/billing/*`."""

from fastapi import APIRouter

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    BillingPlanChangeResponse,
    BillingSubscription,
    BillingUsage,
    ChangePlanRequest,
)
from apps.frontend.realtime.billing_operations import (
    BillingTopupPayload,
    op_billing_payment_history,
    op_billing_plan_change,
    op_billing_subscription,
    op_billing_topup,
    op_billing_usage,
)
from core.context import require_context
from core.models.payment_models import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    TransactionResponse,
)
from core.pagination import ListResponse
from core.websocket import EmptyPayload

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/subscription", response_model=BillingSubscription)
async def get_subscription(container: ContainerDep) -> BillingSubscription:
    return await op_billing_subscription(EmptyPayload(), user=require_context().user, container=container)


@router.get("/usage", response_model=BillingUsage)
async def get_usage_stats(container: ContainerDep) -> BillingUsage:
    return await op_billing_usage(EmptyPayload(), user=require_context().user, container=container)


@router.patch("/plan", response_model=BillingPlanChangeResponse)
async def change_plan(plan_request: ChangePlanRequest, container: ContainerDep) -> BillingPlanChangeResponse:
    return await op_billing_plan_change(plan_request, user=require_context().user, container=container)


@router.post("/topup", response_model=CreatePaymentResponse)
async def create_topup_payment(payment_request: CreatePaymentRequest, container: ContainerDep) -> CreatePaymentResponse:
    context = require_context()
    return await op_billing_topup(
        BillingTopupPayload(amount=payment_request.amount, public_host=context.host),
        user=context.user,
        container=container,
    )


@router.get("/history", response_model=ListResponse[TransactionResponse])
async def get_payment_history(container: ContainerDep) -> ListResponse[TransactionResponse]:
    return await op_billing_payment_history(EmptyPayload(), user=require_context().user, container=container)
