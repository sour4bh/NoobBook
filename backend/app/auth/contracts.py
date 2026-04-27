from typing import List, Literal, Optional

from app.base.contracts import ContractModel


class UserIdentity(ContractModel):
    id: str
    email: Optional[str] = None
    global_role: Literal["admin", "user"]
    is_global_admin: bool
    role: Literal["admin", "user"]
    is_admin: bool
    is_authenticated: bool


class WorkspaceSummary(ContractModel):
    id: str
    name: str
    role: Literal["owner", "admin", "member"]
    owner_user_id: Optional[str] = None
    is_personal: bool = False


class WorkspaceSessionContext(ContractModel):
    available_workspaces: List[WorkspaceSummary]
    selected_workspace: Optional[WorkspaceSummary] = None
    selected_workspace_id: Optional[str] = None
    workspace_role: Optional[Literal["owner", "admin", "member"]] = None
    can_manage_workspace: bool
    can_create_project: bool


class MeResponse(ContractModel):
    success: Literal[True] = True
    auth_required: bool
    asset_token: Optional[str] = None
    user: UserIdentity
    workspace: WorkspaceSessionContext


class AuthUser(ContractModel):
    id: str
    email: Optional[str] = None
    global_role: Optional[Literal["admin", "user"]] = None


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
    workspace: Optional[WorkspaceSessionContext] = None


class AssetTokenPayload(ContractModel):
    scope: Literal["browser_asset"]
    version: Literal[1]
    user_id: str
