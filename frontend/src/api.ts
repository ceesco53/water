import axios from 'axios'
import type { Conditions, HistorySnapshot } from './types'

export async function fetchConditions(): Promise<Conditions> {
  const { data } = await axios.get<Conditions>('/api/conditions')
  return data
}

export async function forceRefresh(): Promise<Conditions> {
  const { data } = await axios.post<Conditions>('/api/refresh')
  return data
}

export async function fetchHistory(days: number): Promise<HistorySnapshot[]> {
  const since = new Date(Date.now() - days * 86_400_000).toISOString()
  const { data } = await axios.get<HistorySnapshot[]>('/api/history/snapshots', { params: { since } })
  return data
}
