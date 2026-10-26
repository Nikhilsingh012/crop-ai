import type { ReactElement } from 'react';

export type HazardAssessment = {
  hazard: string;
  title: string;
  status: string;
  outcome?: 'ASSESSED/TRIGGERED' | 'ASSESSED/NO_TRIGGER' | 'INSUFFICIENT_DATA' | 'UNSUPPORTED';
  evaluation_status?: 'evaluated' | 'no_trigger_detected' | 'insufficient_data' | 'no_applicable_rule' | 'forecast_unavailable' | string;
  explanation: string;
  risk_index?: number | null;
  risk_index_type?: string;
  risk_index_details?: { exposed_observations: number; valid_observations: number; observation_unit: string; window_start?: string; window_end?: string; formula?: string; interpretation?: string };
  rule_assessments?: Array<{ rule_id: string; evaluation_status: string; risk_index: number | null; risk_index_details: { exposed_observations: number; valid_observations: number; observation_unit: string; window_start?: string; window_end?: string }; threshold?: number; operator?: string; unit?: string; window_start?: string; window_end?: string }>;
  severity?: string | null;
  assessment_type?: string;
  sources?: Array<{ publication_title?: string; source_url?: string }>;
  triggered_rules?: Array<{ assessment_type?: string; daily_field?: string; exposed_hours?: number; forecast_hours?: number; forecast_timezone?: string; threshold?: number; unit?: string; operator?: string; triggered_hours?: Array<{ time: string; temperature_c: number }>; triggered_days?: Array<{ date: string; temperature_max_c?: number; temperature_min_c?: number }> }>;
  limitations?: string[];
  recommended_actions?: string[];
  reason?: string;
  matched_rule_ids?: string[];
  skipped_rule_ids?: string[];
  thresholds?: Array<{ rule_id?: string; value?: number; unit?: string }>;
  measured_values?: Array<{ parameter?: string; minimum?: number; maximum?: number; unit?: string }>;
  skipped_rules?: Array<{ rule_id: string; reason: string }>;
};

export function HazardAssessments(props: { hazards: HazardAssessment[] }): ReactElement | null;
