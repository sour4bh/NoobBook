import { render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PermissionsProvider } from '../contexts/PermissionsContext';
import { usePermissions } from '../contexts/permissions';

const PermissionProbe = () => {
  const { loading, hasPermission } = usePermissions();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="studio">{String(hasPermission('studio', 'video'))}</span>
      <span data-testid="memory">{String(hasPermission('chat_features', 'memory'))}</span>
    </div>
  );
};

describe('PermissionsProvider', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads backend permissions and gates item checks', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({
      data: {
        success: true,
        permissions: {
          document_sources: { enabled: true, items: {} },
          data_sources: { enabled: true, items: {} },
          studio: { enabled: false, items: { video: true } },
          integrations: { enabled: true, items: {} },
          chat_features: { enabled: true, items: { memory: false } },
        },
      },
    });

    render(
      <PermissionsProvider>
        <PermissionProbe />
      </PermissionsProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('studio').textContent).toBe('false');
    expect(screen.getByTestId('memory').textContent).toBe('false');
  });

  it('defaults to allow when permission loading fails', async () => {
    vi.spyOn(axios, 'get').mockRejectedValue(new Error('offline'));

    render(
      <PermissionsProvider>
        <PermissionProbe />
      </PermissionsProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('studio').textContent).toBe('true');
    expect(screen.getByTestId('memory').textContent).toBe('true');
  });
});
