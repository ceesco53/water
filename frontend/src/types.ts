export type RatingColor = 'green' | 'blue' | 'yellow' | 'red'

export interface ScoreFactor {
  label: string
  impact: number
  reason: string
}

export interface Beach {
  id: string | number
  name: string
  status: 'safe' | 'unsafe' | 'caution' | 'unknown'
  status_code: number | null
}

export interface Gauge {
  site_code: string
  site_name: string
  description: string
  discharge_cfs: number | null
  gage_height_ft: number | null
  discharge_p80?: number | null
}

export interface Conditions {
  score: number
  rating: string
  rating_color: RatingColor
  score_factors: ScoreFactor[]
  swimguide: {
    status: 'safe' | 'unsafe' | 'caution' | 'unknown'
    beaches: Beach[]
    error?: string
  }
  weather: {
    rain_24h_in: number | null
    rain_72h_in: number | null
    wind_speed_mph: number | null
    wind_direction: string | null
  }
  gauges: {
    upstream: Gauge
    local: Gauge
    secondary: Gauge
  }
  water_temp_f: number | null
  last_updated: string
  cache_age_seconds: number
}
