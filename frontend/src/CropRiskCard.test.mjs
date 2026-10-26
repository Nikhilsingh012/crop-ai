import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import ReactDOMServer from 'react-dom/server';
import { CropRiskCard, cropRiskCardView } from './CropRiskCard.mjs';

function render(props) {
  return ReactDOMServer.renderToStaticMarkup(React.createElement(CropRiskCard, props));
}

test('supported risk levels use labeled, distinct status treatments and a risk index', () => {
  for (const [level, tone, label] of [
    ['LOW', 'low', 'Low risk'], ['MODERATE', 'moderate', 'Moderate risk'], ['HIGH', 'high', 'High risk'], ['VERY_HIGH', 'high', 'Very high risk'],
  ]) {
    const view = cropRiskCardView({ status: 'assessed', riskLevel: level, riskIndex: 12 });
    assert.equal(view.tone, tone);
    assert.equal(view.badge, label);
    const html = render({ cropName: 'Tomato', status: 'assessed', riskLevel: level, riskIndex: 12 });
    assert.match(html, new RegExp(label));
    assert.match(html, /Risk index 12\/100/);
    assert.match(html, /not probability of crop damage/);
  }
});

test('no applicable verified rule is unavailable, not low risk, and says so once in the main view', () => {
  const html = render({
    cropName: 'Carrot', status: 'unavailable', riskLevel: 'UNAVAILABLE', riskIndex: null,
    hazards: [{ hazard: 'HEAT_STRESS', title: 'Heat stress', status: 'unavailable', evaluation_status: 'no_applicable_rule', explanation: 'No rule applies.', sources: [] }],
  });
  assert.match(html, /Risk assessment unavailable - no verified rule for this crop and forecast/);
  assert.doesNotMatch(html, /Low risk|Risk index/);
  assert.match(html, /<details class="crop-risk-card__details">/);
});

test('missing growth stage, location, or forecast is not converted into low risk', () => {
  const view = cropRiskCardView({ status: 'unavailable', hazards: [{ status: 'unavailable', evaluation_status: 'insufficient_data' }] });
  assert.equal(view.tone, 'unavailable');
  assert.equal(view.index, null);
  const html = render({ cropName: 'Potato', status: 'unavailable', hazards: [{ hazard: 'HEAT_STRESS', title: 'Heat', status: 'unavailable', evaluation_status: 'insufficient_data', explanation: 'Growth stage is missing.' }], missingInputs: ['Farm state is missing.'] });
  assert.match(html, /Unable to assess/);
  assert.doesNotMatch(html, /Low risk|Risk index/);
  assert.match(html, /Farm state is missing/);
});

test('partial indicator has no score and weather outlook contains only supplied measurements', () => {
  const html = render({
    cropName: 'Wheat', status: 'partially_assessed', riskIndex: null,
    hazards: [{ hazard: 'HEAT_STRESS', title: 'Heat', status: 'assessed', evaluation_status: 'trigger_detected', assessment_type: 'deterministic_exposure_indicator', recommended_actions: ['Check the local advisory.'] }],
    weather: { forecast: [{ date: '2026-10-25', rainfall: 0, temperature_max: 31, temperature_min: null }, { date: '2026-10-26', rainfall: null, temperature_max: null, temperature_min: null }], humidity: 67 },
  });
  assert.match(html, /Partially assessed/);
  assert.match(html, /2026-10-25 to 2026-10-26/);
  assert.match(html, /0 mm rain/);
  assert.match(html, /31 deg C/);
  assert.match(html, /67%/);
  assert.doesNotMatch(html, /<strong>2026-10-26<\/strong>|Temperature unavailable|not reported/);
  assert.doesNotMatch(html, /Risk index/);
  assert.match(html, /Check the local advisory/);
  assert.match(html, /Top hazard checks: <\/strong>Heat: forecast condition detected/);
  assert.doesNotMatch(html, /undefined/);
});

