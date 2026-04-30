import { z } from 'zod';

export class ContractParseError extends Error {
  constructor(contract: string, error: z.ZodError) {
    super(`${contract} contract mismatch: ${error.message}`);
    this.name = 'ContractParseError';
  }
}

function parseContract<T>(schema: z.ZodType<T>, payload: unknown, contract: string): T {
  const result = schema.safeParse(payload);
  if (!result.success) {
    throw new ContractParseError(contract, result.error);
  }
  return result.data;
}

const unknownRecordSchema = z.record(z.string(), z.unknown());

export const errorEnvelopeSchema = z.object({
  success: z.literal(false),
  error: z.string(),
}).strict();

const authUserSchema = z.object({
  id: z.string(),
  email: z.string().nullable().optional(),
  global_role: z.enum(['admin', 'user']).nullable().optional(),
}).strict();

const userIdentitySchema = z.object({
  id: z.string(),
  email: z.string().nullable().optional(),
  global_role: z.enum(['admin', 'user']),
  is_global_admin: z.boolean(),
  role: z.enum(['admin', 'user']),
  is_admin: z.boolean(),
  is_authenticated: z.boolean(),
}).strict();

const workspaceSummarySchema = z.object({
  id: z.string(),
  name: z.string(),
  role: z.enum(['owner', 'admin', 'member']),
  owner_user_id: z.string().nullable().optional(),
  is_personal: z.boolean(),
}).strict();

const workspaceMemberSchema = z.object({
  user_id: z.string(),
  email: z.string().nullable().optional(),
  role: z.enum(['owner', 'admin', 'member']),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
}).strict();

const projectMemberSchema = z.object({
  user_id: z.string(),
  email: z.string().nullable().optional(),
  role: z.enum(['owner', 'editor', 'viewer']),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
}).strict();

const inviteSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  email: z.string(),
  workspace_role: z.enum(['owner', 'admin', 'member']),
  project_id: z.string().nullable().optional(),
  project_role: z.enum(['owner', 'editor', 'viewer']).nullable().optional(),
  expires_at: z.string().nullable().optional(),
  token: z.string(),
}).strict();

const workspaceSessionContextSchema = z.object({
  available_workspaces: z.array(workspaceSummarySchema),
  selected_workspace: workspaceSummarySchema.nullable().optional(),
  selected_workspace_id: z.string().nullable().optional(),
  workspace_role: z.enum(['owner', 'admin', 'member']).nullable().optional(),
  can_manage_workspace: z.boolean(),
  can_create_project: z.boolean(),
}).strict();

export const workspaceSessionResponseSchema = z.object({
  success: z.literal(true),
  workspace: workspaceSessionContextSchema,
}).strict();

export const workspaceCreateResponseSchema = z.object({
  success: z.literal(true),
  workspace: workspaceSummarySchema,
}).strict();

export const workspaceMembersResponseSchema = z.object({
  success: z.literal(true),
  members: z.array(workspaceMemberSchema),
  count: z.number().int(),
}).strict();

export const workspaceInviteResponseSchema = z.object({
  success: z.literal(true),
  invite: inviteSchema,
}).strict();

export const inviteAcceptResponseSchema = z.object({
  success: z.literal(true),
  workspace: workspaceSummarySchema,
  workspace_role: z.enum(['owner', 'admin', 'member']),
  project_id: z.string().nullable().optional(),
  project_role: z.enum(['owner', 'editor', 'viewer']).nullable().optional(),
}).strict();

export const projectMembersResponseSchema = z.object({
  success: z.literal(true),
  members: z.array(projectMemberSchema),
  count: z.number().int(),
}).strict();

export const projectMemberResponseSchema = z.object({
  success: z.literal(true),
  member: projectMemberSchema,
}).strict();

export const projectInviteResponseSchema = z.object({
  success: z.literal(true),
  invite: inviteSchema,
}).strict();

const authSessionSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string().nullable().optional(),
  expires_in: z.number().int().nullable().optional(),
  token_type: z.string().nullable().optional(),
}).strict();

export const meResponseSchema = z.object({
  success: z.literal(true),
  auth_required: z.boolean(),
  asset_token: z.string().nullable().optional(),
  user: userIdentitySchema,
  workspace: workspaceSessionContextSchema,
}).strict();

export const authSessionResponseSchema = z.object({
  success: z.literal(true),
  user: authUserSchema.nullable().optional(),
  session: authSessionSchema.nullable().optional(),
  asset_token: z.string().nullable().optional(),
  workspace: workspaceSessionContextSchema.nullable().optional(),
}).strict();

const tokenUsageSchema = z.object({
  input: z.number().int().optional(),
  output: z.number().int().optional(),
}).strict();

export const messageSchema = z.object({
  id: z.string(),
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  timestamp: z.string(),
  model: z.string().nullable().optional(),
  tokens: tokenUsageSchema.optional(),
  error: z.boolean().optional(),
  citations: z.array(z.unknown()).optional(),
}).passthrough();

