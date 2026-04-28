import React, { useEffect, useMemo, useState } from 'react';
import { Copy, EnvelopeSimple, UsersThree, CircleNotch } from '@phosphor-icons/react';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import { workspacesAPI, type WorkspaceRole } from '@/lib/api';
import type { WorkspaceMember, MembershipInvite } from '@/lib/api/contracts';
import { createLogger } from '@/lib/logger';

const log = createLogger('workspace-members-section');

interface WorkspaceMembersSectionProps {
  currentUserId: string;
  workspaceId?: string | null;
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

function roleLabel(role: string): string {
  return role.charAt(0).toUpperCase() + role.slice(1);
}

export const WorkspaceMembersSection: React.FC<WorkspaceMembersSectionProps> = ({
  currentUserId,
  workspaceId,
}) => {
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<WorkspaceRole>('member');
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [createdInvite, setCreatedInvite] = useState<MembershipInvite | null>(null);
  const { toasts, dismissToast, success, error } = useToast();

  const createdInviteLink = useMemo(
    () => createdInvite ? inviteLink(createdInvite) : '',
    [createdInvite],
  );

  useEffect(() => {
    if (!workspaceId) {
      setMembers([]);
      return;
    }

    const loadMembers = async () => {
      try {
        setLoading(true);
        setMembers(await workspacesAPI.listMembers(workspaceId));
      } catch (err) {
        log.error({ err }, 'failed to load workspace members');
        error('Failed to load workspace members');
      } finally {
        setLoading(false);
      }
    };

    loadMembers();
  }, [workspaceId, error]);

  const handleCreateInvite = async () => {
    if (!workspaceId) {
      error('Select a workspace first');
      return;
    }
    const email = inviteEmail.trim();
    if (!email) {
      error('Email is required');
      return;
    }

    try {
      setCreatingInvite(true);
      const invite = await workspacesAPI.createInvite(workspaceId, email, inviteRole);
      setCreatedInvite(invite);
      setInviteEmail('');
      success('Invite link created');
    } catch (err) {
      log.error({ err }, 'failed to create workspace invite');
      error('Failed to create invite');
    } finally {
      setCreatingInvite(false);
    }
  };

  const handleCopyInvite = async () => {
    if (!createdInviteLink) return;
    try {
      await copyText(createdInviteLink);
      success('Invite link copied');
    } catch (err) {
      log.error({ err }, 'failed to copy workspace invite');
      error('Failed to copy invite link');
    }
  };

  if (!workspaceId) {
    return (
      <div className="rounded-lg border bg-muted/20 p-6 text-sm text-muted-foreground">
        Select a workspace before managing members.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-medium text-stone-900 mb-1">Workspace Members</h2>
          <p className="text-sm text-muted-foreground">
            Manage the people who can join this workspace. Projects remain private until shared.
          </p>
        </div>
        <Badge variant="outline" className="gap-1.5 whitespace-nowrap">
          <UsersThree size={14} />
          {members.length} {members.length === 1 ? 'member' : 'members'}
        </Badge>
      </div>

      <div className="rounded-lg border p-4 space-y-4">
        <div>
          <h3 className="text-sm font-medium text-stone-900">Create invite link</h3>
          <p className="text-sm text-muted-foreground">
            Send this link to the invited email address. Invite links are one-time and expire.
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-[1fr_150px_auto]">
          <div className="space-y-1.5">
            <Label htmlFor="workspace-invite-email">Email</Label>
            <Input
              id="workspace-invite-email"
              type="email"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              placeholder="teammate@example.com"
              disabled={creatingInvite}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Role</Label>
            <Select
              value={inviteRole}
              onValueChange={(value) => setInviteRole(value as WorkspaceRole)}
              disabled={creatingInvite}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="member">Member</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-end">
            <Button
              onClick={handleCreateInvite}
              disabled={creatingInvite || !inviteEmail.trim()}
              className="w-full gap-2"
            >
              {creatingInvite ? <CircleNotch size={16} className="animate-spin" /> : <EnvelopeSimple size={16} />}
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

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Joined</TableHead>
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
            ) : members.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                  No workspace members found.
                </TableCell>
              </TableRow>
            ) : members.map((member) => (
              <TableRow key={member.user_id}>
                <TableCell className="font-medium">
                  {member.email || member.user_id}
                  {member.user_id === currentUserId ? (
                    <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                  ) : null}
                </TableCell>
                <TableCell>
                  <Badge variant={member.role === 'owner' ? 'default' : 'secondary'}>
                    {roleLabel(member.role)}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {member.created_at ? new Date(member.created_at).toLocaleDateString() : '-'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
};
