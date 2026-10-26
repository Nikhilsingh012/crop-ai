function normalizeCropName(name) {
  return typeof name === 'string' ? name.trim().toLocaleLowerCase().replace(/[^a-z0-9]+/g, ' ').trim() : '';
}

function assessmentRank(item, statusOf) {
  const status = statusOf(item);
  const statusRank = status === 'assessed' ? 3 : status === 'partially_assessed' ? 2 : status === 'unavailable' ? 0 : 1;
  const hazards = Array.isArray(item?.hazards) ? item.hazards : Array.isArray(item?.risk?.hazards) ? item.risk.hazards : [];
  const usefulHazards = hazards.filter((hazard) => hazard?.status === 'assessed').length;
  const triggers = hazards.filter((hazard) => hazard?.evaluation_status === 'trigger_detected' || hazard?.evaluation_status === 'evaluated').length;
  return statusRank * 10000 + usefulHazards * 100 + triggers;
}

export function dedupeBestAssessmentByCrop(items, cropNameOf, statusOf) {
  const best = new Map();
  for (const item of Array.isArray(items) ? items : []) {
    const key = normalizeCropName(cropNameOf(item));
    if (!key) continue;
    const current = best.get(key);
    if (!current || assessmentRank(item, statusOf) > assessmentRank(current, statusOf)) best.set(key, item);
  }
  return [...best.values()];
}

export function cropAssessmentKey(name) {
  return normalizeCropName(name);
}

export function uniqueCropsForAssessment(crops) {
  const unique = new Map();
  for (const crop of Array.isArray(crops) ? crops : []) {
    const name = normalizeCropName(crop?.crop_name);
    if (!name) continue;
    const lat = Number.isFinite(crop.latitude) ? crop.latitude.toFixed(3) : crop.state || crop.district || 'unknown-location';
    const lon = Number.isFinite(crop.longitude) ? crop.longitude.toFixed(3) : '';
    const key = `${name}|${lat}|${lon}`;
    if (!unique.has(key)) unique.set(key, crop);
  }
  return [...unique.values()];
}
