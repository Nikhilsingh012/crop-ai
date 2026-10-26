import React from 'react';
import { HazardAssessments } from './HazardAssessments.mjs';

const h = React.createElement;

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function noVerifiedRule(hazards) {
  return Array.isArray(hazards) && hazards.length > 0
    && hazards.every((item) => item?.status !== 'assessed' && item?.evaluation_status === 'no_applicable_rule');
}

function topHazardLines(hazards) {
  return (Array.isArray(hazards) ? hazards : [])
    .filter((hazard) => hazard?.status === 'assessed')
    .slice(0, 2)
    .map((hazard) => {
      const state = hazard.evaluation_status === 'trigger_detected' || hazard.evaluation_status === 'evaluated'
        ? 'forecast condition detected'
        : hazard.evaluation_status === 'no_trigger_detected' ? 'no rule trigger detected' : 'assessed';
      const trigger = (hazard.triggered_rules || []).find((rule) => rule?.triggered_hours?.length || rule?.triggered_days?.length);
      let matchedCondition = '';
      const comparison = { gt: '>', gte: '≥', lt: '<', lte: '≤' }[trigger?.operator] || trigger?.operator;
      if (trigger?.triggered_hours?.length) {
        const sample = trigger.triggered_hours[0];
        matchedCondition = ` (${sample.temperature_c} deg C ${comparison} ${trigger.threshold} ${trigger.unit})`;
      } else if (trigger?.triggered_days?.length) {
        const sample = trigger.triggered_days[0];
        const value = trigger.daily_field === 'temperature_min' ? sample.temperature_min_c : sample.temperature_max_c;
        const label = trigger.daily_field === 'temperature_min' ? 'Tmin' : 'Tmax';
        matchedCondition = ` (${label} ${value} deg C ${comparison} ${trigger.threshold} ${trigger.unit})`;
      }
      const index = finite(hazard.risk_index) ? ` (weather exposure index ${hazard.risk_index}/100)` : '';
      return `${hazard.title}: ${state}${matchedCondition}${index}`;
    });
}

function ruleWindowLabel(hazards) {
  const windows = [];
  for (const hazard of Array.isArray(hazards) ? hazards : []) {
    if (hazard?.status !== 'assessed') continue;
    const assessments = Array.isArray(hazard.rule_assessments) && hazard.rule_assessments.length
      ? hazard.rule_assessments
      : [hazard];
    for (const assessment of assessments) {
      const details = assessment.risk_index_details || {};
      const start = assessment.window_start || details.window_start;
      const end = assessment.window_end || details.window_end;
      if (typeof start === 'string' && typeof end === 'string') windows.push([start, end]);
    }
  }
  const unique = [...new Map(windows.map((window) => [window.join('|'), window])).values()];
  if (unique.length === 1) return unique[0][0] === unique[0][1] ? unique[0][0] : `${unique[0][0]} to ${unique[0][1]}`;
  if (unique.length > 1) return 'Rule-specific forecast windows';
  return null;
}

function modelView(assessment) {
  if (!assessment || assessment.status !== 'modelled_estimate' || !finite(assessment.risk_percent)) return null;
  const risk = Math.max(0, Math.min(100, Math.round(assessment.risk_percent)));
  const safe = finite(assessment.safe_percent) ? Math.max(0, Math.min(100, Math.round(assessment.safe_percent))) : 100 - risk;
  const level = String(assessment.level || (risk >= 60 ? 'HIGH' : risk >= 30 ? 'MODERATE' : 'LOW')).toUpperCase();
  const tone = ['low', 'moderate', 'high'].includes(assessment.tone)
    ? assessment.tone
    : level === 'HIGH' ? 'high' : level === 'MODERATE' ? 'moderate' : 'low';
  const levelLabel = level === 'HIGH' ? 'High' : level === 'MODERATE' ? 'Moderate' : level === 'LOW' ? 'Low' : level;
  const factors = (Array.isArray(assessment.factors) ? assessment.factors : [])
    .filter((factor) => factor && finite(factor.score))
    .slice(0, 4);
  const recommendations = (Array.isArray(assessment.recommendations) ? assessment.recommendations : [])
    .filter((item) => typeof item === 'string' && item.trim())
    .map((item) => item.trim());
  return {
    risk, safe, level, levelLabel, tone,
    badge: `${levelLabel} estimated risk`,
    alert: Boolean(assessment.alert) || level !== 'LOW',
    watch: Boolean(assessment.watch) || level === 'MODERATE',
    factors,
    recommendations,
    confidence: assessment.confidence || 'limited',
    confidenceReason: assessment.confidence_reason || '',
    modelName: assessment.model?.name || 'Crop weather risk model',
    modelVersion: assessment.model?.version || '',
    method: assessment.model?.method || 'deterministic agronomic heuristic',
    limitations: (Array.isArray(assessment.limitations) ? assessment.limitations : []).filter(Boolean),
  };
}

export function cropRiskCardView({ status, riskLevel, riskIndex, hazards = [], modelAssessment = null }) {
  const assessed = status === 'assessed';
  const partial = status === 'partially_assessed';
  const score = finite(riskIndex) ? riskIndex : null;
  const model = modelView(modelAssessment);
  if (model) {
    const top = model.factors[0];
    const verifiedNote = assessed
      ? 'A source-backed rule check is shown separately below.'
      : partial
        ? 'A source-backed indicator was also checked; it is shown separately below.'
        : 'No verified source-backed rule covers this crop, growth stage and location, so this percentage is a modelled agronomic estimate rather than a rule finding.';
    return {
      tone: model.tone,
      badge: model.badge,
      overview: `Estimated weather-related risk at this location is ${model.risk}%, leaving an estimated ${model.safe}% safe margin.${top ? ` The largest contributor is ${String(top.label || top.key).toLowerCase()} at ${Math.round(top.score)}%.` : ''} ${verifiedNote}`,
      index: null,
      unavailable: false,
      model,
      verifiedStatus: status || 'unavailable',
    };
  }
  if (assessed && score !== null && riskLevel) {
    const normalized = String(riskLevel).toLowerCase();
    const displayLevel = normalized.replace(/_/g, ' ').split(' ').map((word, index) => index === 0 ? `${word.slice(0, 1).toUpperCase()}${word.slice(1)}` : word).join(' ');
    const category = normalized === 'low' ? 'low' : ['moderate', 'medium'].includes(normalized) ? 'moderate' : ['high', 'very_high', 'critical'].includes(normalized) ? 'high' : 'neutral';
    return {
      tone: category,
      badge: `${displayLevel} risk`,
      overview: `The forecast indicates ${normalized.replace('_', ' ').toLowerCase()} weather exposure under the verified crop rules.`,
      index: score,
      unavailable: false,
      model: null,
    };
  }
  if (partial) {
    return {
      tone: 'partial', badge: 'Partially assessed',
      overview: score === null
        ? 'A verified weather indicator was checked; an overall risk level is not available.'
        : 'Some verified rules were assessed; other hazards remain unassessed.',
      index: score, unavailable: false, model: null,
    };
  }
  if (noVerifiedRule(hazards)) {
    return {
      tone: 'unavailable', badge: 'Unavailable',
      overview: 'Risk assessment unavailable - no verified rule for this crop and forecast.',
      index: null, unavailable: true, model: null,
    };
  }
  return {
    tone: 'unavailable', badge: 'Unable to assess',
    overview: 'This forecast could not be assessed with the available crop or weather information.',
    index: null, unavailable: true, model: null,
  };
}

function validMetric(value, minimum, maximum) {
  return finite(value) && value >= minimum && value <= maximum;
}

function weatherLines(weather, expectedRainfall) {
  const lines = [];
  const days = Array.isArray(weather?.forecast) ? weather.forecast.filter((day) => day && typeof day.date === 'string') : [];
  const dates = days.map((day) => day.date);
  const period = dates.length ? (dates[0] === dates[dates.length - 1] ? dates[0] : `${dates[0]} to ${dates[dates.length - 1]}`)
    : weather?.riskWindowHours ? `Next ${weather.riskWindowHours} hours` : 'Forecast dates unavailable';
  if (dates.length) {
    days.slice(0, 3).forEach((day) => {
      const metrics = [];
      if (validMetric(day.rainfall, 0, 10000)) metrics.push(`${day.rainfall} mm rain`);
      const high = validMetric(day.temperature_max, -100, 70) ? day.temperature_max : null;
      const low = validMetric(day.temperature_min, -100, 70) ? day.temperature_min : null;
      if (high !== null || low !== null) metrics.push(`temperature ${low === null ? '' : `${low} to `}${high === null ? '' : high} deg C`);
      if (metrics.length) lines.push({ key: day.date, label: day.date, value: metrics.join(' | ') });
    });
  }
  if (!lines.length && validMetric(expectedRainfall, 0, 100000)) {
    lines.push({ key: 'risk-window-rain', label: 'Assessment window', value: `${expectedRainfall} mm rainfall` });
  }
  const humidity = validMetric(weather?.current_humidity_percent, 0, 100)
    ? weather.current_humidity_percent
    : validMetric(weather?.humidity, 0, 100) ? weather.humidity : null;
  if (humidity !== null) lines.push({ key: 'humidity', label: 'Current humidity', value: `${humidity}%` });
  return { period, lines };
}

function actionsFrom(hazards, alerts) {
  const items = [];
  for (const hazard of Array.isArray(hazards) ? hazards : []) {
    if (hazard?.status !== 'assessed' || hazard?.evaluation_status === 'no_trigger_detected') continue;
    for (const action of hazard.recommended_actions || []) if (typeof action === 'string' && action.trim()) items.push(action.trim());
  }
  for (const alert of Array.isArray(alerts) ? alerts : []) {
    for (const action of alert?.recommended_actions || []) if (typeof action === 'string' && action.trim()) items.push(action.trim());
  }
  return [...new Set(items)];
}

export function CropRiskCard({
  cropName, status, riskLevel, riskIndex, hazards = [], modelAssessment = null, weather,
  expectedRainfall, riskWindowHours, forecastLabel, locationLabel,
  alerts = [], missingInputs = [], limitations = [], technicalContent,
}) {
  const view = cropRiskCardView({ status, riskLevel, riskIndex, hazards, modelAssessment });
  const model = view.model;
  const weatherView = weatherLines({ ...weather, riskWindowHours }, expectedRainfall);
  const verifiedActions = actionsFrom(hazards, alerts);
  const actions = [...new Set([...verifiedActions, ...(model?.recommendations || [])])].slice(0, model ? 4 : 2);
  const actionable = actions.length > 0;
  const actionMessage = actionable
    ? null
    : model
      ? 'No model or verified action crossed its recommendation threshold for this forecast. Keep scouting the crop.'
      : view.unavailable
        ? 'No verified recommendation is available for this crop and forecast.'
        : 'No verified action is indicated by the applicable rules.';
  const modelLimitations = model?.limitations || [];
  const detailItems = [...new Set([...(missingInputs || []), ...(limitations || []), ...modelLimitations])];
  const forecastCaption = ruleWindowLabel(hazards) || forecastLabel || weatherView.period;
  const topHazards = topHazardLines(hazards);

  return h('article', { className: `crop-risk-card crop-risk-card--${view.tone}`, 'aria-label': `${cropName} crop risk` },
    h('header', { className: 'crop-risk-card__header' },
      h('div', null, h('h3', null, cropName), h('p', null, forecastCaption, locationLabel ? ` | ${locationLabel}` : '')),
      h('span', { className: 'crop-risk-card__badge', 'aria-label': `Assessment status: ${view.badge}` }, view.badge),
    ),
    h('section', { className: 'crop-risk-card__section', 'aria-label': 'Risk overview' },
      h('h4', null, model ? 'Estimated weather risk' : 'Risk overview'),
      model
        ? h('div', { className: `crop-risk-score crop-risk-score--${model.tone}` },
            h('div', { className: 'crop-risk-score__top' },
              h('div', { className: 'crop-risk-score__metric' },
                h('span', null, model.alert ? '⚠ ' : '', 'Estimated risk'),
                h('strong', { className: `crop-risk-score__value crop-risk-score__value--${model.tone}` }, `${model.risk}%`),
                h('small', null, model.levelLabel),
              ),
              h('div', { className: 'crop-risk-score__metric crop-risk-score__metric--safe' },
                h('span', null, 'Estimated safe'),
                h('strong', { className: 'crop-risk-score__value crop-risk-score__value--safe' }, `${model.safe}%`),
                h('small', null, 'safe margin'),
              ),
            ),
            h('div', { className: 'crop-risk-score__track', role: 'progressbar', 'aria-label': `Estimated weather risk ${model.risk}%`, 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': model.risk },
              h('span', { className: `crop-risk-score__fill crop-risk-score__fill--${model.tone}`, style: { width: `${model.risk}%` } }),
            ),
            h('p', { className: 'crop-risk-score__caption' },
              model.watch ? h('strong', null, '⚠ Watch: ') : null,
              `Based on this crop's tolerances and the local forecast. ${model.risk >= 60 ? 'Protective action is worth planning before the risk window.' : model.risk >= 30 ? 'Monitor the crop and keep the main action ready.' : 'Conditions are broadly favourable, but keep normal scouting.'}`,
            ),
          )
        : null,
      h('p', null, view.overview),
      model && model.factors.length
        ? h('ul', { className: 'crop-risk-factors', 'aria-label': 'Weather risk contributors' },
            model.factors.slice(0, 3).map((factor) => h('li', { key: factor.key, className: `crop-risk-factors__item crop-risk-factors__item--${factor.tone || 'neutral'}` },
              h('div', { className: 'crop-risk-factors__head' },
                h('strong', null, factor.label || factor.key),
                h('span', null, `${Math.round(factor.score)}%`),
              ),
              factor.evidence ? h('small', null, factor.evidence) : null,
            )),
          )
        : null,
      model
        ? h('p', { className: 'crop-risk-card__note' },
            `Modelled estimate · ${model.modelName}${model.modelVersion ? ` v${model.modelVersion}` : ''} · ${model.confidence} confidence · not a probability of crop loss.`,
          )
        : null,
      !model && view.index !== null ? h('p', { className: 'crop-risk-card__index' }, h('strong', null, `Risk index ${view.index}/100`), h('span', null, 'Weather exposure index, not probability of crop damage.')) : null,
      topHazards.length ? h('p', { className: 'crop-risk-card__hazards' }, h('strong', null, 'Top hazard checks: '), topHazards.join(' | ')) : null,
    ),
    h('section', { className: 'crop-risk-card__section', 'aria-label': 'Weather outlook' },
      h('h4', null, 'Weather outlook'),
      weatherView.lines.length
        ? h('ul', { className: 'crop-risk-card__weather' }, weatherView.lines.map((line) => h('li', { key: line.key }, h('strong', null, line.label), h('span', null, line.value))))
        : h('p', null, 'No forecast weather measurements are available to display.'),
      weather?.stale ? h('p', { className: 'crop-risk-card__note' }, 'Forecast data may be stale.') : null,
    ),
    h('section', { className: 'crop-risk-card__section', 'aria-label': 'Recommended action' },
      h('h4', null, 'Recommended action'),
      actionable ? h('ul', null, actions.map((action) => h('li', { key: action }, action))) : h('p', null, actionMessage),
      model && actionable ? h('p', { className: 'crop-risk-card__note' }, 'Includes suggested checks from the crop model; confirm crop-specific actions locally.') : null,
    ),
    h('details', { className: 'crop-risk-card__details' },
      h('summary', null, 'Why this assessment?'),
      technicalContent,
      model ? h('div', { className: 'crop-risk-model-method' },
        h('p', null, h('strong', null, 'Modelled estimate method: '), `${model.method}. ${model.confidenceReason || ''}`),
        h('p', null, 'The percentage combines crop tolerances, growth stage, forecast heat, cold, rain, moisture deficit, humidity and wind. It is a screening estimate and does not replace the verified rule check below or local field inspection.'),
      ) : null,
      h(HazardAssessments, { hazards }),
      detailItems.length ? h('ul', { className: 'crop-risk-card__technical-list' }, detailItems.map((item) => h('li', { key: item }, item))) : null,
    ),
  );
}