test('API-shaped rice, wheat, and potato indicators render without invented scores', () => {
  const apiResults = [
    {
      crop: 'Rice', rule: 'rice_flowering_hourly_temperature_above_35c_icar_review',
      period: '2026-10-26T11:00', threshold: '35 deg C', index: 2,
      explanation: 'Forecast hourly air temperature was above 35 deg C. This is weather exposure, not evidence of crop damage.',
      weather: { forecast: [{ date: '2026-10-26', temperature_max: 37, temperature_min: 24, rainfall: 0 }] },
    },
    {
      crop: 'Wheat', rule: 'wheat_grain_filling_daily_tmax_above_30c_imd_kalp',
      period: '2026-10-26', threshold: '30 deg C', index: 20,
      explanation: 'Daily forecast maximum temperature exceeds 30 deg C on 2026-10-26.',
      weather: { forecast: [{ date: '2026-10-26', temperature_max: 31, temperature_min: null, rainfall: null }] },
    },
    {
      crop: 'Potato', rule: 'potato_tuberization_daily_tmin_at_or_above_20c_icar_cpri',
      period: '2026-10-26 to 2026-10-27', threshold: '20 deg C', index: 50,
      explanation: 'This is outside the source stated preferred tuberization condition; it does not establish crop damage.',
      weather: { forecast: [{ date: '2026-10-26', temperature_max: 29, temperature_min: 20, rainfall: 0 }, { date: '2026-10-27', temperature_max: 30, temperature_min: 21, rainfall: null }] },
    },
  ];
  for (const item of apiResults) {
    const html = render({
      cropName: item.crop, status: 'partially_assessed', riskLevel: 'PARTIAL', riskIndex: null,
      forecastLabel: item.period, weather: item.weather,
      hazards: [{
        hazard: 'HEAT_STRESS', title: 'Heat stress', status: 'assessed',
        evaluation_status: 'trigger_detected', assessment_type: 'deterministic_exposure_indicator',
        risk_index: item.index,
        risk_index_type: 'rule_window_weather_exposure_share',
        risk_index_details: { exposed_observations: 1, valid_observations: item.crop === 'Rice' ? 48 : item.crop === 'Wheat' ? 5 : 2, observation_unit: item.crop === 'Rice' ? 'hourly forecast observations' : item.crop === 'Wheat' ? 'daily Tmax forecasts' : 'daily Tmin forecasts', window_start: item.period.split(' to ')[0], window_end: item.period.includes(' to ') ? item.period.split(' to ')[1] : item.period },
        explanation: item.explanation, matched_rule_ids: [item.rule],
        triggered_rules: item.crop === 'Rice'
          ? [{ assessment_type: 'deterministic_exposure_indicator', rule_id: item.rule, operator: 'gt', threshold: 35, unit: 'deg C', forecast_timezone: 'Asia/Kolkata', triggered_hours: [{ time: '2026-10-26T11:00+05:30', temperature_c: 36 }] }]
          : [{ assessment_type: 'deterministic_exposure_indicator', rule_id: item.rule, operator: item.crop === 'Potato' ? 'gte' : 'gt', threshold: item.crop === 'Potato' ? 20 : 30, unit: 'deg C', daily_field: item.crop === 'Potato' ? 'temperature_min' : 'temperature_max', triggered_days: [{ date: '2026-10-26', temperature_min_c: 20, temperature_max_c: 31 }] }],
        recommended_actions: item.crop === 'Rice' ? [] : ['Check the current local advisory.'],
      }],
    });
    assert.match(html, new RegExp(item.crop));
    assert.match(html, new RegExp(item.period.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    assert.match(html, /Partially assessed/);
    assert.match(html, /forecast condition detected/);
    assert.match(html, new RegExp(item.crop === 'Rice' ? '36 deg C &gt; 35 deg C' : item.crop === 'Wheat' ? 'Tmax 31 deg C &gt; 30 deg C' : 'Tmin 20 deg C ≥ 20 deg C'));
    assert.match(html, /Why this assessment\?/);
    assert.match(html, new RegExp(`weather exposure index ${item.index}\\/100`));
    assert.doesNotMatch(html, /Risk index \d+\/100|probability of crop damage/);
    assert.match(html, /not a probability or damage score/);
    assert.match(html, new RegExp(item.threshold.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    assert.match(html, new RegExp(item.explanation.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('separate rule-window indices render their own counts and windows without a combined score', () => {
  const html = render({
    cropName: 'Wheat', status: 'partially_assessed', riskIndex: null,
    hazards: [{
      hazard: 'HEAT_STRESS', title: 'Heat stress', status: 'assessed',
      evaluation_status: 'trigger_detected', assessment_type: 'deterministic_exposure_indicator',
      risk_index: null, risk_index_type: 'separate_per_rule_weather_exposure_shares',
      rule_assessments: [
        { rule_id: 'rule-a', risk_index: 40, risk_index_details: { exposed_observations: 2, valid_observations: 5, observation_unit: 'daily Tmax forecasts' }, window_start: '2026-10-15', window_end: '2026-10-19' },
        { rule_id: 'rule-b', risk_index: 20, risk_index_details: { exposed_observations: 1, valid_observations: 5, observation_unit: 'daily Tmax forecasts' }, window_start: '2026-10-15', window_end: '2026-10-19' },
      ],
      explanation: 'Two rules were evaluated independently.', recommended_actions: [],
    }],
  });
  assert.match(html, /rule-a: weather exposure index 40\/100 = 2 of 5 daily Tmax forecasts \(2026-10-15 to 2026-10-19\)/);
  assert.match(html, /rule-b: weather exposure index 20\/100 = 1 of 5 daily Tmax forecasts/);
  assert.match(html, /not probability or damage score/);
  assert.doesNotMatch(html, /Risk index \d+\/100/);
  assert.doesNotMatch(html, /60\/100|30\/100|average/i);
});

test('unsupported hazards remain in the collapsed technical section and do not create recommendations', () => {
  const html = render({
    cropName: 'Spinach', status: 'unavailable', riskIndex: null,
    hazards: [{ hazard: 'HEAT_STRESS', title: 'Heat stress', status: 'unavailable', evaluation_status: 'no_applicable_rule', explanation: 'Candidate rule was excluded.', skipped_rules: [{ rule_id: 'provisional-spinach-rule', reason: 'unverified' }] }],
  });
  const detailsAt = html.indexOf('<details');
  assert.ok(detailsAt > 0);
  assert.ok(html.indexOf('provisional-spinach-rule') > detailsAt);
  assert.match(html, /No verified recommendation is available/);
  assert.equal((html.match(/Risk assessment unavailable - no verified rule/g) || []).length, 1);
});
