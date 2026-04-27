import { render, screen, waitFor } from '@testing-library/react';
import { AxiosHeaders, type AxiosResponse } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../components/project', () => ({
  ProjectList: ({ onCreateNew }: { onCreateNew: () => void }) => (
    <button type="button" onClick={onCreateNew}>Create New Project</button>
  ),
  ProjectWorkspace: () => <div data-testid="project-workspace" />,
}));

import App from '../App';
import { projectsAPI } from '../lib/api';
import { authAPI } from '../lib/api/auth';

describe('app shell smoke', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('boots into the dashboard when auth is optional', async () => {
    vi.spyOn(authAPI, 'me').mockResolvedValue({
      success: true,
      auth_required: false,
      user: {
        id: 'dev-user',
        email: null,
        global_role: 'admin',
        is_global_admin: true,
        role: 'admin',
        is_admin: true,
        is_authenticated: false,
      },
      workspace: {
        available_workspaces: [{
          id: 'workspace-1',
          name: 'Personal Workspace',
          role: 'owner',
          owner_user_id: 'dev-user',
          is_personal: true,
        }],
        selected_workspace: {
          id: 'workspace-1',
          name: 'Personal Workspace',
          role: 'owner',
          owner_user_id: 'dev-user',
          is_personal: true,
        },
        selected_workspace_id: 'workspace-1',
        workspace_role: 'owner',
        can_manage_workspace: true,
        can_create_project: true,
      },
    });
    const projectsResponse: AxiosResponse<{ projects: [] }> = {
      data: { projects: [] },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: { headers: new AxiosHeaders() },
    };
    vi.spyOn(projectsAPI, 'list').mockResolvedValue(projectsResponse);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('NoobBook')).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getByText('Create New Project')).toBeTruthy();
    });
  });
});
