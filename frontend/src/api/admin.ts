import client from './client'

export interface AdminStats {
  total_users: number
  active_users: number
  total_teams: number
  total_queries: number
  queries_this_month: number
  license: {
    plan: string
    state: string
    max_users: number
    max_teams: number
    expires_at: string | null
    days_remaining: number | null
  }
}

export interface AuditLogEntry {
  id: number
  user_id: number
  username: string
  team_id: number
  team_name: string
  query: string
  answer_snippet: string
  confidence: number
  model: string
  duration_ms: number
  created_at: string
  provenance_sig: string | null
}

export interface SystemConfig {
  [key: string]: string
}

export interface HealthStatus {
  ollama: { status: 'ok' | 'error'; message: string }
  openai: { status: 'ok' | 'error' | 'unconfigured'; message: string }
  claude: { status: 'ok' | 'error' | 'unconfigured'; message: string }
  disk_usage_gb: number
  disk_free_gb: number
  team_doc_counts: Record<string, number>
}

export interface AdminUser {
  id: number
  username: string
  email: string
  system_role: 'admin' | 'user'
  is_active: boolean
  must_change_password: boolean
  created_at: string
}

export async function getAdminStats(): Promise<AdminStats> {
  const res = await client.get<AdminStats>('/admin/stats')
  return res.data
}

export async function getAuditLog(params?: {
  team_id?: number
  user_id?: number
  limit?: number
  offset?: number
}): Promise<AuditLogEntry[]> {
  const res = await client.get<AuditLogEntry[]>('/admin/audit', { params })
  return res.data
}

export async function getSystemConfig(): Promise<SystemConfig> {
  const res = await client.get<SystemConfig>('/admin/settings')
  return res.data
}

export async function updateSystemConfig(config: Partial<SystemConfig>): Promise<SystemConfig> {
  const res = await client.put<SystemConfig>('/admin/settings', config)
  return res.data
}

export async function getHealth(): Promise<HealthStatus> {
  const res = await client.get<HealthStatus>('/admin/health')
  return res.data
}

export async function getAdminUsers(): Promise<AdminUser[]> {
  const res = await client.get<AdminUser[]>('/admin/users')
  return res.data
}

export async function createUser(data: {
  username: string
  email: string
  password: string
  system_role: string
}): Promise<AdminUser> {
  const res = await client.post<AdminUser>('/admin/users', data)
  return res.data
}

export async function updateUser(userId: number, data: Partial<AdminUser>): Promise<AdminUser> {
  const res = await client.patch<AdminUser>(`/admin/users/${userId}`, data)
  return res.data
}

export async function deleteUser(userId: number): Promise<void> {
  await client.delete(`/admin/users/${userId}`)
}

export async function verifyProvenance(logId: number): Promise<{ valid: boolean; message: string }> {
  const res = await client.get<{ valid: boolean; message: string }>(`/admin/audit/${logId}/verify`)
  return res.data
}
