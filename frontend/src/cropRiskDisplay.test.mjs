import test from 'node:test';
import assert from 'node:assert/strict';
import { cropAssessmentKey, dedupeBestAssessmentByCrop, uniqueCropsForAssessment } from './cropRiskDisplay.mjs';

test('collapse duplicate crop cards and prefer the assessment with usable verified results', () => {
  const rows = [
    { crop: 'Rice', status: 'unavailable', hazards: [] },
    { crop: 'Spinach', status: 'unavailable', hazards: [] },
    { crop: 'rice', status: 'partially_assessed', hazards: [{ status: 'assessed', evaluation_status: 'trigger_detected' }] },
  ];
  const result = dedupeBestAssessmentByCrop(rows, (item) => item.crop, (item) => item.status);
  assert.equal(result.length, 2);
  assert.equal(result[0].status, 'partially_assessed');
  assert.equal(result[0].crop, 'rice');
  assert.equal(cropAssessmentKey('  RICE  '), cropAssessmentKey('Rice'));
});

test('keep unavailable distinct when no duplicate has usable assessment data', () => {
  const rows = [
    { crop: 'Carrot', status: 'unavailable', id: 1 },
    { crop: 'carrot', status: 'unavailable', id: 2 },
  ];
  const result = dedupeBestAssessmentByCrop(rows, (item) => item.crop, (item) => item.status);
  assert.equal(result.length, 1);
  assert.equal(result[0].id, 1);
  assert.equal(result[0].status, 'unavailable');
});

test('assess a repeated crop/location only once while keeping the same crop at another location', () => {
  const crops = [
    { crop_name: 'Rice', id: 9, latitude: 19.12341, longitude: 73.12341 },
    { crop_name: ' rice ', id: 8, latitude: 19.12342, longitude: 73.12342 },
    { crop_name: 'Rice', id: 7, latitude: 20.2, longitude: 74.2 },
  ];
  const result = uniqueCropsForAssessment(crops);
  assert.deepEqual(result.map((crop) => crop.id), [9, 7]);
});
