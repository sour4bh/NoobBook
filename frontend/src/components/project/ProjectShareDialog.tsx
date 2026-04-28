import React, { useEffect, useMemo, useState } from 'react';
import { CircleNotch, Copy, EnvelopeSimple, Plus, Trash } from '@phosphor-icons/react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ToastContainer } from '@/components/ui/toast';
import { useToast } from '@/components/ui/use-toast';
import { projectsAPI, workspacesAPI, type ProjectRole } from '@/lib/api';
import type { MembershipInvite, ProjectMember, WorkspaceMember } from '@/lib/api/contracts';
import { createLogger } from '@/lib/logger';

const log = createLogger('project-share-dialog');

interface ProjectShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  workspaceId?: string | null;
  currentUserId: string;
}

function roleLabel(role: string): string {
  return role.charAt(0).toUpperCase() + role.slice(1);
}

function inviteLink(invite: MembershipInvite): string {
  return `${window.location.origin}/workspace-invites/${encodeURIComponent(invite.token)}`;
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const element = document.createElement('textarea');
  element.value = value;
  element.setAttribute('readonly', 'true');
  element.style.position = 'absolute';
  element.style.left = '-9999px';
  document.body.appendChild(element);
  element.select();
  document.execCommand('copy');
  document.body.removeChild(element);
}

