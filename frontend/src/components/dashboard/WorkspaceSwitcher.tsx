import React from 'react';
import { Buildings, CircleNotch, Plus } from '@phosphor-icons/react';

import { Button } from '../ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Input } from '../ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { workspacesAPI } from '@/lib/api';
import type { WorkspaceSessionContext } from '@/lib/api/contracts';
import { useToast } from '../ui/use-toast';

interface WorkspaceSwitcherProps {
  workspace: WorkspaceSessionContext | null;
  onWorkspaceChange: (workspaceId: string) => Promise<void>;
}

export const WorkspaceSwitcher: React.FC<WorkspaceSwitcherProps> = ({
  workspace,
  onWorkspaceChange,
}) => {
  const [createOpen, setCreateOpen] = React.useState(false);
  const [name, setName] = React.useState('');
  const [saving, setSaving] = React.useState(false);
  const { error, success } = useToast();

  const currentId = workspace?.selected_workspace_id || '';
  const workspaces = workspace?.available_workspaces || [];

  const handleCreate = async () => {
    const cleanName = name.trim();
    if (!cleanName) {
      error('Workspace name is required');
      return;
    }
    try {
      setSaving(true);
      const created = await workspacesAPI.create(cleanName);
      await onWorkspaceChange(created.id);
      setName('');
      setCreateOpen(false);
      success('Workspace created');
    } catch {
      error('Failed to create workspace');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      <Select
        value={currentId}
        onValueChange={(value) => {
          if (value && value !== currentId) {
            onWorkspaceChange(value);
          }
        }}
      >
        <SelectTrigger
          className="h-8 w-[220px] bg-white border-stone-200"
          aria-label="Select workspace"
        >
          <div className="flex min-w-0 items-center gap-2">
            <Buildings size={16} className="text-muted-foreground shrink-0" />
            <SelectValue placeholder="Select workspace" />
          </div>
        </SelectTrigger>
        <SelectContent>
          {workspaces.map((item) => (
            <SelectItem key={item.id} value={item.id}>
              {item.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button
        variant="soft"
        size="icon"
        className="h-8 w-8"
        onClick={() => setCreateOpen(true)}
        aria-label="Create workspace"
      >
        <Plus size={16} />
      </Button>

      <Dialog open={createOpen} onOpenChange={(open) => {
        if (!saving) setCreateOpen(open);
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Create workspace</DialogTitle>
            <DialogDescription>
              Create a workspace for a separate team or client.
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') handleCreate();
              }}
              placeholder="Workspace name"
              disabled={saving}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button variant="soft" onClick={() => setCreateOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={saving || !name.trim()}>
              {saving ? <CircleNotch size={16} className="mr-2 animate-spin" /> : null}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
