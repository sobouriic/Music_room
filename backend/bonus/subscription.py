from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import current_user, music_sensitive
from app.core.config import get_settings
from app.core.exceptions import fail
from app.db.session import get_db, lock_user
from app.schemas.auth import Input

router = APIRouter(tags=["subscription"], dependencies=[Depends(music_sensitive)])


class PlanInput(Input):
    plan: Literal["free", "premium"]


class SubscriptionView(BaseModel):
    plan: Literal["free", "premium"]
    billing_mode: Literal["demo", "external"]


def view(user):
    return {
        "plan": user.plan,
        "billing_mode": "external" if get_settings().app_env == "production" else "demo",
    }


@router.get("/subscription", response_model=SubscriptionView)
def get_subscription(user=Depends(current_user)):
    return view(user)


@router.put("/subscription", response_model=SubscriptionView)
def switch_subscription(
    data: PlanInput, user=Depends(current_user), db=Depends(get_db, scope="function")
):
    if get_settings().app_env == "production":
        fail(403, "billing_required", "Plan changes require a verified billing provider")
    user = lock_user(db, user.id)
    user.plan = data.plan
    return view(user)
