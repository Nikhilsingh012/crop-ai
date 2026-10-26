import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import ReactDOMServer from 'react-dom/server';
import { HazardAssessments } from './HazardAssessments.mjs';

test('renders evaluated and unsupported hazards separately, with source evidence', () => {
  const html = ReactDOMServer.renderToStaticMarkup(React.createElement(HazardAssessments, {
    hazards: [
      {
        hazard: 'HEAT_STRESS', title: 'Heat stress', status: 'assessed', outcome: 'ASSESSED/TRIGGERED', evaluation_status: 'evaluated', severity: 'MODERATE',
        risk_index: 2, explanation: 'One forecast hour crossed the exposure threshold.',
        triggered_rules: [{ exposed_hours: 1, forecast_hours: 48, threshold: 35, unit: 'deg C', operator: 'gt' }],
        sources: [{ publication_title: 'Rice heat guidance', source_url: 'https://example.org/rice' }],
      },
      { hazard: 'DRY_SPELL', title: 'Dry spell', status: 'unavailable', evaluation_status: 'no_applicable_rule', explanation: 'No verified matching rule.',
        skipped_rules: [{ rule_id: 'rice_dry_candidate', reason: 'Evidence status is provisional.' }] },
      { hazard: 'COLD_FROST', title: 'Cold / frost', status: 'assessed', evaluation_status: 'no_trigger_detected', severity: 'LOW', risk_index: 0, explanation: 'No forecast sample crossed the rule threshold.' },
    ],
  }));
  assert.match(html, /MODERATE exposure index 2\/100/);
  assert.match(html, /Threshold exposure: 1\/48 hourly samples crossed gt 35deg C/);
  assert.match(html, /href="https:\/\/example.org\/rice"/);
  assert.match(html, /Not evaluated \(no applicable rule\): No verified matching rule/);
  assert.match(html, /rice_dry_candidate: Evidence status is provisional/);
  assert.match(html, /No trigger detected\. LOW exposure index 0\/100/);
});

test('renders missing-input assessments distinctly from hazards with no matching rule', () => {
  const html = ReactDOMServer.renderToStaticMarkup(React.createElement(HazardAssessments, {
    hazards: [{ hazard: 'HEAT_STRESS', title: 'Heat stress', status: 'unavailable', evaluation_status: 'insufficient_data', explanation: 'Growth stage is missing.' }],
  }));
  assert.match(html, /Not evaluated \(missing input\): Growth stage is missing/);
});

test('renders deterministic crop-weather indicators without displaying a probability score', () => {
  const html = ReactDOMServer.renderToStaticMarkup(React.createElement(HazardAssessments, {
    hazards: [{
      hazard: 'HEAT_STRESS', title: 'Heat stress', status: 'assessed',
      assessment_type: 'deterministic_exposure_indicator', evaluation_status: 'trigger_detected',
      risk_index: null, explanation: 'Daily forecast Tmax exceeds 30 deg C on 2026-10-16.',
      triggered_rules: [{ assessment_type: 'deterministic_exposure_indicator', operator: 'gt', threshold: 30, unit: 'deg C',
        triggered_days: [{ date: '2026-10-16', temperature_max_c: 30.5 }] }],
    }],
  }));
  assert.match(html, /Published weather threshold crossed/);
  assert.match(html, /2026-10-16 \(30\.5 C\)/);
  assert.doesNotMatch(html, /exposure index|probability/);
});

test('explains the potato daily Tmin condition as exposure, not crop damage', () => {
  const html = ReactDOMServer.renderToStaticMarkup(React.createElement(HazardAssessments, {
    hazards: [{
      hazard: 'HEAT_STRESS', title: 'Heat stress', status: 'assessed',
      assessment_type: 'deterministic_exposure_indicator', evaluation_status: 'trigger_detected',
      risk_index: null, explanation: 'Outside the preferred condition; this does not establish crop damage.',
      triggered_rules: [{ assessment_type: 'deterministic_exposure_indicator', daily_field: 'temperature_min', operator: 'gte', threshold: 20, unit: 'deg C',
        triggered_days: [{ date: '2026-10-15', temperature_min_c: 20 }] }],
    }],
  }));
  assert.match(html, /Daily minimum-temperature condition/);
  assert.match(html, /2026-10-15 \(Tmin 20 C\)/);
  assert.match(html, /does not establish crop damage/);
  assert.doesNotMatch(html, /probability|exposure index/);
});

test('renders hourly rice flowering exposure with date, threshold, source, and no score', () => {
  const html = ReactDOMServer.renderToStaticMarkup(React.createElement(HazardAssessments, {
    hazards: [{
      hazard: 'HEAT_STRESS', title: 'Heat stress', status: 'assessed',
      assessment_type: 'deterministic_exposure_indicator', evaluation_status: 'trigger_detected',
      risk_index: null, explanation: 'Forecast hourly air temperature was above 35 deg C; this is not evidence of crop damage.',
      triggered_rules: [{ assessment_type: 'deterministic_exposure_indicator', operator: 'gt', threshold: 35, unit: 'deg C', forecast_timezone: 'Asia/Kolkata',
        triggered_hours: [{ time: '2026-10-15T07:00', temperature_c: 35.4 }] }],
      sources: [{ publication_title: 'ICAR review', source_url: 'https://epubs.icar.org.in/rice-review' }],
    }],
  }));
  assert.match(html, /Published weather threshold crossed/);
  assert.match(html, /Forecast hourly temperature condition \(Asia\/Kolkata\)/);
  assert.match(html, /2026-10-15T07:00 \(35\.4 C\)/);
  assert.match(html, /threshold gt 35 deg C/);
  assert.match(html, /Source: ICAR review/);
  assert.doesNotMatch(html, /exposure index|probability/);
});
