from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Profile, User


def by_email(db: Session, email: str):
    return db.scalar(select(User).where(User.email == email))


def create(db: Session, email: str, password_hash: str | None, verified=False):
    user = User(email=email, password_hash=password_hash, verified=verified)
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    db.flush()
    return user
