import client from './client'

export interface ChatSource {
  filename: string
  page: number | null
  section: string | null
}

export interface ChatResponse {
  answer: string
  confidence: number
  sources: ChatSource[]
  chunks: string[]
  provenance_sig: string | null
  model: string
  duration_ms: number
}

export interface ChatHistoryItem {
  id: number
  query: string
  answer: string
  confidence: number
  model: string
  created_at: string
  team_id: number
}

export async function sendChat(
  teamId: number,
  query: string
): Promise<ChatResponse> {
  const res = await client.post<ChatResponse>('/chat/', { team_id: teamId, query })
  return res.data
}

export async function getChatHistory(teamId: number): Promise<ChatHistoryItem[]> {
  const res = await client.get<ChatHistoryItem[]>(`/chat/history/${teamId}`)
  return res.data
}
