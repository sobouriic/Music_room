import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import (
    authenticate,
    bearer,
    current_auth,
    current_user,
    sensitive,
)
from app.core.config import get_settings
from app.db.session import get_db, lock_user
from app.schemas.auth import (
    ChangePassword,
    EmailInput,
    GoogleExchange,
    GoogleStart,
    GoogleStartResult,
    Login,
    Message,
    RefreshInput,
    Register,
    ResetPassword,
    TokenPair,
    VerifyEmail,
)
from mandatory.services import auth_service as service
from mandatory.services import oauth_service
from mandatory.services.rate_limit import hit

router = APIRouter(prefix="/auth", tags=["authentication"], dependencies=[Depends(sensitive)])


@router.post("/register", response_model=Message, status_code=202)
def register(data: Register, db=Depends(get_db, scope="function")):
    hit("email", data.email)
    return service.register(db, data)


@router.post("/verify-email", response_model=Message)
def verify(data: VerifyEmail, db=Depends(get_db, scope="function")):
    return service.verify_email(db, data.token, data.password)


@router.post("/resend-verification", response_model=Message, status_code=202)
def resend(data: EmailInput, db=Depends(get_db, scope="function")):
    hit("email", data.email)
    return service.request_email(db, data.email, "verify")


@router.post("/login", response_model=TokenPair)
def login(data: Login, db=Depends(get_db, scope="function")):
    hit("email", data.email)
    return service.login(db, data)


@router.post("/refresh", response_model=TokenPair)
def refresh(data: RefreshInput, db=Depends(get_db, scope="function")):
    return service.refresh(db, data.refresh_token)


@router.post("/logout", response_model=Message)
def logout(data: RefreshInput, auth=Depends(current_auth), db=Depends(get_db, scope="function")):
    return service.logout(db, auth[0], auth[1], data.refresh_token)


@router.post("/logout-all", response_model=Message)
def logout_all(user=Depends(current_user), db=Depends(get_db, scope="function")):
    user = lock_user(db, user.id)
    service.invalidate_all(db, user)
    return {"message": "All sessions revoked"}


@router.post("/forgot-password", response_model=Message, status_code=202)
def forgot(data: EmailInput, db=Depends(get_db, scope="function")):
    hit("email", data.email)
    return service.request_email(db, data.email, "reset")


@router.post("/reset-password", response_model=Message)
def reset(data: ResetPassword, db=Depends(get_db, scope="function")):
    return service.reset_password(db, data)


@router.post("/change-password", response_model=Message)
def change(data: ChangePassword, user=Depends(current_user), db=Depends(get_db, scope="function")):
    return service.change_password(db, user, data)


@router.post("/google/start", response_model=GoogleStartResult)
def google_start(
    data: GoogleStart,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db=Depends(get_db, scope="function"),
):
    user = authenticate(credentials, db)[0] if credentials else None
    return oauth_service.start(db, data, user)


@router.get("/google/callback", response_class=HTMLResponse)
def google_callback(request: Request):
    # Native auth sessions intercept an HTTP redirect to the registered scheme.
    # Do not depend on inline JavaScript executing in the provider browser.
    params = request.query_params
    state = params.get("state", "")
    if state.startswith("native.") and (params.get("code") or params.get("error")):
        result = {key: params[key] for key in ("state", "code", "error") if key in params}
        return RedirectResponse(
            "musicroom://oauth?" + urlencode(result),
            status_code=302,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )
    cfg = get_settings()
    # A fixed configured destination prevents open redirects. The fragment keeps
    # the provider code out of frontend HTTP requests and access logs.
    target = json.dumps(cfg.google_web_return_url).replace("<", "\\u003c")
    return HTMLResponse(
        """<!doctype html><html><head><meta name="referrer" content="no-referrer">
<title>Music Room</title></head><body><p>Returning to Music Room…</p>
<a id="return">Return to the app</a><script>
const params = new URLSearchParams(location.search);
history.replaceState(null, '', location.pathname);
const nativeUrl = 'musicroom://oauth?' + params.toString();
document.getElementById('return').href = nativeUrl;
if (params.has('state') && (params.has('code') || params.has('error'))) {
  const destination = params.get('state').startsWith('native.')
    ? nativeUrl
    : TARGET + '#google-callback=' + encodeURIComponent(params.toString());
  document.getElementById('return').href = destination;
  location.replace(destination);
} else {
  document.querySelector('p').textContent =
    'This sign-in attempt has ended. Start Google sign-in again from Music Room.';
}
</script></body></html>""".replace("TARGET", target),
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; script-src 'unsafe-inline'; "
                "base-uri 'none'; frame-ancestors 'none'"
            ),
        },
    )


@router.post("/google/exchange", response_model=TokenPair)
def google_exchange(data: GoogleExchange, db=Depends(get_db, scope="function")):
    return oauth_service.exchange(db, data, "login")


@router.post("/google/link", response_model=Message)
def google_link(
    data: GoogleExchange, user=Depends(current_user), db=Depends(get_db, scope="function")
):
    return oauth_service.exchange(db, data, "link", user)


@router.delete("/google/link", response_model=Message)
def google_unlink(user=Depends(current_user), db=Depends(get_db, scope="function")):
    return service.unlink_google(db, user)
