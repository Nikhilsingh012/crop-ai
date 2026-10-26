import { FormEvent, useEffect, useState } from 'react';
import { AssistantLauncher, PlatformPages } from './PlatformPages';
import type { HazardAssessment } from './HazardAssessments.mjs';
import { CropRiskCard } from './CropRiskCard.mjs';
import { cropAssessmentKey, dedupeBestAssessmentByCrop, uniqueCropsForAssessment } from './cropRiskDisplay.mjs';
import './App.css';

type UserType = 'farmer' | 'gardener';
type User = { id: number; name: string; user_type: UserType };
type Crop = { id: number; crop_name: string; variety?: string; current_stage?: string; status: string; field_id: number };
type CatalogCrop = { crop_id: string; canonical_name: string; aliases: string[]; category: string; knowledge_status: 'FULL' | 'PARTIAL' | 'LIMITED'; verified_hazards?: string[]; verified_stages?: string[]; verified_regions?: string[] };
type Alert = { id: number; title: string; message: string; severity: string; is_read: boolean };
type Farm = { id: number };
type Field = { id: number };
type Weather = { provider: string; configured: boolean; provider_status?: string; provider_http_status?: number|null; provider_error?: string; freshness_status?: 'fresh'|'stale'|'unavailable'|string; cache?: string; latitude?: number; longitude?: number; timezone?: string; forecast_issued_at?: string; retrieved_at?: string; stale?: boolean; cache_age_seconds?: number; temperature?: number; humidity?: number; rainfall?: number; wind_speed?: number; precipitation_probability?: number|null; forecast?: Array<{ date: string; rainfall?: number|null; temperature_max?: number|null; temperature_min?: number|null; precipitation_probability?: number|null }>; hourly_forecast?: Array<{ time:string; rainfall?:number|null; temperature?:number|null; humidity?:number|null; wind_speed?:number|null; wind_gust?:number|null; precipitation_probability?:number|null }>; forecast_resolution?: string; message?: string };
type ModelFactor = { key: string; label: string; score: number; level?: string; tone?: string; weight?: number|null; evidence?: string };
type ModelAssessment = {
  status?: string;
  risk_percent: number | null;
  safe_percent: number | null;
  level?: string;
  tone?: string;
  alert?: boolean;
  watch?: boolean;
  label?: string;
  summary?: string;
  top_factor?: string;
  factors?: ModelFactor[];
  recommendations?: string[];
  confidence?: string;
  confidence_reason?: string;
  profile_source?: string;
  limitations?: string[];
  model?: { name?: string; version?: string; method?: string; is_probability?: boolean };
};
type WeatherRisk = { crop: string; state?: string|null; level: string; score: number | null; status?: string; knowledge_status: string; summary?: string; limitations?: string[]; missing_inputs?: string[]; hazards?: HazardAssessment[]; model_assessment?: ModelAssessment|null; weather_observations?: { current_humidity_percent?: number|null }; expected_rainfall: number|null; risk_window_hours: number|null; risk_resolution?: string; reasons: string[] };
type WeatherSignal = { date?: string; rainfall_mm: number; category: string; title: string; explanation: string; recommended_action: string; source: string; source_url: string };
type WeatherRiskResponse = { location?: string; official_advisory_url?: string; weather: Weather & { latitude: number; longitude: number; forecast?: Array<{ date: string; rainfall?: number|null }> }; weather_signals?: WeatherSignal[]; risks: WeatherRisk[] };
type Place = { id: number; name: string; admin1?: string; admin2?: string; country?: string; latitude: number; longitude: number };
type MainPage = 'crops' | 'risk' | 'diagnose' | 'market' | 'tools';
type IntelligenceCrop = { id: number; crop_name: string; city?: string; district?: string; state?: string; country?: string; latitude?: number; longitude?: number; growth_stage?: string };
type IntelligenceResult = { crop: IntelligenceCrop; weather?: { forecast_issued_at?: string; retrieved_at?: string; timezone?: string; stale?: boolean; freshness_status?: string; cache_age_seconds?: number; provider_status?: string; provider_http_status?: number|null; provider_error?: string; humidity?: number|null; forecast?: Array<{ date: string; rainfall?: number|null; temperature_max?: number|null; temperature_min?: number|null }> }; risk: { overall_risk: string; risk_score: number | null; status?: string; knowledge_status: string; growth_stage?: string; location?: { city?: string; district?: string; state?: string|null; country?: string|null; latitude?: number; longitude?: number }; missing_inputs?: string[]; hazards?: HazardAssessment[]; model_assessment?: ModelAssessment|null; limitations?: string[]; summary: string; analyzed_at?: string; alerts: Array<{ title: string; severity: string; expected_time: string; explanation: string; recommended_actions: string[] }> } };
type CarePlan = { title: string; stage: string; summary: string; today: string[]; watch_for: string[]; next_step: string; context_note: string; safety: string };
type Diagnosis = {
  crop?: string;
  crop_name?: string;
  disease?: string;
  disease_name?: string;
  cure?: string;
  confidence?: number;
  symptoms?: string[] | string;
  treatment?: string;
  prevention?: string;
  recommended_action?: string;
  recommendations?: string[];
  model_status?: string;
  agreement?: boolean;
  possible_cause?: string;
  vision_error?: string;
};

const GROWTH_STAGES = [
  { value: 'germination', label: 'Germination' },
  { value: 'seedling', label: 'Seedling' },
  { value: 'vegetative', label: 'Vegetative' },
  { value: 'tuber initiation', label: 'Potato tuber initiation' },
  { value: 'tuberization', label: 'Potato tuberization' },
  { value: 'bulb development', label: 'Onion bulb development' },
  { value: 'flowering', label: 'Flowering' },
  { value: 'fruiting', label: 'Fruiting / podding' },
  { value: 'grain filling', label: 'Grain filling' },
  { value: 'maturity', label: 'Maturity' },
  { value: 'harvest', label: 'Harvest' },
];

const API = '/api';

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? 'Request failed');
  return data;
}

function chatText(value: string): string {
  return value
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*]\s+/gm, '• ');
}

function unavailableCropAssessment(crop: IntelligenceCrop, reason: string): IntelligenceResult {
  return {
    crop,
    risk: {
      overall_risk: 'UNAVAILABLE', risk_score: null, status: 'unavailable', knowledge_status: 'LIMITED',
      growth_stage: crop.growth_stage,
      location: { city: crop.city, district: crop.district, state: crop.state, latitude: crop.latitude, longitude: crop.longitude },
      hazards: [], limitations: [reason], summary: `Assessment unavailable: ${reason}`,
      alerts: [],
    },
  };
}

