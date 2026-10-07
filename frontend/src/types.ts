export type RatingColor = 'green' | 'blue' | 'yellow' | 'red'

export interface ScoreFactor {
  label: string
  impact: number
  reason: string
}

export type BacteriaStatus = 'safe' | 'caution' | 'unsafe' | 'unknown'

export interface BacteriaReading {
  source: 'Sound Rivers' | 'NC DEQ'
  site_id: string
  site_name: string
  status: BacteriaStatus
  advisory: string | null
  sample_date: string | null
  age_days: number | null
  mpn: number | null
  geomean_mpn: number | null
  salinity_ppt: number | null
  water_temp_f: number | null
  source_url: string
}

export interface NwsAlert {
  event: string
  severity: 'Extreme' | 'Severe' | 'Moderate' | 'Minor' | 'Unknown' | null
  headline: string | null
  ends: string | null
}

export interface WaterIncident {
  id: string
  type: string
  fish_kill: boolean
  algal_bloom: boolean
  date: string
  age_days: number
  waterbody: string | null
  location: string | null
  fish_count: number | null
  investigation_status: string | null
  findings: string | null
  distance_mi: number | null
}

export interface SewerSpill {
  id: string
  date: string
  age_days: number
  system: string | null
  location: string | null
  volume_gal: number | null
  volume_reached_water_gal: number | null
  reached_water: boolean
  waterbody: string | null
  ongoing: boolean
  cause: string | null
  distance_mi: number | null
}

export interface BacteriaRisk {
  probability: number
  caution_probability: number
  summer_storm: boolean
  summer_floor_rain_in: number
  rain_72h_in: number | null
  missing_inputs: string[]
  trained: { date: string; samples: number; exceedances: number; years: [number, number] }
  validation: { loyo_auc: number; loyo_brier: number; base_rate_brier: number; formula_auc: number }
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
  bacteria: {
    primary: BacteriaReading | null
    readings: BacteriaReading[]
  }
  bacteria_risk: BacteriaRisk | null
  weather: {
    rain_24h_in: number | null
    rain_72h_in: number | null
    rain_7d_in: number | null
    // Set when KEWN's gauge is out (PNO) or missing reports; rain may be undercounted
    rain_gauge_issue: string | null
    wind_speed_mph: number | null
    wind_direction: string | null
    rain_forecast_pct: number | null
    rain_forecast_period: string | null
    qpf_72h_in: number | null
    thunder_pct_6h: number | null
    thunder_pct_24h: number | null
  }
  // null = feed unreachable; [] = checked, nothing found
  alerts: NwsAlert[] | null
  reports: {
    radius_mi: number
    lookback_days: number
    incidents: WaterIncident[] | null
    sewer_spills: SewerSpill[] | null
  }
  water: {
    temp_f: number | null
    temp_source: string | null
    temp_date: string | null
    salinity_ppt: number | null
    salinity_site: string | null
    salinity_date: string | null
  }
  vibrio: {
    level: 'low' | 'elevated' | 'high' | 'unknown'
    reason: string
  }
  gauges: {
    upstream: Gauge
    local: Gauge
  }
  last_updated: string
  cache_age_seconds: number
}
