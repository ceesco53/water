import axios from 'axios'
import type { Conditions } from './types'

export async function fetchConditions(): Promise<Conditions> {
  const { data } = await axios.get<Conditions>('/api/conditions')
  return data
}

export async function forceRefresh(): Promise<Conditions> {
  const { data } = await axios.post<Conditions>('/api/refresh')
  return data
}
