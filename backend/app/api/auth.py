from fastapi import APIRouter, HTTPException, Request, Response

from app.schemas import LoginRequest, ok
from app.security import create_session, destroy_session, is_valid_session, verify_pin


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
COOKIE_NAME = "cft_session"


@router.post("/login")
async def login(payload: LoginRequest, response: Response) -> dict:
    if not verify_pin(payload.pin):
        raise HTTPException(status_code=401, detail="invalid PIN")
    token = create_session()
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=30 * 24 * 60 * 60,
    )
    return ok({"authenticated": True})


@router.get("/session")
async def session(request: Request) -> dict:
    return ok({"authenticated": is_valid_session(request.cookies.get(COOKIE_NAME))})


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    destroy_session(request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME)
    return ok({"authenticated": False})
