from fastapi import APIRouter

from bonus import nearby, offline, subscription
from mandatory.api import activity, auth, friends, music, realtime, users

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(subscription.router)
router.include_router(offline.router)
router.include_router(nearby.router)

router.include_router(friends.router)

router.include_router(music.device_router)
router.include_router(music.router)

router.include_router(realtime.router)

router.include_router(activity.router)
