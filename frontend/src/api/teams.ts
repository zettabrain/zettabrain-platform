import client from './client'

export interface Team {
  id: number
  name: string
  slug: string
  docs_folder: string
  skills_enabled: boolean
  llm_provider: string | null
  llm_model: string | null
  embed_provider: string | null
  embed_model: string | null
}

export interface TeamMember {
  id: number
  username: string
  email: string
  team_role: 'manager' | 'member' | 'viewer'
}

export interface TeamStats {
  team_id: number
  doc_count: number
  collection_name: string
}

export async function getTeams(): Promise<Team[]> {
  const res = await client.get<Team[]>('/teams/')
  return res.data
}

export async function getTeam(teamId: number): Promise<Team> {
  const res = await client.get<Team>(`/teams/${teamId}`)
  return res.data
}

export async function createTeam(data: Partial<Team>): Promise<Team> {
  const res = await client.post<Team>('/teams/', data)
  return res.data
}

export async function updateTeam(teamId: number, data: Partial<Team>): Promise<Team> {
  const res = await client.patch<Team>(`/teams/${teamId}`, data)
  return res.data
}

export async function deleteTeam(teamId: number): Promise<void> {
  await client.delete(`/teams/${teamId}`)
}

export async function getTeamMembers(teamId: number): Promise<TeamMember[]> {
  const res = await client.get<TeamMember[]>(`/teams/${teamId}/members`)
  return res.data
}

export async function addTeamMember(teamId: number, userId: number, role: string): Promise<void> {
  await client.post(`/teams/${teamId}/members`, { user_id: userId, team_role: role })
}

export async function removeTeamMember(teamId: number, userId: number): Promise<void> {
  await client.delete(`/teams/${teamId}/members/${userId}`)
}

export async function getTeamStats(teamId: number): Promise<TeamStats> {
  const res = await client.get<TeamStats>(`/teams/${teamId}/stats`)
  return res.data
}

export async function ingestTeamDocs(teamId: number): Promise<{ message: string }> {
  const res = await client.post<{ message: string }>(`/ingest/${teamId}`)
  return res.data
}
