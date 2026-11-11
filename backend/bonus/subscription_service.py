from app.core.exceptions import fail
from app.db.session import lock_user


def require_premium(db, user):
    # Same account lock serializes downgrade and offline synchronization.
    if lock_user(db, user.id).plan != "premium":
        fail(403, "premium_required", "Offline mode needs a Premium subscription")