export const chatMessageResponseSchema = z.object({
  success: z.literal(true),
  user_message: messageSchema,
  assistant_message: messageSchema,
}).strict();

const emptyPayloadSchema = z.object({}).strict();

export const chatStreamEventSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('user_message'),
    payload: messageSchema,
  }).strict(),
  z.object({
    type: z.literal('assistant_delta'),
    payload: z.object({ delta: z.string() }).strict(),
  }).strict(),
  z.object({
    type: z.literal('assistant_done'),
    payload: messageSchema,
  }).strict(),
  z.object({
    type: z.literal('error'),
    payload: z.object({
      message: z.string(),
      assistant_message: messageSchema.nullable().optional(),
    }).strict(),
  }).strict(),
  z.object({
    type: z.literal('ping'),
    payload: emptyPayloadSchema,
  }).strict(),
]);

const citationChunkSchema = z.object({
  content: z.string(),
  chunk_id: z.string(),
  source_id: z.string(),
  source_name: z.string(),
  page_number: z.number().int(),
  chunk_index: z.number().int(),
}).strict();

export const citationResponseSchema = z.object({
  success: z.literal(true),
  chunk: citationChunkSchema,
}).strict();

export const processedContentResponseSchema = z.object({
  success: z.literal(true),
  content: z.string(),
  source_name: z.string(),
}).strict();

export const generatedAssetAccessSchema = z.object({
  project_id: z.string().min(1),
  filename: z.string().min(1),
  mime_type: z.string().min(1),
}).strict();

export const activeTaskSchema = z.object({
  id: z.string(),
  type: z.enum(['source', 'studio', 'background']),
  label: z.string(),
  detail: z.string(),
  status: z.string(),
  created_at: z.string().nullable().optional(),
  progress: z.string().nullable().optional(),
}).strict();

export const activeTasksResponseSchema = z.object({
  success: z.literal(true),
  tasks: z.array(activeTaskSchema),
  count: z.number().int(),
}).strict().superRefine((value, ctx) => {
  if (value.count !== value.tasks.length) {
    ctx.addIssue({
      code: 'custom',
      path: ['count'],
      message: 'count must match tasks length',
    });
  }
});

const costBucketSchema = z.object({
  provider: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  input_tokens: z.number().int(),
  output_tokens: z.number().int(),
  cache_creation_input_tokens: z.number().int().optional().default(0),
  cache_read_input_tokens: z.number().int().optional().default(0),
  provider_units: unknownRecordSchema.optional().default({}),
  cost: z.number(),
}).strict();

const costByModelSchema = z.record(z.string(), costBucketSchema);

export const projectCostsResponseSchema = z.object({
  success: z.literal(true),
  costs: z.object({
    total_cost: z.number(),
    by_model: costByModelSchema,
  }).strict(),
}).strict();

export const sourceRowSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: z.enum(['DOCUMENT', 'AUDIO', 'IMAGE', 'DATA', 'LINK', 'UNKNOWN']),
  status: z.enum(['uploaded', 'processing', 'embedding', 'ready', 'error', 'cancelled']),
  project_id: z.string().nullable().optional(),
  token_count: z.number().int().nullable().optional(),
  embedding_info: unknownRecordSchema.optional(),
}).strict();

export const studioJobSchema = z.object({
  id: z.string(),
  project_id: z.string().nullable().optional(),
  job_type: z.string().nullable().optional(),
  status: z.enum(['pending', 'processing', 'ready', 'error', 'cancelled']),
  progress: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  source_id: z.string().nullable().optional(),
  source_name: z.string().nullable().optional(),
  direction: z.string().nullable().optional(),
  started_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  job_data: unknownRecordSchema.optional(),
}).passthrough();

export const studioEventPayloadSchema = z.object({
  studio_item: z.string(),
  direction: z.string().nullable().optional(),
  source_ids: z.array(z.string()).default([]),
  status: z.enum(['pending', 'processing', 'ready', 'error', 'cancelled']).default('pending'),
}).strict();

