import React, { createContext, useContext, useState, useEffect } from 'react'
import { getTeams, type Team } from '../api/teams'
import { useAuth } from './AuthContext'

interface TeamContextValue {
  teams: Team[]
  activeTeam: Team | null
  setActiveTeam: (team: Team) => void
  isLoading: boolean
  refresh: () => void
}

const TeamContext = createContext<TeamContextValue | null>(null)

export function TeamProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const [teams, setTeams] = useState<Team[]>([])
  const [activeTeam, setActiveTeamState] = useState<Team | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const fetchTeams = () => {
    if (!user) return
    setIsLoading(true)
    getTeams()
      .then((data) => {
        setTeams(data)
        // restore last active team
        const lastId = localStorage.getItem('zb_active_team')
        const last = lastId ? data.find((t) => t.id === Number(lastId)) : null
        setActiveTeamState(last ?? data[0] ?? null)
      })
      .catch(console.error)
      .finally(() => setIsLoading(false))
  }

  useEffect(() => {
    fetchTeams()
  }, [user]) // eslint-disable-line react-hooks/exhaustive-deps

  const setActiveTeam = (team: Team) => {
    setActiveTeamState(team)
    localStorage.setItem('zb_active_team', String(team.id))
  }

  return (
    <TeamContext.Provider value={{ teams, activeTeam, setActiveTeam, isLoading, refresh: fetchTeams }}>
      {children}
    </TeamContext.Provider>
  )
}

export function useTeam() {
  const ctx = useContext(TeamContext)
  if (!ctx) throw new Error('useTeam must be used within TeamProvider')
  return ctx
}