async function fetchLocationWeather(latitude: number, longitude: number): Promise<Weather> {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    current: 'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m',
    daily: 'precipitation_sum,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
    hourly: 'precipitation,temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,precipitation_probability',
    forecast_days: '7',
    forecast_hours: '49',
    past_hours: '0',
    timezone: 'auto',
    temperature_unit: 'celsius',
    wind_speed_unit: 'kmh',
    precipitation_unit: 'mm',
  });
  let payload: Record<string, any>;
  try {
    const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params}`);
    if (!response.ok) throw new Error(`Weather provider returned HTTP ${response.status}.`);
    payload = await response.json();
  } catch (browserError) {
    try {
      const serverWeather = await api<Weather>(`/weather?${params}`);
      const currentHour = serverWeather.forecast_issued_at?.slice(0, 13);
      return {
        ...serverWeather,
        hourly_forecast: serverWeather.hourly_forecast?.filter((hour) => !currentHour || hour.time.slice(0, 13) > currentHour).slice(0, 48),
      };
    } catch (serverError) {
      const reason = serverError instanceof Error ? serverError.message : String(browserError);
      throw new Error(`Weather could not be loaded from the browser or server provider. ${reason}`);
    }
  }
  const current = payload.current ?? {};
  const daily = payload.daily ?? {};
  const forecast = (daily.time ?? []).map((date: string, index: number) => ({
    date,
    rainfall: daily.precipitation_sum?.[index] ?? null,
    temperature_max: daily.temperature_2m_max?.[index],
    temperature_min: daily.temperature_2m_min?.[index],
    precipitation_probability: daily.precipitation_probability_max?.[index] ?? null,
  }));
  const hourly = payload.hourly ?? {};
  const hourlyForecast = (hourly.time ?? []).map((time: string, index: number) => ({
    time,
    rainfall: hourly.precipitation?.[index] ?? null,
    temperature: hourly.temperature_2m?.[index] ?? null,
    humidity: hourly.relative_humidity_2m?.[index] ?? null,
    wind_speed: hourly.wind_speed_10m?.[index] ?? null,
    wind_gust: hourly.wind_gusts_10m?.[index] ?? null,
    precipitation_probability: hourly.precipitation_probability?.[index] ?? null,
  })).filter((hour: { time: string }) => !current.time || hour.time.slice(0, 13) > String(current.time).slice(0, 13)).slice(0, 48);
  const dailyProbabilities = forecast.map((day: { precipitation_probability?: number|null }) => day.precipitation_probability)
    .filter((value: number|null|undefined): value is number => typeof value === 'number' && Number.isFinite(value));
  return {
    provider: 'open-meteo',
    configured: true,
    latitude: payload.latitude ?? latitude,
    longitude: payload.longitude ?? longitude,
    timezone: payload.timezone,
    forecast_issued_at: current.time,
    retrieved_at: new Date().toISOString(),
    temperature: current.temperature_2m,
    humidity: current.relative_humidity_2m,
    rainfall: current.precipitation,
    wind_speed: current.wind_speed_10m,
    precipitation_probability: dailyProbabilities.length ? Math.max(...dailyProbabilities) : null,
    forecast,
    hourly_forecast: hourlyForecast,
    forecast_resolution: 'hourly',
  };
}

function forecastForSavedCrop(crop: IntelligenceCrop, forecast?: Weather): Weather | undefined {
  if (!forecast || forecast.provider !== 'open-meteo' || forecast.stale || !Number.isFinite(forecast.latitude) || !Number.isFinite(forecast.longitude)
    || !Number.isFinite(crop.latitude) || !Number.isFinite(crop.longitude)
    || Math.abs(forecast.latitude! - crop.latitude!) > 0.1 || Math.abs(forecast.longitude! - crop.longitude!) > 0.1) return undefined;
  return forecast;
}

function analyzeSavedCrop(crop: IntelligenceCrop, forecast?: Weather): Promise<IntelligenceResult> {
  const matchingForecast = forecastForSavedCrop(crop, forecast);
  return api<IntelligenceResult>(`/crops/${crop.id}/analyze`, {
    method: 'POST', body: JSON.stringify(matchingForecast ? { weather: matchingForecast } : {}),
  });
}

function AppFooter() {
  return (
    <footer className="app-footer" aria-label="Site footer">
      <div className="footer-grid">
        <div className="footer-brand">
          <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M25.5 5.5C16 6 8 9.1 7.5 17.2c-.2 3.3 2 5.3 5 5.3 8.8 0 12.1-8.8 13-17Z"/><path d="M5.5 27c3.2-6.4 8.3-10.8 16-14.7"/></svg></span>
          <strong>Kheti Lens</strong>
          <span className="brand-chip">beta</span>
        </div>
        <p className="footer-tagline">Crop health, forecast risk, and mandi intelligence — one calm workspace for Indian fields and gardens.</p>
        <nav className="footer-links" aria-label="Official data sources">
          <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Weather · Open-METEO</a>
          <a href="https://www.data.gov.in/" target="_blank" rel="noreferrer">Mandi prices · AGMARKNET</a>
          <a href="https://mausam.imd.gov.in/" target="_blank" rel="noreferrer">Advisories · IMD</a>
          <a href="https://www.india.gov.in/topics/agriculture" target="_blank" rel="noreferrer">Schemes · india.gov.in</a>
        </nav>
      </div>
      <div className="footer-bottom">
        <small>© 2026 Kheti Lens · Built for Indian farmers and gardeners</small>
        <small>Decision support only — confirm critical actions with your local agricultural university or Krishi Vigyan Kendra.</small>
      </div>
    </footer>
  );
}

export default function App() {
  const [userType, setUserType] = useState<UserType | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [fieldId, setFieldId] = useState<number | null>(null);
  const [authMode, setAuthMode] = useState<'register' | 'login'>('login');
  const [authBusy, setAuthBusy] = useState(false);
  const [crops, setCrops] = useState<Crop[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [cropName, setCropName] = useState('');
  const [growthStage, setGrowthStage] = useState('');
  const [cropVariety, setCropVariety] = useState('');
  const [cropLocality, setCropLocality] = useState('');
  const [cropState, setCropState] = useState('');
  const [savedCropStates, setSavedCropStates] = useState<Record<number, string>>({});
  const [cropCountry, setCropCountry] = useState('');
  const [cropDistrict, setCropDistrict] = useState('');
  const [cropSoilType, setCropSoilType] = useState('');
  const [cropDrainage, setCropDrainage] = useState('');
  const [cropIrrigation, setCropIrrigation] = useState('');
  const [cropCatalog, setCropCatalog] = useState<CatalogCrop[]>([]);
  const [question, setQuestion] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [status, setStatus] = useState('');
  const [weather, setWeather] = useState<Weather | null>(null);
  const [weatherError, setWeatherError] = useState('');
  const [weatherLocationLabel, setWeatherLocationLabel] = useState('');
  const [locationStatus, setLocationStatus] = useState('Location not checked');
  const [locationQuery, setLocationQuery] = useState('');
  const [locationMatches, setLocationMatches] = useState<Place[]>([]);
  const [selectedLocationId, setSelectedLocationId] = useState('');
  const [manualLatitude, setManualLatitude] = useState('');
  const [manualLongitude, setManualLongitude] = useState('');
  const [weatherRisks, setWeatherRisks] = useState<WeatherRisk[]>([]);
  const [weatherSignals, setWeatherSignals] = useState<WeatherSignal[]>([]);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState('');
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [scanBusy, setScanBusy] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [carePlan, setCarePlan] = useState<CarePlan | null>(null);
  const [coordinates, setCoordinates] = useState<{ latitude: number; longitude: number } | null>(null);
  const [intelligenceCrops, setIntelligenceCrops] = useState<IntelligenceCrop[]>([]);
  const [intelligenceResults, setIntelligenceResults] = useState<IntelligenceResult[]>([]);
  const [savedRiskBusy, setSavedRiskBusy] = useState(false);
  const [activePage, setActivePage] = useState<MainPage>('crops');
  const [assistantLanguage, setAssistantLanguage] = useState<'en' | 'hi' | 'hinglish'>('en');

  // Full-bleed header/footer: keep the viewport width CSS var in sync.
  // clientWidth excludes the scrollbar, so nothing overflows sideways.
  useEffect(() => {
    const syncViewport = () => {
      document.documentElement.style.setProperty('--vw', `${document.documentElement.clientWidth}px`);
    };
    syncViewport();
    window.addEventListener('resize', syncViewport);
    return () => window.removeEventListener('resize', syncViewport);
  }, []);

  useEffect(() => {
    if (!imageFile) { setImagePreview(''); return; }
    const objectUrl = URL.createObjectURL(imageFile);
    setImagePreview(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [imageFile]);

  useEffect(() => {
    api<{ items: CatalogCrop[] }>('/crop-catalog').then((result) => setCropCatalog(result.items)).catch(() => undefined);
    api<{ authenticated: boolean; user?: User }>('/auth/me').then((result) => {
      if (result.authenticated && result.user) {
        setUser(result.user);
        setUserType(result.user.user_type);
      }
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!user) return;
    api<{preferred_language?: 'en'|'hi'|'hinglish'}>('/farmer/profile').then((profile) => setAssistantLanguage(profile.preferred_language || 'en')).catch(() => undefined);
    Promise.all([api<{ items: Alert[] }>('/alerts'), api<{ items: Farm[] }>(`/users/${user.id}/farms`), api<{ items: IntelligenceCrop[] }>('/crops')]).then(async ([alertData, farmData, intelligenceData]) => {
      setAlerts(alertData.items);
      setIntelligenceCrops(intelligenceData.items);
      const assessmentCrops = uniqueCropsForAssessment(intelligenceData.items);
      if (assessmentCrops.length) {
        setSavedRiskBusy(true);
        const checks = await Promise.allSettled(assessmentCrops.map((crop) => analyzeSavedCrop(crop)));
        const results = checks.map((check, index) => check.status === 'fulfilled'
          ? check.value
          : unavailableCropAssessment(assessmentCrops[index], check.reason instanceof Error ? check.reason.message : 'Weather data could not be loaded.'));
        const successful = checks.filter((check) => check.status === 'fulfilled').length;
        setIntelligenceResults(results);
        setSavedRiskBusy(false);
        try {
          setAlerts((await api<{ items: Alert[] }>('/alerts')).items);
        } catch {
          // The initial alert list remains visible if refreshing it after assessment fails.
        }
        const failed = checks.length - successful;
        if (failed) setStatus(`${successful} saved crop(s) assessed; ${failed} assessment(s) are unavailable until weather data can be loaded.`);
      }
      const farm = farmData.items[0];
      if (!farm) return;
      const fields = await api<{ items: Field[] }>(`/farms/${farm.id}/fields`);
      const field = fields.items[0];
      if (!field) return;
      setFieldId(field.id);
      const cropData = await api<{ items: Crop[] }>(`/fields/${field.id}/crops`);
      setCrops(cropData.items);
    }).catch((error: Error) => setStatus(error.message));
  }, [user]);

  async function reassessSavedCropsWithForecast(forecast: Weather) {
    const targets = uniqueCropsForAssessment(intelligenceCrops);
    if (!targets.length) return;
    const checks = await Promise.allSettled(targets.map((crop) => analyzeSavedCrop(crop, forecast)));
    const results = checks.map((check, index) => check.status === 'fulfilled'
      ? check.value
      : unavailableCropAssessment(targets[index], check.reason instanceof Error ? check.reason.message : 'Weather data could not be loaded.'));
    setIntelligenceResults((current) => {
      const byCrop = new Map(current.map((item) => [item.crop.id, item]));
      results.forEach((item) => byCrop.set(item.crop.id, item));
      return [...byCrop.values()];
    });
  }

  async function loadWeatherAt(latitude: number, longitude: number, label: string, accuracy?: number) {
    setLocationStatus(`Loading local weather for ${label}…`);
    setWeatherError('');
    try {
      const localWeather = await fetchLocationWeather(latitude, longitude);
      setWeather(localWeather);
      setWeatherLocationLabel(label);
      setCoordinates({ latitude, longitude });
      setLocationStatus(`${label} · ${latitude.toFixed(3)}, ${longitude.toFixed(3)}`);
      if (!user) return;
      try {
        await api('/farmer/profile', { method: 'PUT', body: JSON.stringify({ location_consent: true }) });
        await api('/location', { method: 'POST', body: JSON.stringify({ latitude, longitude, location_name: label, accuracy }) });
        const result = await api<WeatherRiskResponse>('/weather/risk', {
          method: 'POST',
          body: JSON.stringify({ latitude, longitude, accuracy, location: label, weather: localWeather }),
        });
        setWeather(result.weather);
        setWeatherRisks(result.risks);
        setWeatherSignals(result.weather_signals ?? []);
        await reassessSavedCropsWithForecast(localWeather);
        setAlerts((await api<{ items: Alert[] }>('/alerts')).items);
      } catch (error) {
        setWeatherError(`Local weather loaded. Saving location and crop risks failed: ${(error as Error).message}`);
      }
    } catch (error) {
      setWeatherError((error as Error).message);
      setLocationStatus(`Could not load weather for ${label}. Try another place or enter coordinates.`);
    }
  }

  async function requestWeatherRisk() {
    setWeatherError('');
    if (!window.isSecureContext) {
      setLocationStatus('Browser location needs HTTPS or localhost. Search for a place or enter coordinates below instead.');
      return;
    }
    if (!navigator.geolocation) {
      setLocationStatus('Browser location is unavailable in this browser. Search for a place or enter coordinates below.');
      return;
    }
    setLocationStatus('Waiting for browser location permission…');
    navigator.geolocation.getCurrentPosition(async (position) => {
      const { latitude, longitude, accuracy } = position.coords;
      setCropLocality('');setCropState('');setCropDistrict('');
      setCropCountry('');
      await loadWeatherAt(latitude, longitude, 'Current device location', accuracy);
    }, (error) => {
      if (error.code === 1) {
        setLocationStatus('Location permission is blocked for this site. Allow location from the browser site settings, then try again — or search a place / enter coordinates below.');
        setWeatherError('Browser location was denied. Search or coordinates still work.');
      } else if (error.code === 3) {
        setLocationStatus('The browser took too long to find your location. Try again, search a place, or enter coordinates.');
      } else {
        setLocationStatus('The browser could not determine your location. Search a place or enter coordinates below.');
      }
    }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 15 * 60 * 1000 });
  }

  async function useManualCoordinates(event: FormEvent) {
    event.preventDefault();
    const latitude = Number(manualLatitude.trim());
    const longitude = Number(manualLongitude.trim());
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
      setLocationStatus('Enter a valid latitude (-90 to 90) and longitude (-180 to 180).');
      return;
    }
    setCropCountry('');setCropState('');setCropDistrict('');setCropLocality('');
    await loadWeatherAt(latitude, longitude, `Coordinates ${latitude.toFixed(3)}, ${longitude.toFixed(3)}`);
  }

  async function searchLocation(event: FormEvent) {
    event.preventDefault();
    if (!locationQuery.trim()) return;
    setWeatherError('');
    setLocationStatus('Searching Indian locations…');
    try {
      const params = new URLSearchParams({ name: locationQuery.trim(), countryCode: 'IN', count: '8', language: assistantLanguage === 'hi' ? 'hi' : 'en', format: 'json' });
      const response = await fetch(`https://geocoding-api.open-meteo.com/v1/search?${params}`);
      if (!response.ok) throw new Error(`Location search returned HTTP ${response.status}.`);
      const payload = await response.json();
      const places = (payload.results ?? []) as Place[];
      setLocationMatches(places);
      setSelectedLocationId(places[0] ? String(places[0].id) : '');
      setLocationStatus(places.length ? `${places.length} matching locations found. Select the correct district or state.` : 'No matching Indian locations found. Try a nearby town or district name.');
      if (!places.length) setWeatherError('No matching Indian locations found.');
    } catch (error) {
      setLocationMatches([]);
      setSelectedLocationId('');
      setLocationStatus('Location search is unavailable right now. You can enter latitude and longitude below.');
      setWeatherError((error as Error).message);
    }
  }

  async function useSelectedLocation() {
    const place = locationMatches.find((item) => String(item.id) === selectedLocationId);
    if (!place) return;
    const locationName = [place.name, place.admin2, place.admin1].filter(Boolean).join(', ');
    setCropLocality(place.name);
    setCropState(place.admin1 || '');
    setCropDistrict(place.admin2 || '');
    setCropCountry(place.country || '');
    await loadWeatherAt(place.latitude, place.longitude, locationName);
  }

  async function createProfile(event: FormEvent) {
    event.preventDefault();
    if (!userType || (authMode === 'register' && !name.trim())) return;
    setAuthBusy(true);
    try {
      const created = await api<User>(authMode === 'register' ? '/auth/register' : '/auth/login', { method: 'POST', body: JSON.stringify(authMode === 'register' ? { name, email, password, user_type: userType } : { email, password }) });
      setUser(created);
      setUserType(created.user_type);
      if (authMode === 'register') {
        const farm = await api<Farm>('/farms', { method: 'POST', body: JSON.stringify({ user_id: created.id, name: userType === 'farmer' ? 'My farm' : 'My garden' }) });
        const field = await api<Field>('/fields', { method: 'POST', body: JSON.stringify({ farm_id: farm.id, name: userType === 'farmer' ? 'Field 1' : 'Growing space' }) });
        setFieldId(field.id);
      }
      setStatus('Profile ready. Add your first crop.');
    } catch (error) {
      setStatus((error as Error).message);
    } finally {
      setAuthBusy(false);
    }
  }

  function selectScanImage(file?: File) {
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setStatus('Choose a JPG, PNG, or WEBP image.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setStatus('This image is over the 10 MB upload limit. Choose a smaller image.');
      return;
    }
    setStatus('');
    setImageFile(file);
    setDiagnosis(null);
  }

  async function addCrop(event: FormEvent) {
    event.preventDefault();
    if (!cropName.trim()) return;
    if (!fieldId) {
      setStatus('A field is required before adding a crop.');
      return;
    }
    try {
      const crop = await api<Crop>('/crops', { method: 'POST', body: JSON.stringify({ field_id: fieldId, crop_name: cropName, variety: cropVariety || undefined, current_stage: growthStage || undefined, status: 'active' }) });
      setCrops((current) => [crop, ...current]);
      if (coordinates) {
        const intelligenceCrop = await api<IntelligenceCrop>('/crops', { method: 'POST', body: JSON.stringify({ user_id: user?.id, crop_name: cropName, variety: cropVariety || undefined, city: cropLocality || undefined, district: cropDistrict || undefined, state: cropState || undefined, country: cropCountry || null, latitude: coordinates.latitude, longitude: coordinates.longitude, soil_type: cropSoilType || undefined, drainage_condition: cropDrainage || undefined, irrigation_availability: cropIrrigation || undefined, mode: userType, growth_stage: growthStage || undefined }) });
        setIntelligenceCrops((current) => [intelligenceCrop, ...current]);
        const analysis = await analyzeSavedCrop(intelligenceCrop, weather || undefined);
        setIntelligenceResults((current) => [analysis, ...current.filter((item) => item.crop.id !== intelligenceCrop.id)]);
        setAlerts((await api<{ items: Alert[] }>('/alerts')).items);
      } else setStatus(`${crop.crop_name} was saved. Select a weather location before it can be added to crop-specific forecast alerts.`);
      setCropName('');
      setCropVariety('');setCropLocality('');setCropState('');setCropCountry('');setCropDistrict('');setCropSoilType('');setCropDrainage('');setCropIrrigation('');
      if (coordinates) setStatus(`${crop.crop_name} added to your growing list and assessed against available verified rules.`);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  async function assessSavedCrops() {
    if (!intelligenceCrops.length) {
      setStatus('Add a saved crop with a location before checking crop alerts.');
      return;
    }
    setSavedRiskBusy(true);
    const targets = uniqueCropsForAssessment(intelligenceCrops);
    const results = await Promise.allSettled(targets.map((crop) => analyzeSavedCrop(crop, weather || undefined)));
    const checked = results.map((result, index) => result.status === 'fulfilled'
      ? result.value
      : unavailableCropAssessment(targets[index], result.reason instanceof Error ? result.reason.message : 'Weather data could not be loaded.'));
    const successful = results.filter((result) => result.status === 'fulfilled').length;
    setIntelligenceResults((current) => {
      const byCrop = new Map(current.map((item) => [item.crop.id, item]));
      checked.forEach((item) => byCrop.set(item.crop.id, item));
      return [...byCrop.values()];
    });
    try {
      setAlerts((await api<{ items: Alert[] }>('/alerts')).items);
    } catch (error) {
      setStatus(`Crop checks finished, but in-app alerts could not be refreshed: ${(error as Error).message}`);
    }
    const failed = results.length - successful;
    if (failed) setStatus(`${successful} saved crop(s) checked; ${failed} assessment(s) are unavailable until weather data can be loaded.`);
    else setStatus(`${successful} saved crop(s) checked. Any new forecast alerts are listed below.`);
    setSavedRiskBusy(false);
  }

  async function updateSavedCropStage(crop: IntelligenceCrop, stage: string) {
    try {
      const updated = await api<IntelligenceCrop>(`/crops/${crop.id}/context`, {
        method: 'PATCH', body: JSON.stringify({ growth_stage: stage || null }),
      });
      setIntelligenceCrops((current) => current.map((item) => item.id === crop.id ? updated : item));
      const analysis = await analyzeSavedCrop(crop, weather || undefined);
      setIntelligenceResults((current) => [...current.filter((item) => item.crop.id !== crop.id), analysis]);
      setAlerts((await api<{ items: Alert[] }>('/alerts')).items);
      setStatus(`${crop.crop_name} forecast assessment updated for ${stage || 'an unspecified stage'}.`);
    } catch (error) {
      setStatus(`Could not update this crop assessment: ${(error as Error).message}`);
    }
  }

  async function updateSavedCropState(crop: IntelligenceCrop) {
    const state = (savedCropStates[crop.id] ?? crop.state ?? '').trim();
    try {
      const updated = await api<IntelligenceCrop>(`/crops/${crop.id}/context`, {
        method: 'PATCH', body: JSON.stringify({ state: state || null }),
      });
      setIntelligenceCrops((current) => current.map((item) => item.id === crop.id ? updated : item));
      const analysis = await analyzeSavedCrop(crop, weather || undefined);
      setIntelligenceResults((current) => [...current.filter((item) => item.crop.id !== crop.id), analysis]);
      setStatus(`${crop.crop_name} location context updated${state ? ` for ${state}` : ''}.`);
    } catch (error) {
      setStatus(`Could not update this crop location context: ${(error as Error).message}`);
    }
  }

  async function updateCropStage(crop: Crop, stage: string) {
    try {
      const updated = await api<Crop>(`/crops/${crop.id}`, { method: 'PATCH', body: JSON.stringify({ current_stage: stage || null }) });
      setCrops((current) => current.map((item) => item.id === crop.id ? updated : item));
      setStatus(`${crop.crop_name} stage updated. Refresh weather risk to reassess it.`);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  async function deleteCrop(crop: Crop) {
    if (!window.confirm(`Remove ${crop.crop_name} from this growing list?`)) return;
    try {
      await api(`/crops/${crop.id}`, { method: 'DELETE' });
      setCrops((current) => current.filter((item) => item.id !== crop.id));
      setStatus(`${crop.crop_name} was removed.`);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  async function showCarePlan(crop: Crop) {
    try {
      const plan = await api<CarePlan>(`/crops/${crop.id}/care-plan?user_type=${userType}`);
      setCarePlan(plan);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  async function askAgricultureAssistant() {
    const message = question.trim();
    if (!message || chatBusy) return;
    setChatBusy(true);
    const conversation = chatMessages.slice(-8);
    setChatMessages([...chatMessages, { role: 'user', content: message }]);
    setQuestion('');
    try {
      const data = await api<{ answer: string }>('/chat', {
        method: 'POST',
        body: JSON.stringify({
          message,
          language: assistantLanguage,
          conversation,
          diagnosis_context: diagnosis ? {
            crop: diagnosis.crop_name || diagnosis.crop,
            disease: diagnosis.disease_name || diagnosis.disease,
            cure: diagnosis.cure || diagnosis.treatment,
            symptoms: diagnosis.symptoms,
            model_status: diagnosis.model_status,
          } : undefined,
        }),
      });
      setChatMessages((current) => [...current, { role: 'assistant', content: data.answer }]);
      if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(data.answer.replace(/[*#`]/g, ''));
        utterance.lang = assistantLanguage === 'en' ? 'en-IN' : 'hi-IN';
        window.speechSynthesis.speak(utterance);
      }
    } catch (error) {
      setStatus((error as Error).message);
      setChatMessages((current) => [...current, { role: 'assistant', content: `I could not answer that just now. ${(error as Error).message}` }]);
    } finally {
      setChatBusy(false);
    }
  }

  function startAssistantVoice() {
    const speech = window as typeof window & { SpeechRecognition?: new () => { lang: string; onresult: ((event: SpeechRecognitionEvent) => void) | null; onerror: (() => void) | null; start: () => void }; webkitSpeechRecognition?: new () => { lang: string; onresult: ((event: SpeechRecognitionEvent) => void) | null; onerror: (() => void) | null; start: () => void } };
    const Recognition = speech.SpeechRecognition || speech.webkitSpeechRecognition;
    if (!Recognition) { setStatus('Voice input is not supported in this browser. Type your question instead.'); return; }
    const recognition = new Recognition();
    recognition.lang = assistantLanguage === 'en' ? 'en-IN' : 'hi-IN';
    recognition.onresult = (event) => setQuestion(event.results[0][0].transcript);
    recognition.onerror = () => setStatus('Microphone input failed. Check browser permission or type your question.');
    recognition.start();
  }

  async function logout() {
    try { await api('/auth/logout', { method: 'POST' }); } catch { /* Clear local session view even if the server is unreachable. */ }
    setUser(null); setUserType(null); setCrops([]); setAlerts([]); setIntelligenceCrops([]); setIntelligenceResults([]); setFieldId(null);
    setWeather(null); setWeatherRisks([]); setWeatherSignals([]); setCoordinates(null); setWeatherError(''); setLocationStatus('Location not checked');
    setLocationQuery(''); setLocationMatches([]); setSelectedLocationId('');
  }

  async function scanPlant(event: FormEvent) {
    event.preventDefault();
    if (!imageFile) {
      setStatus('Choose a JPG, PNG, or WEBP crop image first.');
      return;
    }
    const form = new FormData();
    form.append('image', imageFile);
    if (scanBusy) return;
    setScanBusy(true);
    setDiagnosis(null);
    setChatMessages([]);
    try {
      const response = await fetch('/api/predict', { method: 'POST', body: form, credentials: 'include' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? 'Disease scan failed.');
      setDiagnosis(data);
      setStatus('Scan complete. Treat this as decision support, not certainty.');
    } catch (error) {
      setStatus((error as Error).message);
    } finally {
      setScanBusy(false);
    }
  }

  const locationControls = (prefix: string) => (
    <div className="location-search">
      <form onSubmit={searchLocation}>
        <label htmlFor={`${prefix}-location-query`}>Search an Indian town, city, or district</label>
        <div className="location-search-row"><input id={`${prefix}-location-query`} value={locationQuery} onChange={(event) => setLocationQuery(event.target.value)} placeholder="e.g. Nashik, Maharashtra" /><button className="location-button" type="submit">Search</button></div>
      </form>
      {locationMatches.length > 0 && <div className="location-search-row"><select aria-label="Choose the matching location" value={selectedLocationId} onChange={(event) => setSelectedLocationId(event.target.value)}>{locationMatches.map((place) => <option key={place.id} value={place.id}>{[place.name, place.admin2, place.admin1].filter(Boolean).join(', ')}</option>)}</select><button className="location-button" type="button" onClick={useSelectedLocation}>Use selected place</button></div>}
      <form onSubmit={useManualCoordinates} className="manual-location">
        <label htmlFor={`${prefix}-manual-latitude`}>Or enter latitude and longitude</label>
        <div className="location-search-row">
          <input id={`${prefix}-manual-latitude`} inputMode="decimal" value={manualLatitude} onChange={(event) => setManualLatitude(event.target.value)} placeholder="Latitude, e.g. 28.496" aria-label="Latitude" />
          <input inputMode="decimal" value={manualLongitude} onChange={(event) => setManualLongitude(event.target.value)} placeholder="Longitude, e.g. 77.536" aria-label="Longitude" />
          <button className="location-button" type="submit">Use coordinates</button>
        </div>
      </form>
      <small className="location-status">Find coordinates by right-clicking your field in Google Maps. Search and coordinates work even when the browser blocks location.</small>
    </div>
  );

  if (!userType) {
    return (
      <main className="welcome-shell">
        <section className="welcome-copy">
          <div className="welcome-brand"><span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M25.5 5.5C16 6 8 9.1 7.5 17.2c-.2 3.3 2 5.3 5 5.3 8.8 0 12.1-8.8 13-17Z"/><path d="M5.5 27c3.2-6.4 8.3-10.8 16-14.7"/></svg></span><span>Kheti Lens</span><span className="brand-chip">beta</span></div>
          <div className="welcome-body">
            <span className="kicker">AGRI INTELLIGENCE / INDIA</span>
            <h1>Grow with <em>clarity.</em></h1>
            <p>Bring crop health, field conditions, market observations, and practical decisions into one considered workspace.</p>
            <div className="welcome-chips" aria-label="What Kheti Lens helps with"><span>Forecast-led crop risk</span><span>Disease scans</span><span>Mandi prices</span></div>
            <div className="welcome-collage">
              <figure className="welcome-photo welcome-photo--main"><img src="/brand-field.svg" alt="Illustrated Indian farmland at golden hour" /></figure>
              <figure className="welcome-photo welcome-photo--small"><img src="/brand-leaf.svg" alt="Illustrated close-up of healthy crop leaves" /></figure>
              <span className="welcome-sticker"><i aria-hidden="true" />Live weather · crop-specific risk</span>
            </div>
          </div>
          <div className="welcome-caption"><span>FIELD NOTES / INDIA</span><span>Better informed, season by season</span></div>
        </section>
        <section className="choice-panel">
          <div className="choice-panel__top">
            <span className="eyebrow">START WITH YOUR CONTEXT</span>
            <h2>Choose your workspace</h2>
            <p className="auth-intro">Start with the growing space you want to care for.</p>
          </div>
          <div className="choice-list">
            <button className="choice farmer" onClick={() => setUserType('farmer')}><span className="choice-index">01</span><span><strong>Farm</strong><small>Fields, seasons, and crop risk</small></span><span className="choice-arrow" aria-hidden="true">↗</span></button>
            <button className="choice gardener" onClick={() => setUserType('gardener')}><span className="choice-index">02</span><span><strong>Home garden</strong><small>Plants, care routines, and pests</small></span><span className="choice-arrow" aria-hidden="true">↗</span></button>
          </div>
          <div className="choice-footnote" aria-label="Kheti Lens at a glance">
            <div><strong>188</strong><span>crops mapped</span></div>
            <div><strong>Live</strong><span>local forecast</span></div>
            <div><strong>1</strong><span>calm workspace</span></div>
          </div>
          <p className="choice-privacy">Weather and location search unlock inside your workspace after you choose.</p>
        </section>
        <AppFooter />
      </main>
    );
  }

  if (!user) {
    return (
      <main className="profile-shell">
        <aside className="auth-visual">
          <img className="auth-visual__image" src="/brand-garden.svg" alt="Illustrated home garden with leafy plants and ripening tomatoes" />
          <div className="auth-visual__scrim" aria-hidden="true" />
          <div className="auth-visual__content">
            <div className="welcome-brand welcome-brand--light"><span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M25.5 5.5C16 6 8 9.1 7.5 17.2c-.2 3.3 2 5.3 5 5.3 8.8 0 12.1-8.8 13-17Z"/><path d="M5.5 27c3.2-6.4 8.3-10.8 16-14.7"/></svg></span><span>Kheti Lens</span><span className="brand-chip">beta</span></div>
            <div className="auth-visual__message">
              <span className="kicker">YOUR GROWING SPACE</span>
              <h2>Every season starts with a closer look.</h2>
              <p>Track crops, read the forecast, and act on what matters — without the noise.</p>
              <div className="auth-visual__chips"><span>Forecast</span><span>Care</span><span>Market</span></div>
            </div>
          </div>
        </aside>
        <section className="profile-card">
          <button className="back-link" onClick={() => setUserType(null)}>← Change workspace</button>
          <span className="eyebrow">{userType === 'farmer' ? 'FARMER PROFILE' : 'GARDEN PROFILE'}</span>
          <h1>{authMode === 'register' ? 'Let’s set up your workspace.' : 'Welcome back.'}</h1>
          <p>{authMode === 'register' ? 'Your profile gives crop and alert features a place to belong.' : 'Sign in to continue tracking your crops.'}</p>
          <form onSubmit={createProfile}>
            {authMode === 'register' && <label>Your name<input required autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Ananya Sharma" /></label>}
            <label>Email<input required autoComplete="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
            <label>Password<input required minLength={8} autoComplete={authMode === 'register' ? 'new-password' : 'current-password'} type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" /></label>
            <button className="primary" type="submit" disabled={authBusy}>{authBusy ? 'Preparing workspace...' : authMode === 'register' ? 'Create account' : 'Sign in'}</button>
          </form>
          <button className="quiet auth-switch" onClick={() => setAuthMode(authMode === 'register' ? 'login' : 'register')}>{authMode === 'register' ? 'Already have an account? Sign in' : 'Need an account? Register'}</button>
          {status && <p className="notice">{status}</p>}
          <p className="auth-inside-note">Location search and live weather are inside your workspace after sign-in.</p>
        </section>
        <AppFooter />
      </main>
    );
  }

  const pageTabs: Array<[MainPage, string]> = [
    ['crops', 'My crops'], ['risk', 'Weather & risk'],
    ['diagnose', 'Diagnose & Ask Kheti'], ['market', 'Mandi Intelligence'], ['tools', 'Farm tools'],
  ];
  const uniqueWeatherRisks = dedupeBestAssessmentByCrop(weatherRisks, (risk) => risk.crop, (risk) => risk.status);
  const uniqueIntelligenceResults = dedupeBestAssessmentByCrop(intelligenceResults, (item) => item.crop.crop_name, (item) => item.risk.status);
  const weatherRiskNames = new Set(uniqueWeatherRisks.map((risk) => cropAssessmentKey(risk.crop)));
  const usableWeatherRiskNames = new Set(uniqueWeatherRisks.filter((risk) => risk.status !== 'unavailable').map((risk) => cropAssessmentKey(risk.crop)));
  const usableIntelligenceNames = new Set(uniqueIntelligenceResults.filter((item) => item.risk.status !== 'unavailable').map((item) => cropAssessmentKey(item.crop.crop_name)));
  const microphoneIcon = <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="2.5" width="6" height="12" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V22m-4 0h8"/></svg>;

  return (
    <main className="app-shell">
      <div className="sticky-shell">
      <header className="topbar"><div className="brand"><span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M25.5 5.5C16 6 8 9.1 7.5 17.2c-.2 3.3 2 5.3 5 5.3 8.8 0 12.1-8.8 13-17Z"/><path d="M5.5 27c3.2-6.4 8.3-10.8 16-14.7"/></svg></span><span>Kheti Lens</span><span className="brand-chip">beta</span></div><span className="mode-label">{userType === 'farmer' ? 'Farm workspace' : 'Home garden workspace'}</span><span className="user-chip" aria-label={`Signed in as ${user.name}`}>{user.name.slice(0, 1).toUpperCase()}</span><button className="quiet" onClick={logout}>Sign out</button></header>
      <nav className="app-page-nav" aria-label="Main sections">
        {pageTabs.map(([page, label], index) => <button key={page} className={activePage === page ? 'selected' : ''} aria-current={activePage === page ? 'page' : undefined} onClick={() => setActivePage(page)}><span className="nav-index">0{index + 1}</span>{label}</button>)}
      </nav>
      </div>
      {activePage !== 'tools' && <section className="page-intro"><div><span className="eyebrow">{user.name.toUpperCase()}</span><h1>{activePage === 'crops' ? 'Your crops and plants' : activePage === 'risk' ? 'Weather and crop risk' : activePage === 'diagnose' ? 'Diagnose a crop and ask for help' : 'Mandi price intelligence'}</h1><p>{activePage === 'market' ? 'Compare reported mandi prices and estimate the gross value of your harvest.' : 'Decision support for your growing space. Confirm uncertain actions with local agricultural experts.'}</p></div>{activePage !== 'diagnose' && activePage !== 'market' && <div className="weather-card"><span>LOCAL WEATHER</span>{weather ? <><strong>{weather.temperature ?? '--'}°</strong><p>{weather.humidity ?? '--'}% humidity · {weather.rainfall ?? '--'} mm rain · {weather.wind_speed ?? '--'} km/h wind</p><small>{weatherLocationLabel || "Selected coordinates"} | Timezone: {weather.timezone || "provider local time"}</small></> : <p>{weatherError || 'Allow location access or search for a town to load local weather.'}</p>}<button className="location-button" onClick={requestWeatherRisk}>{weather ? 'Refresh location risk' : 'Use my location for weather'}</button>{activePage !== 'risk' && locationControls('intro')}{locationStatus && <small className="location-status">{locationStatus}</small>}</div>}</section>}

      {activePage === 'crops' && <section className="page-card">
        <div className="section-heading"><div><span className="eyebrow">GROWING LIST</span><h2>My crops and plants</h2></div><span className="count">{crops.length} tracked</span></div>
        {crops.length === 0 ? <div className="empty-state"><strong>{userType === 'farmer' ? 'Your first crop starts here.' : 'Your first plant starts here.'}</strong><p>Add a crop or plant to track it here.</p></div> : crops.map((crop) => <article className="crop-card" key={crop.id}><div><span className="crop-icon">✳</span><div><h3>{crop.crop_name}</h3><p>{crop.variety || 'Variety not specified'} · {crop.current_stage || 'Stage not specified'}</p><label>Growth stage<select aria-label={`${crop.crop_name} growth stage`} value={crop.current_stage || ''} onChange={(event) => void updateCropStage(crop, event.target.value)}><option value="">Choose a stage</option>{GROWTH_STAGES.map((stage) => <option key={stage.value} value={stage.value}>{stage.label}</option>)}</select></label></div></div><div className="crop-actions"><button className="care-button" onClick={() => showCarePlan(crop)}>Care plan</button><button className="delete-button" onClick={() => deleteCrop(crop)}>Delete</button></div></article>)}
        {carePlan && <section className="care-plan"><div className="care-plan-header"><div><span className="eyebrow">PERSONALISED CARE</span><h2>{carePlan.title}</h2><p>Current stage: {carePlan.stage}</p></div><button className="quiet" onClick={() => setCarePlan(null)}>Close</button></div><p>{carePlan.summary}</p><strong>Today</strong><ul>{carePlan.today.map((item) => <li key={item}>{item}</li>)}</ul><strong>Watch for</strong><ul>{carePlan.watch_for.map((item) => <li key={item}>{item}</li>)}</ul><p><strong>Next step:</strong> {carePlan.next_step}</p><p>{carePlan.context_note}</p><small>{carePlan.safety}</small></section>}
        <form onSubmit={addCrop} className="inline-form crop-add-form"><input list="crop-catalog-options" value={cropName} onChange={(event) => setCropName(event.target.value)} placeholder="Search crop or Indian alias" /><datalist id="crop-catalog-options">{cropCatalog.map((item) => <option key={item.crop_id} value={item.canonical_name}>{item.category} · {item.knowledge_status} · {item.aliases.join(', ')}</option>)}</datalist><select aria-label="Browse crops by category" value="" onChange={(event) => setCropName(event.target.value)}><option value="">Browse categories…</option>{Array.from(new Set(cropCatalog.map((item) => item.category))).map((category) => <optgroup key={category} label={category}>{cropCatalog.filter((item) => item.category === category).map((item) => <option key={item.crop_id} value={item.canonical_name}>{item.canonical_name} · {item.knowledge_status}</option>)}</optgroup>)}</select><select aria-label="Current growth stage (optional)" value={growthStage} onChange={(event) => setGrowthStage(event.target.value)}><option value="">Select growth stage (optional)</option>{GROWTH_STAGES.map((stage) => <option key={stage.value} value={stage.value}>{stage.label}</option>)}</select><button className="primary" type="submit">Add crop</button></form>
        <details className="crop-context-details"><summary>Add optional field context</summary><div className="crop-context-fields"><label>Variety<input value={cropVariety} onChange={(event) => setCropVariety(event.target.value)} placeholder="e.g. HD 2967" /></label><label>Locality<input value={cropLocality} onChange={(event) => setCropLocality(event.target.value)} placeholder="Village or town" /></label><label>State<input value={cropState} onChange={(event) => setCropState(event.target.value)} placeholder="Farm state" /></label><label>Country<input value={cropCountry} onChange={(event) => setCropCountry(event.target.value)} placeholder="Only if known" /></label><label>District<input value={cropDistrict} onChange={(event) => setCropDistrict(event.target.value)} placeholder="Farm district" /></label><label>Soil type<input value={cropSoilType} onChange={(event) => setCropSoilType(event.target.value)} placeholder="If known" /></label><label>Drainage<input value={cropDrainage} onChange={(event) => setCropDrainage(event.target.value)} placeholder="e.g. well drained" /></label><label>Irrigation availability<input value={cropIrrigation} onChange={(event) => setCropIrrigation(event.target.value)} placeholder="e.g. canal, drip, rainfed" /></label></div><small>Optional information is saved with your crop. Add it only if you know it.</small></details>
        {(() => { const selected = cropCatalog.find((item) => [item.canonical_name, ...item.aliases].some((alias) => alias.toLowerCase() === cropName.trim().toLowerCase())); const regions = selected?.verified_regions || []; const regionNote = regions.includes('India') ? 'for India' : regions.length ? `for ${regions.join(', ')}` : ''; return selected?.knowledge_status === 'LIMITED' ? <small className="location-status">No verified weather hazard rule is available for this crop yet.</small> : selected?.knowledge_status === 'PARTIAL' ? <small className="location-status">Verified {selected.verified_hazards?.join(', ').toLowerCase()} exposure check available for {selected.verified_stages?.filter((stage) => stage !== 'all').join(', ') || 'all stages'} {regionNote}. Overall crop assessment remains partial; check the displayed rule stage before adding.</small> : null; })()}
      </section>}

      {activePage === 'risk' && <section className="page-card">
        <div className="section-heading"><div><span className="eyebrow">EARLY WARNINGS</span><h2>Weather and crop risk</h2></div><span className="count">{alerts.filter((item) => !item.is_read).length} unread</span></div>
        <section className="risk-location-panel" aria-labelledby="risk-location-heading">
          <div className="risk-location-copy">
            <span className="eyebrow">WEATHER LOCATION</span>
            <h3 id="risk-location-heading">{weatherLocationLabel ? `Forecast for ${weatherLocationLabel}` : 'Where should we check the forecast?'}</h3>
            <p>{locationStatus}</p>
            {weatherError && <p className="estimate-error" role="status">{weatherError}</p>}
            <small>Browser location can be blocked by permissions. District search and manual coordinates always work and are saved for your crop risk checks.</small>
          </div>
          <div className="risk-location-actions">
            <button className="location-button" type="button" onClick={() => void requestWeatherRisk()}>{weather ? 'Use my location again' : 'Use my current location'}</button>
            {coordinates && <button className="location-button" type="button" onClick={() => void loadWeatherAt(coordinates.latitude, coordinates.longitude, weatherLocationLabel || 'Selected location')}>Reload selected location</button>}
          </div>
          {locationControls('risk')}
        </section>
        <button className="secondary" onClick={() => void assessSavedCrops()} disabled={savedRiskBusy}>{savedRiskBusy ? 'Checking saved crops…' : 'Check saved crop alerts'}</button>
        {!intelligenceCrops.length && crops.length > 0 && <p className="forecast-daily-note">Your growing list has {crops.length} crop(s), but none has a saved forecast location yet. Select a location and add the crop again to enable crop-specific assessment. Missing location is unavailable, not low risk.</p>}
        {weather?.forecast?.length ? <section className="risk-weather-window" aria-label="Local weather forecast"><div className="risk-weather-heading"><div><span className="eyebrow">LOCAL FORECAST · {weather.provider.toUpperCase()}</span><h3>Weather at your selected coordinates</h3><p>{weather.latitude?.toFixed(3)}, {weather.longitude?.toFixed(3)} · {weather.timezone || 'Local timezone'}{weather.forecast_issued_at ? ` · Forecast ${weather.forecast_issued_at}` : ''}{weather.retrieved_at ? ` · Retrieved ${new Date(weather.retrieved_at).toLocaleString('en-IN')}` : ''}</p>{weather.stale && <p className="forecast-stale-note">Provider unavailable; showing cached weather ({Math.round((weather.cache_age_seconds || 0) / 3600)} hours old).</p>}</div><a href="https://mausam.imd.gov.in/responsive/agromet_adv_ser_district_current_en.php" target="_blank" rel="noreferrer">Open current IMD district advisories ↗</a></div>{weather.hourly_forecast?.length ? <div className="risk-hourly-window"><strong>Next 48 hours · hourly forecast</strong><div className="risk-hourly-grid">{Array.from({length: Math.min(8, Math.ceil(Math.min(weather.hourly_forecast.length, 48) / 6))}, (_, index) => { const hours = weather.hourly_forecast!.slice(index * 6, index * 6 + 6); const rain = hours.map((hour) => hour.rainfall); const complete = hours.length === 6 && rain.every((value) => value != null); const temps = hours.map((hour) => hour.temperature).filter((value): value is number => value != null); const humidities = hours.map((hour) => hour.humidity).filter((value): value is number => value != null); const winds = hours.map((hour) => hour.wind_speed).filter((value): value is number => value != null); return <span key={index}>{hours[0]?.time || `Period ${index + 1}`}<small>{complete ? `${rain.reduce<number>((total, value) => total + Number(value), 0).toFixed(1)} mm rain` : 'Rain data incomplete'}</small><small>{temps.length ? `${Math.min(...temps)}–${Math.max(...temps)}°C` : 'Temp unavailable'}</small><small>{humidities.length ? `${Math.round(humidities.reduce((sum, value) => sum + value, 0) / humidities.length)}% RH` : 'Humidity unavailable'}</small><small>{winds.length ? `Wind ${Math.max(...winds)} km/h` : 'Wind unavailable'}</small></span>; })}</div></div> : <p className="forecast-daily-note">Hourly observations are unavailable from this provider. Daily totals below are not presented as an exact 48-hour accumulation.</p>}<div className="risk-weather-days">{weather.forecast.slice(0, 5).map((day) => <article key={day.date}><strong>{day.date}</strong><span>Rain {day.rainfall == null ? 'not reported' : `${day.rainfall} mm`}</span><span>High {day.temperature_max == null ? '—' : `${day.temperature_max}°C`} · Low {day.temperature_min == null ? '—' : `${day.temperature_min}°C`}</span></article>)}</div></section> : null}
        {weatherSignals.map((signal) => <article className="weather-signal-card" key={`${signal.date}-${signal.category}-${signal.rainfall_mm}`}><div><span className="eyebrow">GENERAL WEATHER SIGNAL · {signal.date || 'FORECAST'}</span><h3>{signal.title}</h3><p>{signal.explanation}</p><p><strong>Suggested check:</strong> {signal.recommended_action}</p><a href={signal.source_url} target="_blank" rel="noreferrer">Source: {signal.source}</a></div><strong>{signal.rainfall_mm} mm</strong></article>)}
        {uniqueWeatherRisks.filter((risk) => risk.status !== 'unavailable' || !usableIntelligenceNames.has(cropAssessmentKey(risk.crop))).map((risk) => <CropRiskCard
          key={`${risk.crop}-${risk.risk_window_hours}`}
          cropName={risk.crop}
          status={risk.status}
          riskLevel={risk.level}
          riskIndex={risk.score}
          hazards={risk.hazards || []}
          modelAssessment={risk.model_assessment}
          weather={{ ...weather, current_humidity_percent: risk.weather_observations?.current_humidity_percent }}
          expectedRainfall={risk.expected_rainfall}
          riskWindowHours={risk.risk_window_hours}
          locationLabel={risk.state || weatherLocationLabel || undefined}
          missingInputs={risk.missing_inputs || []}
          limitations={risk.limitations || []}
          technicalContent={<div><p>{risk.summary}</p><p>Forecast resolution: {risk.risk_resolution || 'not specified by the API'} ? Knowledge status: {risk.knowledge_status}</p></div>}
        />)}
        {uniqueIntelligenceResults.filter((item) => !usableWeatherRiskNames.has(cropAssessmentKey(item.crop.crop_name)) && (!weatherRiskNames.has(cropAssessmentKey(item.crop.crop_name)) || item.risk.status !== 'unavailable')).map((item) => {
          const location = [item.risk.location?.city || item.crop.city, item.risk.location?.district || item.crop.district, item.risk.location?.state || item.crop.state, item.crop.country].filter(Boolean).join(', ');
          const stage = item.risk.growth_stage || item.crop.growth_stage;
          return <CropRiskCard
            key={`intelligence-${item.crop.id}`}
            cropName={item.crop.crop_name}
            status={item.risk.status}
            riskLevel={item.risk.overall_risk}
            riskIndex={item.risk.risk_score}
            hazards={item.risk.hazards || []}
            modelAssessment={item.risk.model_assessment}
            alerts={item.risk.alerts}
            weather={item.weather}
            locationLabel={location || undefined}
            missingInputs={item.risk.missing_inputs || []}
            limitations={item.risk.limitations || []}
            technicalContent={<>
              <p>{item.risk.summary}</p>
              <p>Knowledge status: {item.risk.knowledge_status} ? Growth stage: {stage || 'not recorded'} ? Forecast issued: {item.weather?.forecast_issued_at || 'not supplied'}{item.weather?.timezone ? ` (${item.weather.timezone})` : ''}</p>
              {item.weather?.provider_status && <p>Weather source status: {item.weather.provider_status}{item.weather.freshness_status ? ` ? ${item.weather.freshness_status}` : ''}{item.weather.cache_age_seconds != null ? ` ? cache age ${item.weather.cache_age_seconds}s` : ''}{item.weather.provider_http_status ? ` ? HTTP ${item.weather.provider_http_status}` : ''}{item.weather.provider_error ? ` ? ${item.weather.provider_error}` : ''}</p>}
              {item.weather?.stale && <p>Cached forecast may be stale. Exposure rules are not scored against stale data.</p>}
              <div className="crop-risk-context">
                <label>Growth stage for rule matching<select aria-label={`${item.crop.crop_name} risk assessment stage`} value={item.crop.growth_stage || ''} onChange={(event) => void updateSavedCropStage(item.crop, event.target.value)}><option value="">Not recorded</option>{GROWTH_STAGES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
                <label>Farm state for geographic rule matching<input aria-label={`${item.crop.crop_name} farm state`} value={savedCropStates[item.crop.id] ?? item.crop.state ?? ''} onChange={(event) => setSavedCropStates((current) => ({ ...current, [item.crop.id]: event.target.value }))} placeholder="Enter known farm state" /></label>
                <button type="button" className="text-button" onClick={() => void updateSavedCropState(item.crop)}>Save state and reassess</button>
              </div>
              <p>Enter only known crop stage and farm state; no location or stage is inferred from coordinates.</p>
            </>}
          />;
        })}
        {alerts.length === 0 ? <div className="quiet-state">No alerts yet. Check saved crop alerts to assess each crop against its verified rules.</div> : alerts.map((alert) => { const evidence = alert.message.match(/Evidence source: (https?:\/\/\S+)/); const message = evidence ? alert.message.slice(0, evidence.index).trim() : alert.message; return <article className={`alert-card ${alert.severity.toLowerCase()}`} key={alert.id}><span className="alert-mark" /><div><strong>{alert.title}</strong><p>{message}</p>{evidence && <a href={evidence[1]} target="_blank" rel="noreferrer">Evidence source</a>}</div></article>; })}
      </section>}

      {activePage === 'diagnose' && <section className="page-card diagnose-page">
        <div className="diagnose-grid">
          <section className="diagnose-upload"><span className="eyebrow">CROP / PLANT DISEASE SCAN</span><h2>Examine a crop</h2><p>Use a sharp, well lit image of one affected leaf or plant area for the most useful visual assessment.</p><form onSubmit={scanPlant}><label className={`upload-zone ${imageFile ? 'has-image' : ''}`} htmlFor="scan-image" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); selectScanImage(event.dataTransfer.files[0]); }}><input id="scan-image" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => selectScanImage(event.target.files?.[0])} /><span className="upload-symbol" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M16 22V7m0 0-6 6m6-6 6 6M6 21v5h20v-5"/></svg></span><strong>{imageFile ? 'Choose a different image' : 'Choose an image or drop it here'}</strong><small>JPG, PNG, or WEBP · Up to 10 MB</small></label><button className="primary" type="submit" disabled={scanBusy || !imageFile}>{scanBusy ? 'Analyzing…' : 'Analyze crop'}</button></form>
            {imageFile && <div className="scan-preview"><img src={imagePreview} alt="Preview of the selected crop for disease analysis"/><div className="scan-file"><div><strong>{imageFile.name}</strong><small>{(imageFile.size / 1024 / 1024).toFixed(2)} MB · Ready for analysis</small></div><button type="button" className="text-button" onClick={() => { setImageFile(null); setDiagnosis(null); }}>Remove</button></div></div>}
            {scanBusy && <p role="status" className="scan-progress">Checking the image and preparing crop care guidance…</p>}
            {diagnosis && <div className="diagnosis"><span className="eyebrow">GEMINI VISION · LIKELY IDENTIFICATION</span><dl className="diagnosis-fields"><div><dt>Crop name</dt><dd>{diagnosis.crop_name || diagnosis.crop || 'Unknown'}</dd></div><div><dt>Likely disease</dt><dd>{diagnosis.disease_name || diagnosis.disease || 'Unable to identify'}</dd></div><div><dt>Care / cure guidance</dt><dd>{diagnosis.cure || diagnosis.treatment || diagnosis.recommendations?.[0] || 'No guidance returned.'}</dd></div></dl><p className="diagnosis-safety">This is an AI assessment from the image, not a confirmed diagnosis. Confirm uncertain symptoms with a local agriculture expert before treatment.</p></div>}
          </section>
          <section className="diagnose-chat">
            <span className="eyebrow">ASK KHETI · GEMINI ASSISTANT</span>
            <h2>Get a second opinion</h2>
            <p>Ask about this scan or get crop guidance in English, Hindi, or Hinglish. Kheti remembers this conversation.</p>
            <label>Language<select value={assistantLanguage} onChange={(event) => setAssistantLanguage(event.target.value as 'en'|'hi'|'hinglish')}><option value="en">English</option><option value="hi">Hindi</option><option value="hinglish">Hinglish</option></select></label>
            <div className="chat-transcript" aria-live="polite">
              {chatMessages.length === 0 && <p className="chat-empty">Ask anything about sowing, care, pests, or the scan result. For exact doses and live prices, Kheti will point you to the product label or an official source.</p>}
              {chatMessages.map((message, index) => <article key={index} className={`chat-message ${message.role}`}><span className="chat-role">{message.role === 'user' ? 'You' : 'Kheti'}</span>{chatText(message.content)}</article>)}
              {chatBusy && <p role="status" className="scan-progress">Kheti is thinking…</p>}
            </div>
            <div className="chat-input-row">
              <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={diagnosis ? `Ask about ${diagnosis.crop_name || diagnosis.crop || 'this crop'} or its care…` : 'Ask about the crop or disease…'} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void askAgricultureAssistant(); } }} />
              <button className="mic-button" type="button" onClick={startAssistantVoice} aria-label="Speak your question" title="Speak your question">{microphoneIcon}</button>
              <button className="primary" disabled={chatBusy || !question.trim()} onClick={askAgricultureAssistant}>{chatBusy ? 'Thinking…' : 'Ask Kheti'}</button>
            </div>
            {chatMessages.length > 0 && <div className="chat-actions"><button className="text-button" type="button" onClick={() => setChatMessages([])}>Clear conversation</button></div>}
          </section>
        </div>
        <small className="scan-disclaimer">Image analysis is decision support, not a confirmed diagnosis. Do not apply pesticides or change treatment based only on an AI result; verify with a local agriculture expert.</small>
      </section>}
      {activePage === 'market' && <PlatformPages userId={user.id} initialPage="market" />}
      {activePage === 'tools' && <PlatformPages userId={user.id} initialPage="voice" />}
      {status && <div className="toast" role="status">{status}</div>}
      {activePage !== 'tools' && activePage !== 'market' && <AssistantLauncher onClick={()=>setActivePage('tools')}/>}
      <AppFooter />
    </main>
  );
}
