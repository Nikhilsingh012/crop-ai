import type { ReactElement, ReactNode } from 'react';
import type { HazardAssessment } from './HazardAssessments.mjs';

export type RiskCardWeather = {
  forecast?: Array<{ date?: string; rainfall?: number | null; temperature_max?: number | null; temperature_min?: number | null }>;
  humidity?: number | null;
  current_humidity_percent?: number | null;
  stale?: boolean;
  riskWindowHours?: number | null;
};

export type RiskCardModelFactor = {
  key: string;
  label?: string;
  score: number;
  level?: string;
  tone?: string;
  weight?: number | null;
  evidence?: string;
};

export type RiskCardModelAssessment = {
  status?: string;
  risk_percent: number | null;
  safe_percent: number | null;
  level?: string;
  tone?: string;
  alert?: boolean;
  watch?: boolean;
  label?: string;
  summary?: string;
  factors?: RiskCardModelFactor[];
  recommendations?: string[];
  confidence?: string;
  confidence_reason?: string;
  profile_source?: string;
  limitations?: string[];
  model?: { name?: string; version?: string; method?: string; is_probability?: boolean };
};

export type RiskCardProps = {
  cropName: string;
  status?: string;
  riskLevel?: string | null;
  riskIndex?: number | null;
  hazards?: HazardAssessment[];
  modelAssessment?: RiskCardModelAssessment | null;
  weather?: RiskCardWeather;
  expectedRainfall?: number | null;
  riskWindowHours?: number | null;
  forecastLabel?: string;
  locationLabel?: string;
  alerts?: Array<{ recommended_actions?: string[] }>;
  missingInputs?: string[];
  limitations?: string[];
  technicalContent?: ReactNode;
};

export function cropRiskCardView(props: Pick<RiskCardProps, 'status' | 'riskLevel' | 'riskIndex' | 'hazards' | 'modelAssessment'>): {
  tone: string;
  badge: string;
  overview: string;
  index: number | null;
  unavailable: boolean;
  model?: {
    risk: number;
    safe: number;
    level: string;
    levelLabel: string;
    tone: string;
    badge: string;
    alert: boolean;
    watch: boolean;
    factors: RiskCardModelFactor[];
    recommendations: string[];
    confidence: string;
    confidenceReason: string;
    modelName: string;
    modelVersion: string;
    method: string;
    limitations: string[];
  } | null;
  verifiedStatus?: string;
};
export function CropRiskCard(props: RiskCardProps): ReactElement;