export type ErrorEnvelope = z.infer<typeof errorEnvelopeSchema>;
export type MeResponse = z.infer<typeof meResponseSchema>;
export type AuthSessionResponse = z.infer<typeof authSessionResponseSchema>;
export type WorkspaceSummary = z.infer<typeof workspaceSummarySchema>;
export type WorkspaceSessionContext = z.infer<typeof workspaceSessionContextSchema>;
export type WorkspaceSessionResponse = z.infer<typeof workspaceSessionResponseSchema>;
export type WorkspaceMember = z.infer<typeof workspaceMemberSchema>;
export type ProjectMember = z.infer<typeof projectMemberSchema>;
export type MembershipInvite = z.infer<typeof inviteSchema>;
export type WorkspaceInviteResponse = z.infer<typeof workspaceInviteResponseSchema>;
export type InviteAcceptResponse = z.infer<typeof inviteAcceptResponseSchema>;
export type ProjectMembersResponse = z.infer<typeof projectMembersResponseSchema>;
export type ProjectMemberResponse = z.infer<typeof projectMemberResponseSchema>;
export type ProjectInviteResponse = z.infer<typeof projectInviteResponseSchema>;
export type Message = z.infer<typeof messageSchema>;
export type ChatMessageResponse = z.infer<typeof chatMessageResponseSchema>;
export type ChatStreamEvent = z.infer<typeof chatStreamEventSchema>;
export type CitationResponse = z.infer<typeof citationResponseSchema>;
export type ChunkContent = z.infer<typeof citationChunkSchema>;
export type ProcessedContentResponse = z.infer<typeof processedContentResponseSchema>;
export type ProcessedContent = Omit<ProcessedContentResponse, 'success'>;
export type GeneratedAssetAccess = z.infer<typeof generatedAssetAccessSchema>;
export type ActiveTask = z.infer<typeof activeTaskSchema>;
export type ActiveTasksResponse = z.infer<typeof activeTasksResponseSchema>;
export type ProjectCostsResponse = z.infer<typeof projectCostsResponseSchema>;
export type CostTracking = ProjectCostsResponse['costs'];
export type ModelCostBreakdown = CostTracking['by_model'][string];
export type SourceRow = z.infer<typeof sourceRowSchema>;
export type StudioJob = z.infer<typeof studioJobSchema>;
export type StudioEventPayload = z.infer<typeof studioEventPayloadSchema>;

export function parseErrorEnvelope(payload: unknown): ErrorEnvelope {
  return parseContract(errorEnvelopeSchema, payload, 'ErrorEnvelope');
}

export function parseMeResponse(payload: unknown): MeResponse {
  return parseContract(meResponseSchema, payload, 'MeResponse');
}

export function parseAuthSessionResponse(payload: unknown): AuthSessionResponse {
  return parseContract(authSessionResponseSchema, payload, 'AuthSessionResponse');
}

export function parseWorkspaceSessionResponse(payload: unknown): WorkspaceSessionResponse {
  return parseContract(workspaceSessionResponseSchema, payload, 'WorkspaceSessionResponse');
}

export function parseWorkspaceCreateResponse(payload: unknown): z.infer<typeof workspaceCreateResponseSchema> {
  return parseContract(workspaceCreateResponseSchema, payload, 'WorkspaceCreateResponse');
}

export function parseWorkspaceMembersResponse(payload: unknown): z.infer<typeof workspaceMembersResponseSchema> {
  return parseContract(workspaceMembersResponseSchema, payload, 'WorkspaceMembersResponse');
}

export function parseWorkspaceInviteResponse(payload: unknown): WorkspaceInviteResponse {
  return parseContract(workspaceInviteResponseSchema, payload, 'WorkspaceInviteResponse');
}

export function parseInviteAcceptResponse(payload: unknown): InviteAcceptResponse {
  return parseContract(inviteAcceptResponseSchema, payload, 'InviteAcceptResponse');
}

export function parseProjectMembersResponse(payload: unknown): ProjectMembersResponse {
  return parseContract(projectMembersResponseSchema, payload, 'ProjectMembersResponse');
}

export function parseProjectMemberResponse(payload: unknown): ProjectMemberResponse {
  return parseContract(projectMemberResponseSchema, payload, 'ProjectMemberResponse');
}

export function parseProjectInviteResponse(payload: unknown): ProjectInviteResponse {
  return parseContract(projectInviteResponseSchema, payload, 'ProjectInviteResponse');
}

export function parseChatMessageResponse(payload: unknown): ChatMessageResponse {
  return parseContract(chatMessageResponseSchema, payload, 'ChatMessageResponse');
}

export function parseChatStreamEvent(eventName: string, payload: unknown): ChatStreamEvent {
  return parseContract(
    chatStreamEventSchema,
    { type: eventName, payload },
    'ChatStreamEvent',
  );
}

export function parseCitationResponse(payload: unknown): CitationResponse {
  return parseContract(citationResponseSchema, payload, 'CitationResponse');
}

export function parseProcessedContentResponse(payload: unknown): ProcessedContentResponse {
  return parseContract(processedContentResponseSchema, payload, 'ProcessedContentResponse');
}

export function parseGeneratedAssetAccess(payload: unknown): GeneratedAssetAccess {
  return parseContract(generatedAssetAccessSchema, payload, 'GeneratedAssetAccess');
}

export function parseActiveTasksResponse(payload: unknown): ActiveTasksResponse {
  return parseContract(activeTasksResponseSchema, payload, 'ActiveTasksResponse');
}

export function parseProjectCostsResponse(payload: unknown): ProjectCostsResponse {
  return parseContract(projectCostsResponseSchema, payload, 'ProjectCostsResponse');
}
