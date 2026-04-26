/**
 * PermissionsContext
 * Educational Note: Provides per-user permission state to the entire app tree.
 * Fetches the current user's permissions from the backend on mount and exposes
 * a `hasPermission(category, item?)` helper that components can call to gate UI
 * features. Defaults to "allow" while loading or on error so the app stays
 * usable even if the permissions endpoint is unavailable.
 *
 * Security note (NBB-202A): this fail-open behavior is UI-only convenience.
 * The backend does NOT trust permissions asserted by the client; every
 * sensitive action is re-checked server-side by `require_permission` /
 * `user_has_permission` in `backend/app/auth/`, which is fail-closed in
 * auth-required mode. A user cannot unlock a feature by tampering with this
 * context — the backend will still return 403.
 */

import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { API_BASE_URL } from '@/lib/api/client';
import { PermissionsContext, type UserPermissions } from './permissions';

export const PermissionsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [permissions, setPermissions] = useState<UserPermissions | null>(null);
  const [loading, setLoading] = useState(true);

  const loadPermissions = useCallback(async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/settings/users/me/permissions`);
      if (response.data.success) {
        setPermissions(response.data.permissions);
      }
    } catch {
      // Silent fail — default to all-enabled if API fails
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPermissions();
  }, [loadPermissions]);

  const hasPermission = useCallback((category: string, item?: string): boolean => {
    if (!permissions) return true; // Default allow during loading/error

    const cat = permissions[category as keyof UserPermissions];
    if (!cat) return true; // Unknown category = allow

    if (!cat.enabled) return false; // Entire category disabled

    if (!item) return true; // Category-level check passed

    return cat.items[item] !== false; // Default to true for unknown items
  }, [permissions]);

  return (
    <PermissionsContext.Provider value={{ permissions, loading, hasPermission, refreshPermissions: loadPermissions }}>
      {children}
    </PermissionsContext.Provider>
  );
};
