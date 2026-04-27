import axios from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { chatsAPI } from '../lib/api/chats';
import {
  ContractParseError,
  parseActiveTasksResponse,
  parseChatStreamEvent,
  parseGeneratedAssetAccess,
  parseMeResponse,
  parseProjectCostsResponse,
} from '../lib/api/contracts';
import { setSession } from '../lib/auth/session';

const message = {
  id: 'msg-1',
  role: 'assistant' as const,
  content: 'hello',
  timestamp: '2026-04-27T00:00:00Z',
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
        role: 'user',
        is_admin: false,
        is_authenticated: true,
      },
    }).user.id).toBe('user-1');

    expect(parseProjectCostsResponse({
      success: true,
      costs: {
        total_cost: 1.25,
        by_model: {
          opus: { input_tokens: 1, output_tokens: 2, cost: 0.1 },
          sonnet: { input_tokens: 3, output_tokens: 4, cost: 0.2 },
          haiku: { input_tokens: 5, output_tokens: 6, cost: 0.3 },
        },
      },
    }).costs.by_model.sonnet.cost).toBe(0.2);

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
  });

  it('rejects malformed contract payloads', () => {
    expect(() => parseMeResponse({
      success: true,
      auth_required: true,
      user: {
        id: 'user-1',
        role: 'owner',
        is_admin: false,
        is_authenticated: true,
      },
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
});
