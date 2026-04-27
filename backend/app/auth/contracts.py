from typing import Literal, Optional

from app.base.contracts import ContractModel


class UserIdentity(ContractModel):
    id: str
    email: Optional[str] = None
    role: Literal["admin", "user"]
    is_admin: bool
    is_authenticated: bool


class MeResponse(ContractModel):
    success: Literal[True] = True
    auth_required: bool
    asset_token: Optional[str] = None
    user: UserIdentity


class AuthUser(ContractModel):
    id: str
    email: Optional[str] = None


class AuthSession(ContractModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: Optional[str] = None


class AuthSessionResponse(ContractModel):
    success: Literal[True] = True
    user: Optional[AuthUser] = None
    session: Optional[AuthSession] = None
    asset_token: Optional[str] = None


class AssetTokenPayload(ContractModel):
    scope: Literal["browser_asset"]
    version: Literal[1]
    user_id: str
