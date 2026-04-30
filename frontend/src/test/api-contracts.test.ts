import axios, { AxiosHeaders } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { chatsAPI } from '../lib/api/chats';
import {
  ContractParseError,
  parseActiveTasksResponse,
  parseChatStreamEvent,
  parseGeneratedAssetAccess,
  parseInviteAcceptResponse,
  parseMeResponse,
  parseProjectInviteResponse,
  parseProjectMemberResponse,
  parseProjectMembersResponse,
  parseProjectCostsResponse,
  parseWorkspaceInviteResponse,
  parseWorkspaceMembersResponse,
  parseWorkspaceSessionResponse,
} from '../lib/api/contracts';
import { AUTH_SESSION_EXPIRED_EVENT, api, fetchWithAuthRefresh } from '../lib/api/client';
import { getAccessToken, getRefreshToken, setSelectedWorkspaceId, setSession } from '../lib/auth/session';

const message = {
  id: 'msg-1',
  role: 'assistant' as const,
  content: 'hello',
  timestamp: '2026-04-27T00:00:00Z',
};

const workspace = {
  available_workspaces: [{
    id: 'workspace-1',
    name: 'Personal Workspace',
    role: 'owner' as const,
    owner_user_id: 'user-1',
    is_personal: true,
  }],
  selected_workspace: {
    id: 'workspace-1',
    name: 'Personal Workspace',
    role: 'owner' as const,
    owner_user_id: 'user-1',
    is_personal: true,
  },
  selected_workspace_id: 'workspace-1',
  workspace_role: 'owner' as const,
  can_manage_workspace: true,
  can_create_project: true,
};

describe('frontend API contract parsers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('accepts valid backend DTO payloads', () => {
    expect(parseMeResponse({
      success: true,
      auth_required: true,
      asset_token: 'asset-token',
      user: {
        id: 'user-1',
        email: 'user@example.com',
        global_role: 'user',
        is_global_admin: false,
        role: 'user',
        is_admin: false,
        is_authenticated: true,
      },
      workspace,
    }).user.id).toBe('user-1');

    expect(parseProjectCostsResponse({
      success: true,
      costs: {
        total_cost: 1.25,
        by_model: {
          'anthropic:claude-sonnet-4-6': {
            provider: 'anthropic',
            model: 'claude-sonnet-4-6',
            input_tokens: 3,
            output_tokens: 4,
            cost: 0.2,
          },
        },
      },
    }).costs.by_model['anthropic:claude-sonnet-4-6'].cost).toBe(0.2);

    expect(parseActiveTasksResponse({
      success: true,
      count: 1,
      tasks: [{
        id: 'task-1',
        type: 'source',
        label: 'Source',
        detail: 'Processing...',
        status: 'processing',
      }],
    }).tasks).toHaveLength(1);

    expect(parseWorkspaceSessionResponse({
      success: true,
      workspace,
    }).workspace.selected_workspace_id).toBe('workspace-1');

    expect(parseWorkspaceMembersResponse({
      success: true,
      count: 1,
      members: [{
        user_id: 'user-1',
        email: 'user@example.com',
        role: 'owner',
        created_at: '2026-04-27T00:00:00Z',
      }],
    }).members[0].role).toBe('owner');

    const invite = {
      id: 'invite-1',
      workspace_id: 'workspace-1',
      email: 'teammate@example.com',
      workspace_role: 'member' as const,
      project_id: 'project-1',
      project_role: 'viewer' as const,
      expires_at: '2026-04-28T00:00:00Z',
      token: 'signed-token',
    };
    expect(parseWorkspaceInviteResponse({
      success: true,
      invite: { ...invite, project_id: null, project_role: null },
    }).invite.token).toBe('signed-token');
    expect(parseInviteAcceptResponse({
      success: true,
      workspace: workspace.selected_workspace,
      workspace_role: 'member',
      project_id: 'project-1',
      project_role: 'viewer',
    }).project_id).toBe('project-1');
    expect(parseProjectMembersResponse({
      success: true,
      count: 1,
      members: [{
        user_id: 'user-2',
        email: 'editor@example.com',
        role: 'editor',
      }],
    }).members[0].role).toBe('editor');
    expect(parseProjectMemberResponse({
      success: true,
      member: {
        user_id: 'user-3',
        email: 'viewer@example.com',
        role: 'viewer',
      },
    }).member.user_id).toBe('user-3');
    expect(parseProjectInviteResponse({
      success: true,
      invite,
    }).invite.project_role).toBe('viewer');
  });

  it('rejects malformed contract payloads', () => {
    expect(() => parseMeResponse({
      success: true,
      auth_required: true,
      user: {
        id: 'user-1',
        global_role: 'user',
        is_global_admin: false,
        role: 'owner',
        is_admin: false,
        is_authenticated: true,
      },
      workspace,
    })).toThrow(ContractParseError);

    expect(() => parseChatStreamEvent('assistant_delta', {})).toThrow(ContractParseError);

    expect(() => parseActiveTasksResponse({
      success: true,
      count: 2,
      tasks: [{
        id: 'task-1',
        type: 'studio',
        label: 'Studio',
        detail: 'Generating...',
        status: 'processing',
      }],
    })).toThrow(ContractParseError);
  });

  it('validates generated asset access payloads', () => {
    expect(parseGeneratedAssetAccess({
      project_id: 'project-1',
      filename: 'chart.png',
      mime_type: 'image/png',
    }).filename).toBe('chart.png');

    expect(() => parseGeneratedAssetAccess({
      project_id: '',
      filename: 'chart.png',
      mime_type: 'image/png',
    })).toThrow(ContractParseError);
  });

  it('attaches the selected workspace id to axios and fetch requests', async () => {
    setSession('access-token', 'refresh-token', 'asset-token');
    setSelectedWorkspaceId('workspace-1');

    const originalAdapter = api.defaults.adapter;
    const adapter = vi.fn(async (config) => ({
      data: { success: true },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }));
    api.defaults.adapter = adapter;

    try {
      await api.get('/contract-test');
      const axiosHeaders = new AxiosHeaders(adapter.mock.calls[0][0].headers);
      expect(axiosHeaders.get('Authorization')).toBe('Bearer access-token');
      expect(axiosHeaders.get('X-NoobBook-Workspace-Id')).toBe('workspace-1');
    } finally {
      api.defaults.adapter = originalAdapter;
    }

    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await fetchWithAuthRefresh('/api/v1/contract-test');
    const fetchHeaders = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(fetchHeaders.get('Authorization')).toBe('Bearer access-token');
    expect(fetchHeaders.get('X-NoobBook-Workspace-Id')).toBe('workspace-1');
  });

  it('refreshes auth before retrying chat SSE transport', async () => {
    setSession('old-access-token', 'refresh-token', 'old-asset-token');

    vi.spyOn(axios, 'post').mockResolvedValue({
      data: {
        success: true,
        session: {
          access_token: 'fresh-access-token',
          refresh_token: 'fresh-refresh-token',
        },
        asset_token: 'fresh-asset-token',
      },
    });

    const streamBody = [
      'event: assistant_delta',
      'data: {"delta":"Hello"}',
      '',
      'event: assistant_done',
      `data: ${JSON.stringify(message)}`,
      '',
      '',
    ].join('\n');

    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ success: false, error: 'Expired token' }),
        { status: 401, headers: { 'Content-Type': 'application/json' } },
      ))
      .mockResolvedValueOnce(new Response(streamBody, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }));

    vi.stubGlobal('fetch', fetchMock);

    const events: string[] = [];
    const result = await chatsAPI.streamMessage(
      'project-1',
      'chat-1',
      'hello',
      {
        onAssistantDelta: (delta) => events.push(delta),
      },
    );

    expect(result.terminalEvent).toBe('assistant_done');
    expect(events).toEqual(['Hello']);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect((fetchMock.mock.calls[0][1]?.headers as Headers).get('Authorization')).toBe(
      'Bearer old-access-token',
    );
    expect((fetchMock.mock.calls[1][1]?.headers as Headers).get('Authorization')).toBe(
      'Bearer fresh-access-token',
    );
  });

  it('expires the local session when auth refresh fails', async () => {
    setSession('old-access-token', 'refresh-token', 'old-asset-token');

    vi.spyOn(axios, 'post').mockRejectedValue(new Error('refresh token already used'));
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ success: false, error: 'Expired token' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    const onExpired = vi.fn();
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, onExpired);
    try {
      const response = await fetchWithAuthRefresh('/api/v1/contract-test');

      expect(response.status).toBe(401);
      expect(onExpired).toHaveBeenCalledTimes(1);
      expect(getAccessToken()).toBeNull();
      expect(getRefreshToken()).toBeNull();
    } finally {
      window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, onExpired);
    }
  });
});
