from fastapi import HTTPException


def fail(status: int, code: str, message: str):
    raise HTTPException(
        status,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )
