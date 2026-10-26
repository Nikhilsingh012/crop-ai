import React from 'react';

function unavailableLabel(status) {
  if (status === 'insufficient_data') return 'Not evaluated (missing input)';
  if (status === 'forecast_unavailable') return 'Forecast unavailable';
  return 'Not evaluated (no applicable rule)';
}

export function HazardAssessments({ hazards }) {
  if (!Array.isArray(hazards) || hazards.length === 0) return null;
  return React.createElement(
    'ul',
    { className: 'hazard-assessments' },
    hazards.map((hazard) => React.createElement(
      'li',
      { key: hazard.hazard },
      React.createElement('strong', null, `${hazard.title}: `),
      hazard.outcome ? `${hazard.outcome}: ` : '',
      hazard.status === 'unavailable'
        ? `${unavailableLabel(hazard.evaluation_status)}: ${hazard.explanation || 'No explanation supplied.'}`
        : hazard.assessment_type === 'deterministic_exposure_indicator'
          ? `${hazard.evaluation_status === 'trigger_detected' ? 'Published weather threshold crossed' : 'No trigger detected'}: ${hazard.explanation || 'No explanation supplied.'}`
        : `${hazard.evaluation_status === 'no_trigger_detected' ? 'No trigger detected. ' : ''}${hazard.severity || 'ASSESSED'} exposure index ${hazard.risk_index}/100. ${hazard.explanation || 'No explanation supplied.'}`,
      hazard.risk_index_type === 'rule_window_weather_exposure_share' && hazard.risk_index_details
        ? ` Rule-window weather exposure index ${hazard.risk_index}/100 = ${hazard.risk_index_details.exposed_observations} of ${hazard.risk_index_details.valid_observations} ${hazard.risk_index_details.observation_unit} (${hazard.risk_index_details.window_start} to ${hazard.risk_index_details.window_end}); this is not a probability or damage score.`
        : '',
      ...(hazard.risk_index_type === 'separate_per_rule_weather_exposure_shares' && Array.isArray(hazard.rule_assessments)
        ? hazard.rule_assessments.map((assessment) => React.createElement(
          'span', { key: `rule-index-${assessment.rule_id}` },
          ` ${assessment.rule_id}: weather exposure index ${assessment.risk_index}/100 = ${assessment.risk_index_details.exposed_observations} of ${assessment.risk_index_details.valid_observations} ${assessment.risk_index_details.observation_unit} (${assessment.window_start} to ${assessment.window_end}); not probability or damage score.`,
        )) : []),
      ...(hazard.triggered_rules || []).map((rule, index) => React.createElement(
        'span',
        { key: `trigger-${index}` },
        rule.assessment_type === 'deterministic_exposure_indicator'
          ? rule.triggered_hours?.length
            ? ` Forecast hourly temperature condition (${rule.forecast_timezone || 'UTC'}): ` + rule.triggered_hours.map((hour) => `${hour.time} (${hour.temperature_c} C)`).join(', ') + `; threshold ${rule.operator} ${rule.threshold} ${rule.unit}.`
          : rule.triggered_days?.length
            ? (rule.daily_field === 'temperature_min' ? ' Daily minimum-temperature condition: ' : ' Forecast Tmax threshold: ') + rule.triggered_days.map((day) => `${day.date} (${rule.daily_field === 'temperature_min' ? 'Tmin ' + day.temperature_min_c : day.temperature_max_c} C)`).join(', ') + '; threshold ' + rule.operator + ' ' + rule.threshold + ' ' + rule.unit + '.'
            : ' No forecast day crossed this deterministic temperature condition.'
          : ` Threshold exposure: ${rule.exposed_hours}/${rule.forecast_hours} hourly samples crossed ${rule.operator || 'the threshold'} ${rule.threshold}${rule.unit}.`,
      )),
      ...(hazard.skipped_rules || []).map((rule) => React.createElement(
        'small',
        { key: `skipped-${rule.rule_id}`, className: 'hazard-rule-skip' },
        `${rule.rule_id}: ${rule.reason}`,
      )),
      ...(hazard.sources || []).filter((source) => source.source_url).map((source) => React.createElement(
        'a',
        { key: source.source_url, href: source.source_url, target: '_blank', rel: 'noreferrer' },
        `Source: ${source.publication_title || source.source_url}`,
      )),
      ...(hazard.limitations || []).map((limitation) => React.createElement('small', { key: limitation }, limitation)),
    )),
  );
}
