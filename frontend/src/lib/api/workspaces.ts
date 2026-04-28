import { api } from './client';
import {
  parseInviteAcceptResponse,
  parseWorkspaceCreateResponse,
  parseWorkspaceInviteResponse,
  parseWorkspaceMembersResponse,
  parseWorkspaceSessionResponse,
  type InviteAcceptResponse,
  type MembershipInvite,
  type WorkspaceMember,
  type WorkspaceSessionContext,
  type WorkspaceSummary,
} from './contracts';

export type WorkspaceRole = 'owner' | 'admin' | 'member';

export const workspacesAPI = {
  async list(selectedWorkspaceId?: string | null): Promise<WorkspaceSessionContext> {
    const response = await api.get('/workspaces', {
      params: selectedWorkspaceId ? { workspace_id: selectedWorkspaceId } : undefined,
    });
    return parseWorkspaceSessionResponse(response.data).workspace;
  },

  async create(name: string): Promise<WorkspaceSummary> {
    const response = await api.post('/workspaces', { name });
    return parseWorkspaceCreateResponse(response.data).workspace;
  },

  async listMembers(workspaceId: string): Promise<WorkspaceMember[]> {
    const response = await api.get(`/workspaces/${workspaceId}/members`);
    return parseWorkspaceMembersResponse(response.data).members;
  },

  async createInvite(
    workspaceId: string,
    email: string,
    workspaceRole: WorkspaceRole,
  ): Promise<MembershipInvite> {
    const response = await api.post(`/workspaces/${workspaceId}/invites`, {
      email,
      workspace_role: workspaceRole,
    });
    return parseWorkspaceInviteResponse(response.data).invite;
  },

  async acceptInvite(token: string): Promise<InviteAcceptResponse> {
    const response = await api.post(`/workspace-invites/${encodeURIComponent(token)}/accept`);
    return parseInviteAcceptResponse(response.data);
  },
};

export type {
  InviteAcceptResponse,
  MembershipInvite,
  WorkspaceMember,
  WorkspaceSessionContext,
  WorkspaceSummary,
};
