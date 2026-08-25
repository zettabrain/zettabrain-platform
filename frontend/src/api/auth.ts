import client from './client'

export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: number
  username: string
  email: string
  system_role: 'admin' | 'user'
  is_active: boolean
  must_change_password: boolean
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const form = new URLSearchParams()
  form.append('username', username)
  form.append('password', password)
  const res = await client.post<LoginResponse>('/auth/token', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return res.data
}

export async function getMe(): Promise<User> {
  const res = await client.get<User>('/auth/me')
  return res.data
}

export async function changePassword(current: string, newPassword: string): Promise<void> {
  await client.post('/auth/change-password', {
    current_password: current,
    new_password: newPassword,
  })
}
