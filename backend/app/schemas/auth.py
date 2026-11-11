import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Password = Annotated[str, Field(min_length=12, max_length=128)]
Token = Annotated[str, Field(min_length=20, max_length=2048)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailInput(Input):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize(cls, value):
        return value.casefold()


class Register(EmailInput):
    password: Password

    @field_validator("password")
    @classmethod
    def password_policy(cls, value):
        if len(set(value)) < 5 or value.casefold() in {"password123456", "123456789012"}:
            raise ValueError("Choose a less predictable password")
        return value


class Login(EmailInput):
    password: Annotated[str, Field(min_length=1, max_length=128)]


class TokenInput(Input):
    token: Token


class VerifyEmail(TokenInput):
    # Only the email owner can establish the verified account's credentials.
    password: Password
    _policy = field_validator("password")(Register.password_policy.__func__)


class RefreshInput(Input):
    refresh_token: Token


class ResetPassword(Input):
    token: Token
    password: Password
    _policy = field_validator("password")(Register.password_policy.__func__)


class ChangePassword(Input):
    current_password: Annotated[str | None, Field(max_length=128)] = None
    password: Password
    _policy = field_validator("password")(Register.password_policy.__func__)


class Message(BaseModel):
    message: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class GoogleStart(Input):
    code_challenge: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$")]
    intent: Literal["login", "link"] = "login"
    platform: Literal["web", "native"] = "web"


class GoogleExchange(Input):
    state: Token
    code: Annotated[str, Field(min_length=1, max_length=4096)]
    code_verifier: Annotated[str, Field(min_length=43, max_length=128)]

    @field_validator("code_verifier")
    @classmethod
    def verifier_chars(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9._~-]+", value):
            raise ValueError("Invalid PKCE verifier")
        return value


class GoogleStartResult(BaseModel):
    authorization_url: str
    state: str
    expires_in: int = 600
