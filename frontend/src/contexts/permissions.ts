import { createContext, useContext } from 'react';

interface PermissionCategory {
  enabled: boolean;
  items: Record<string, boolean>;
}

export interface UserPermissions {
  document_sources: PermissionCategory;
  data_sources: PermissionCategory;
  studio: PermissionCategory;
  integrations: PermissionCategory;
  chat_features: PermissionCategory;
}

interface PermissionsContextValue {
  permissions: UserPermissions | null;
  loading: boolean;
  hasPermission: (category: string, item?: string) => boolean;
  refreshPermissions: () => Promise<void>;
}

export const PermissionsContext = createContext<PermissionsContextValue>({
  permissions: null,
  loading: true,
  hasPermission: () => true,
  refreshPermissions: async () => {},
});

export const usePermissions = () => useContext(PermissionsContext);
