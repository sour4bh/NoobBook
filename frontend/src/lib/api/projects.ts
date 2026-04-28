/**
 * Projects API Service
 * Educational Note: These methods abstract the API calls for project management,
 * making them easier to use throughout the application and maintaining consistency.
 */

import { api } from './client';
import {
  parseActiveTasksResponse,
  parseProjectInviteResponse,
  parseProjectMemberResponse,
  parseProjectMembersResponse,
  parseProjectCostsResponse,
  type ActiveTasksResponse,
  type CostTracking,
  type MembershipInvite,
  type ProjectMember,
} from './contracts';
import type { AxiosResponse } from 'axios';

/**
 * Memory Types
 * Educational Note: Memory helps the AI maintain context across conversations.
 * User memory persists across all projects, project memory is specific to a project.
 */
export interface MemoryData {
  user_memory: string | null;
  project_memory: string | null;
}

/**
 * Cost Tracking Types
 * Educational Note: These types match the backend cost tracking structure.
 */
export type { ActiveTask, ActiveTasksResponse, CostTracking, ModelCostBreakdown } from './contracts';
export type ProjectRole = 'owner' | 'editor' | 'viewer';

type ProjectCostsAxiosResponse = AxiosResponse<{
  success: true;
  costs: CostTracking;
}>;

/**
 * Project API Methods
 */
export const projectsAPI = {
  // List all projects
  list: (workspaceId: string) => api.get('/projects', { params: { workspace_id: workspaceId } }),

  // Create a new project
  create: (data: { name: string; description?: string; workspace_id: string }) =>
    api.post('/projects', data),

  // Get a specific project
  get: (id: string) => api.get(`/projects/${id}`),

  // Update a project
  update: (id: string, data: { name?: string; description?: string }) =>
    api.put(`/projects/${id}`, data),

  // Delete a project
  delete: (id: string) => api.delete(`/projects/${id}`),

  // Open a project (mark as accessed)
  open: (id: string) => api.post(`/projects/${id}/open`),

  // Get project cost tracking data
  getCosts: async (id: string): Promise<ProjectCostsAxiosResponse> => {
    const response = await api.get(`/projects/${id}/costs`);
    return {
      ...response,
      data: parseProjectCostsResponse(response.data),
    };
  },

  getActiveTasks: async (id: string): Promise<ActiveTasksResponse> => {
    const response = await api.get(`/projects/${id}/active-tasks`);
    return parseActiveTasksResponse(response.data);
  },

  // Get project memory data (user memory + project memory)
  getMemory: (id: string) => api.get(`/projects/${id}/memory`),

  // Update user and/or project memory (both fields optional)
  updateMemory: (id: string, data: { user_memory?: string; project_memory?: string }) =>
    api.put(`/projects/${id}/memory`, data),

  listMembers: async (id: string): Promise<ProjectMember[]> => {
    const response = await api.get(`/projects/${id}/members`);
    return parseProjectMembersResponse(response.data).members;
  },

  addMember: async (
    id: string,
    userId: string,
    role: ProjectRole,
  ): Promise<ProjectMember> => {
    const response = await api.post(`/projects/${id}/members`, {
      user_id: userId,
      role,
    });
    return parseProjectMemberResponse(response.data).member;
  },

  updateMemberRole: async (
    id: string,
    userId: string,
    role: ProjectRole,
  ): Promise<ProjectMember> => {
    const response = await api.put(`/projects/${id}/members/${userId}`, { role });
    return parseProjectMemberResponse(response.data).member;
  },

  removeMember: async (id: string, userId: string): Promise<void> => {
    await api.delete(`/projects/${id}/members/${userId}`);
  },

  createInvite: async (
    id: string,
    email: string,
    projectRole: ProjectRole,
  ): Promise<MembershipInvite> => {
    const response = await api.post(`/projects/${id}/invites`, {
      email,
      workspace_role: 'member',
      project_role: projectRole,
    });
    return parseProjectInviteResponse(response.data).invite;
  },
};
