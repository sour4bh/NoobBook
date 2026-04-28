import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkspaceMembersSection } from '../components/settings/sections/WorkspaceMembersSection';
import { ProjectShareDialog } from '../components/project/ProjectShareDialog';
import { projectsAPI, workspacesAPI } from '@/lib/api';

vi.mock('@/lib/api', () => ({
  workspacesAPI: {
    listMembers: vi.fn(),
    createInvite: vi.fn(),
  },
  projectsAPI: {
    listMembers: vi.fn(),
    addMember: vi.fn(),
    updateMemberRole: vi.fn(),
    removeMember: vi.fn(),
    createInvite: vi.fn(),
  },
}));

const workspaceMembers = [
  {
    user_id: 'user-1',
    email: 'owner@example.com',
    role: 'owner' as const,
    created_at: '2026-04-27T00:00:00Z',
  },
  {
    user_id: 'user-2',
    email: 'teammate@example.com',
    role: 'member' as const,
    created_at: '2026-04-27T00:00:00Z',
  },
];

const projectMembers = [
  {
    user_id: 'user-1',
    email: 'owner@example.com',
    role: 'owner' as const,
    created_at: '2026-04-27T00:00:00Z',
  },
];

describe('workspace membership UI', () => {
  beforeEach(() => {
    vi.mocked(workspacesAPI.listMembers).mockResolvedValue(workspaceMembers);
    vi.mocked(workspacesAPI.createInvite).mockResolvedValue({
      id: 'invite-1',
      workspace_id: 'workspace-1',
      email: 'new@example.com',
      workspace_role: 'member',
      project_id: null,
      project_role: null,
      expires_at: '2026-04-28T00:00:00Z',
      token: 'workspace-token',
    });
    vi.mocked(projectsAPI.listMembers).mockResolvedValue(projectMembers);
    vi.mocked(projectsAPI.addMember).mockResolvedValue({
      user_id: 'user-2',
      email: 'teammate@example.com',
      role: 'editor',
    });
    vi.mocked(projectsAPI.createInvite).mockResolvedValue({
      id: 'invite-2',
      workspace_id: 'workspace-1',
      email: 'viewer@example.com',
      workspace_role: 'member',
      project_id: 'project-1',
      project_role: 'viewer',
      expires_at: '2026-04-28T00:00:00Z',
      token: 'project-token',
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists workspace members and creates a copyable workspace invite', async () => {
    const user = userEvent.setup();
    render(<WorkspaceMembersSection currentUserId="user-1" workspaceId="workspace-1" />);

    expect(await screen.findByText('owner@example.com')).toBeInTheDocument();
    expect(screen.queryByText('Add User')).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Email'), 'new@example.com');
    await user.click(screen.getByRole('button', { name: /invite/i }));

    await waitFor(() => {
      expect(workspacesAPI.createInvite).toHaveBeenCalledWith(
        'workspace-1',
        'new@example.com',
        'member',
      );
    });
    expect(screen.getByDisplayValue(/workspace-token/)).toBeInTheDocument();
  });

  it('creates project invite links and adds existing workspace members', async () => {
    const user = userEvent.setup();
    render(
      <ProjectShareDialog
        open
        onOpenChange={() => {}}
        projectId="project-1"
        workspaceId="workspace-1"
        currentUserId="user-1"
      />,
    );

    expect(await screen.findByText('owner@example.com')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Workspace member'));
    await user.click(await screen.findByText('teammate@example.com'));
    await user.click(screen.getByLabelText('Project role'));
    await user.click(await screen.findByText('Editor'));
    await user.click(screen.getByRole('button', { name: /^add$/i }));

    await waitFor(() => {
      expect(projectsAPI.addMember).toHaveBeenCalledWith('project-1', 'user-2', 'editor');
    });

    await user.type(screen.getByLabelText('Email'), 'viewer@example.com');
    await user.click(screen.getByRole('button', { name: /^invite$/i }));

    await waitFor(() => {
      expect(projectsAPI.createInvite).toHaveBeenCalledWith('project-1', 'viewer@example.com', 'viewer');
    });
    expect(screen.getByDisplayValue(/project-token/)).toBeInTheDocument();
  });
});
