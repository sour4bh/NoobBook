/**
 * AppSettings Component
 * Admin Settings dialog with Notion-style sidebar navigation.
 * Features: Profile, Team Management, API Keys, Integrations, System Settings.
 */

import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { SettingsSidebar, type SettingsSection } from '../settings/SettingsSidebar';
import {
  ProfileSection,
  TeamSection,
  ApiKeysSection,
  IntegrationsSection,
  SystemSection,
  DesignSection,
  ModelsSection,
} from '../settings/sections';

interface AppSettingsProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userEmail?: string | null;
  globalRole?: string;
  workspaceRole?: string | null;
  canManageWorkspace?: boolean;
  userId?: string;
  onSignOut?: () => Promise<void>;
}

export const AppSettings: React.FC<AppSettingsProps> = ({
  open,
  onOpenChange,
  userEmail = null,
  globalRole = 'user',
  workspaceRole = null,
  canManageWorkspace = false,
  userId = '',
  onSignOut,
}) => {
  const [activeSection, setActiveSection] = useState<SettingsSection>('profile');

  // Handle section change with admin check
  const handleSectionChange = (section: SettingsSection) => {
    const adminOnlySections: SettingsSection[] = ['team', 'api-keys', 'models', 'design', 'system'];
    if (!canManageWorkspace && adminOnlySections.includes(section)) {
      return;
    }
    setActiveSection(section);
  };

  // Reset to profile when closing (so next open starts fresh)
  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      setActiveSection('profile');
    }
    onOpenChange(isOpen);
  };

  const renderSection = () => {
    switch (activeSection) {
      case 'profile':
        return (
          <ProfileSection
            userEmail={userEmail}
            globalRole={globalRole}
            workspaceRole={workspaceRole}
            onSignOut={onSignOut}
          />
        );
      case 'team':
        return canManageWorkspace ? <TeamSection currentUserId={userId} /> : null;
      case 'api-keys':
        return canManageWorkspace ? <ApiKeysSection /> : null;
      case 'models':
        return canManageWorkspace ? <ModelsSection /> : null;
      case 'integrations':
        return <IntegrationsSection isAdmin={canManageWorkspace} />;
      case 'design':
        return canManageWorkspace ? <DesignSection /> : null;
      case 'system':
        return canManageWorkspace ? <SystemSection /> : null;
      default:
        return null;
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-6xl h-[85vh] p-0 gap-0 overflow-hidden bg-card flex flex-col">
        {/* Header */}
        <DialogHeader className="flex-shrink-0 px-6 py-3 border-b">
          <DialogTitle>Settings</DialogTitle>
        </DialogHeader>

        {/* Main content with sidebar */}
        <div className="flex flex-1 min-h-0">
          {/* Sidebar */}
          <SettingsSidebar
            activeSection={activeSection}
            onSectionChange={handleSectionChange}
            canManageWorkspace={canManageWorkspace}
          />

          {/* Content area */}
          <div className="flex-1 overflow-y-auto p-6 bg-white">
            <div className="h-full">{renderSection()}</div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};
