import client from './client'

export interface Skill {
  name: string
  description: string
  version: string
  business_type: string
  requires_corpus: boolean
  tags: string[]
  source: 'team' | 'global' | 'builtin'
}

export interface GenerationResult {
  id: string
  content: string
  citations: string[]
  skill_name: string
  model: string
  duration_ms: number
  created_at: string
}

export interface GenerationHistoryItem {
  id: number
  skill_name: string
  request_summary: string
  created_at: string
  model: string
  duration_ms: number
}

export async function getSkills(teamId: number): Promise<Skill[]> {
  const res = await client.get<Skill[]>(`/teams/${teamId}/skills`)
  return res.data
}

export async function generate(
  teamId: number,
  skillName: string,
  request: string,
  context?: Record<string, string>,
  overrides?: { temperature?: number; max_tokens?: number }
): Promise<GenerationResult> {
  const res = await client.post<GenerationResult>(`/teams/${teamId}/generate`, {
    skill_name: skillName,
    request,
    context: context ?? {},
    overrides: overrides ?? {},
  })
  return res.data
}

export async function getGenerationHistory(teamId: number): Promise<GenerationHistoryItem[]> {
  const res = await client.get<GenerationHistoryItem[]>(`/teams/${teamId}/generation-history`)
  return res.data
}

export function getPdfDownloadUrl(teamId: number, historyId: number): string {
  const token = localStorage.getItem('zb_token')
  return `/api/teams/${teamId}/generation-history/${historyId}/pdf?token=${token}`
}

export async function uploadSkill(teamId: number, file: File): Promise<{ message: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await client.post<{ message: string }>(`/teams/${teamId}/skills/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function deleteSkill(teamId: number, skillName: string): Promise<void> {
  await client.delete(`/teams/${teamId}/skills/${skillName}`)
}
