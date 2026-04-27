import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../components/sources', () => ({
  SourcesPanel: () => <section>Sources shell</section>,
}));

vi.mock('../components/chat', () => ({
  ChatPanel: () => <section>Chat shell</section>,
}));

vi.mock('../components/studio', () => ({
  StudioPanel: () => <section>Studio shell</section>,
}));

vi.mock('../components/project/ProjectHeader', () => ({
  ProjectHeader: () => <header>Project header</header>,
}));

vi.mock('../components/project/ActiveTasksBar', () => ({
  ActiveTasksBar: () => <div>Active tasks shell</div>,
}));

import { ProjectWorkspace } from '../components/project/ProjectWorkspace';

describe('project workspace shell', () => {
  it('renders chat, sources, and studio shells together', () => {
    render(
      <ProjectWorkspace
        project={{ id: 'proj-1', name: 'Demo Project', description: '' }}
        onBack={() => {}}
        onDeleteProject={() => {}}
      />
    );

    expect(screen.getByText('Sources shell')).toBeTruthy();
    expect(screen.getByText('Chat shell')).toBeTruthy();
    expect(screen.getByText('Studio shell')).toBeTruthy();
    expect(screen.getByText('Active tasks shell')).toBeTruthy();
  });
});