export const ProjectShareDialog: React.FC<ProjectShareDialogProps> = ({
  open,
  onOpenChange,
  projectId,
  workspaceId,
  currentUserId,
}) => {
  const [projectMembers, setProjectMembers] = useState<ProjectMember[]>([]);
  const [workspaceMembers, setWorkspaceMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedRole, setSelectedRole] = useState<ProjectRole>('viewer');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<ProjectRole>('viewer');
  const [createdInvite, setCreatedInvite] = useState<MembershipInvite | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const { toasts, dismissToast, success, error } = useToast();

  const memberIds = useMemo(
    () => new Set(projectMembers.map((member) => member.user_id)),
    [projectMembers],
  );
  const eligibleWorkspaceMembers = useMemo(
    () => workspaceMembers.filter((member) => !memberIds.has(member.user_id)),
    [workspaceMembers, memberIds],
  );
  const createdInviteLink = useMemo(
    () => createdInvite ? inviteLink(createdInvite) : '',
    [createdInvite],
  );

  const load = async () => {
    try {
      setLoading(true);
      const [projectList, workspaceList] = await Promise.all([
        projectsAPI.listMembers(projectId),
        workspaceId ? workspacesAPI.listMembers(workspaceId) : Promise.resolve([]),
      ]);
      setProjectMembers(projectList);
      setWorkspaceMembers(workspaceList);
    } catch (err) {
      log.error({ err }, 'failed to load project sharing state');
      error('Failed to load sharing settings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      load();
    }
  }, [open, projectId, workspaceId]);

  const handleAddMember = async () => {
    if (!selectedUserId) {
      error('Choose a workspace member first');
      return;
    }
    try {
      setBusyKey('add-member');
      const member = await projectsAPI.addMember(projectId, selectedUserId, selectedRole);
      setProjectMembers((prev) => [...prev.filter((item) => item.user_id !== member.user_id), member]);
      setSelectedUserId('');
      setSelectedRole('viewer');
      success('Project member added');
    } catch (err) {
      log.error({ err }, 'failed to add project member');
      error('Failed to add project member');
    } finally {
      setBusyKey(null);
    }
  };

  const handleRoleChange = async (member: ProjectMember, role: ProjectRole) => {
    try {
      setBusyKey(`role-${member.user_id}`);
      const updated = await projectsAPI.updateMemberRole(projectId, member.user_id, role);
      setProjectMembers((prev) => prev.map((item) => item.user_id === updated.user_id ? updated : item));
      success('Project role updated');
    } catch (err) {
      log.error({ err }, 'failed to update project member role');
      error('Failed to update project role');
    } finally {
      setBusyKey(null);
    }
  };

  const handleRemoveMember = async (member: ProjectMember) => {
    try {
      setBusyKey(`remove-${member.user_id}`);
      await projectsAPI.removeMember(projectId, member.user_id);
      setProjectMembers((prev) => prev.filter((item) => item.user_id !== member.user_id));
      success('Project member removed');
    } catch (err) {
      log.error({ err }, 'failed to remove project member');
      error('Failed to remove project member');
    } finally {
      setBusyKey(null);
    }
  };

  const handleCreateInvite = async () => {
    const email = inviteEmail.trim();
    if (!email) {
      error('Email is required');
      return;
    }
    try {
      setBusyKey('project-invite');
      const invite = await projectsAPI.createInvite(projectId, email, inviteRole);
      setCreatedInvite(invite);
      setInviteEmail('');
      success('Project invite link created');
    } catch (err) {
      log.error({ err }, 'failed to create project invite');
      error('Failed to create project invite');
    } finally {
      setBusyKey(null);
    }
  };

  const handleCopyInvite = async () => {
    if (!createdInviteLink) return;
    try {
      await copyText(createdInviteLink);
      success('Project invite link copied');
    } catch (err) {
      log.error({ err }, 'failed to copy project invite');
      error('Failed to copy invite link');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <ToastContainer toasts={toasts} onDismiss={dismissToast} />
        <DialogHeader>
          <DialogTitle>Share project</DialogTitle>
          <DialogDescription>
            Add explicit project members or create a one-time invite link.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Member</TableHead>
                  <TableHead>Project role</TableHead>
                  <TableHead className="w-[80px]">Remove</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                      <CircleNotch size={20} className="mx-auto mb-2 animate-spin" />
                      Loading members...
                    </TableCell>
                  </TableRow>
                ) : projectMembers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                      No project members found.
                    </TableCell>
                  </TableRow>
                ) : projectMembers.map((member) => (
                  <TableRow key={member.user_id}>
                    <TableCell className="font-medium">
                      {member.email || member.user_id}
                      {member.user_id === currentUserId ? (
                        <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      {member.role === 'owner' && member.user_id === currentUserId ? (
                        <Badge>{roleLabel(member.role)}</Badge>
                      ) : (
                        <Select
                          value={member.role}
                          onValueChange={(value) => handleRoleChange(member, value as ProjectRole)}
                          disabled={busyKey === `role-${member.user_id}`}
                        >
                          <SelectTrigger className="h-8 w-[130px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="viewer">Viewer</SelectItem>
                            <SelectItem value="editor">Editor</SelectItem>
                            <SelectItem value="owner">Owner</SelectItem>
                          </SelectContent>
                        </Select>
                      )}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        disabled={member.user_id === currentUserId || busyKey === `remove-${member.user_id}`}
                        onClick={() => handleRemoveMember(member)}
                        aria-label={`Remove ${member.email || member.user_id}`}
                      >
                        {busyKey === `remove-${member.user_id}` ? (
                          <CircleNotch size={16} className="animate-spin" />
                        ) : (
                          <Trash size={16} />
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="rounded-lg border p-4 space-y-4">
            <div>
              <h3 className="text-sm font-medium">Add workspace member</h3>
              <p className="text-sm text-muted-foreground">
                Workspace members still need explicit access to this private project.
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-[1fr_140px_auto]">
              <Select value={selectedUserId} onValueChange={setSelectedUserId}>
                <SelectTrigger aria-label="Workspace member">
                  <SelectValue placeholder={eligibleWorkspaceMembers.length ? 'Choose member' : 'No eligible members'} />
                </SelectTrigger>
                <SelectContent>
                  {eligibleWorkspaceMembers.map((member) => (
                    <SelectItem key={member.user_id} value={member.user_id}>
                      {member.email || member.user_id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={selectedRole} onValueChange={(value) => setSelectedRole(value as ProjectRole)}>
                <SelectTrigger aria-label="Project role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="viewer">Viewer</SelectItem>
                  <SelectItem value="editor">Editor</SelectItem>
                  <SelectItem value="owner">Owner</SelectItem>
                </SelectContent>
              </Select>
              <Button
                onClick={handleAddMember}
                disabled={!selectedUserId || busyKey === 'add-member'}
                className="gap-2"
              >
                {busyKey === 'add-member' ? <CircleNotch size={16} className="animate-spin" /> : <Plus size={16} />}
                Add
              </Button>
            </div>
          </div>

          <div className="rounded-lg border p-4 space-y-4">
            <div>
              <h3 className="text-sm font-medium">Invite by link</h3>
              <p className="text-sm text-muted-foreground">
                The invite adds the user to this workspace as a member and grants the selected project role.
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-[1fr_140px_auto]">
              <div className="space-y-1.5">
                <Label htmlFor="project-invite-email">Email</Label>
                <Input
                  id="project-invite-email"
                  type="email"
                  value={inviteEmail}
                  onChange={(event) => setInviteEmail(event.target.value)}
                  placeholder="teammate@example.com"
                  disabled={busyKey === 'project-invite'}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Role</Label>
                <Select value={inviteRole} onValueChange={(value) => setInviteRole(value as ProjectRole)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="viewer">Viewer</SelectItem>
                    <SelectItem value="editor">Editor</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end">
                <Button
                  onClick={handleCreateInvite}
                  disabled={!inviteEmail.trim() || busyKey === 'project-invite'}
                  className="w-full gap-2"
                >
                  {busyKey === 'project-invite' ? (
                    <CircleNotch size={16} className="animate-spin" />
                  ) : (
                    <EnvelopeSimple size={16} />
                  )}
                  Invite
                </Button>
              </div>
            </div>

            {createdInviteLink ? (
              <div className="flex flex-col gap-2 rounded-md bg-stone-50 p-3 sm:flex-row sm:items-center">
                <Input value={createdInviteLink} readOnly className="font-mono text-xs" />
                <Button variant="soft" onClick={handleCopyInvite} className="gap-2 sm:w-auto">
                  <Copy size={16} />
                  Copy
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
