import { FormEvent, useEffect, useState } from 'react';
import { PlatformPages } from './PlatformPages';
import './App.css';

type UserType = 'farmer' | 'gardener';
type User = { id: number; name: string; user_type: UserType };
type Crop = { id: number; crop_name: string; variety?: string; current_stage?: string; status: string; field_id: number };
type CatalogCrop = { crop_id: string; canonical_name: string; aliases: string[]; category: string; knowledge_status: 'FULL' | 'PARTIAL' | 'LIMITED' };
type Alert = { id: number; title: string; message: string; severity: string; is_read: boolean };
type Farm = { id: number };
type Field = { id: number };
type Weather = { provider: string; configured: boolean; latitude?: number; longitude?: number; timezone?: string; temperature?: number; humidity?: number; rainfall?: number; wind_speed?: number; precipitation_probability?: number; forecast?: Array<{ date: string; rainfall: number; temperature_max?: number; temperature_min?: number; precipitation_probability?: number }>; message?: string };
type WeatherRisk = { crop: string; level: string; score: number | null; knowledge_status: string; summary?: string; limitations?: string[]; expected_rainfall: number; risk_window_hours: number; reasons: string[] };
type WeatherSignal = { date?: string; rainfall_mm: number; category: string; title: string; explanation: string; recommended_action: string; source: string; source_url: string };
type WeatherRiskResponse = { location?: string; weather: Weather & { latitude: number; longitude: number; forecast?: Array<{ date: string; rainfall: number }> }; weather_signals?: WeatherSignal[]; risks: WeatherRisk[] };
type Place = { id: number; name: string; admin1?: string; admin2?: string; country?: string; latitude: number; longitude: number };
type MainPage = 'overview' | 'crops' | 'risk' | 'diagnose' | 'tools';
type IntelligenceCrop = { id: number; crop_name: string; city?: string; state?: string; growth_stage?: string };
type IntelligenceResult = { crop: IntelligenceCrop; risk: { overall_risk: string; risk_score: number | null; knowledge_status: string; limitations?: string[]; summary: string; alerts: Array<{ title: string; severity: string; expected_time: string; explanation: string; recommended_actions: string[] }> } };
type CarePlan = { title: string; stage: string; summary: string; today: string[]; watch_for: string[]; next_step: string; context_note: string; safety: string };
type Diagnosis = {
  crop?: string;
  disease?: string;
  confidence?: number;
  symptoms?: string[] | string;
  treatment?: string;
  prevention?: string;
  recommended_action?: string;
  recommendations?: string[];
  model_status?: string;
  agreement?: boolean;
};

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

async function fetchLocationWeather(latitude: number, longitude: number): Promise<Weather> {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    current: 'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m',
    daily: 'precipitation_sum,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
    forecast_days: '7',
    timezone: 'auto',
  });
  let payload: Record<string, any>;
  try {
    const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params}`);
    if (!response.ok) throw new Error(`Weather provider returned HTTP ${response.status}.`);
    payload = await response.json();
  } catch (browserError) {
    try {
      return await api<Weather>(`/weather?${params}`);
    } catch (serverError) {
      const reason = serverError instanceof Error ? serverError.message : String(browserError);
      throw new Error(`Weather could not be loaded from the browser or server provider. ${reason}`);
    }
  }
  const current = payload.current ?? {};
  const daily = payload.daily ?? {};
  const forecast = (daily.time ?? []).map((date: string, index: number) => ({
    date,
    rainfall: daily.precipitation_sum?.[index] ?? 0,
    temperature_max: daily.temperature_2m_max?.[index],
    temperature_min: daily.temperature_2m_min?.[index],
    precipitation_probability: daily.precipitation_probability_max?.[index] ?? 0,
  }));
  return {
    provider: 'open-meteo',
    configured: true,
    latitude: payload.latitude ?? latitude,
    longitude: payload.longitude ?? longitude,
    timezone: payload.timezone,
    temperature: current.temperature_2m,
    humidity: current.relative_humidity_2m,
    rainfall: current.precipitation,
    wind_speed: current.wind_speed_10m,
    precipitation_probability: Math.max(0, ...forecast.map((day: { precipitation_probability?: number }) => day.precipitation_probability ?? 0)),
    forecast,
  };
}

export default function App() {
  const [userType, setUserType] = useState<UserType | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [fieldId, setFieldId] = useState<number | null>(null);
  const [authMode, setAuthMode] = useState<'register' | 'login'>('login');
  const [crops, setCrops] = useState<Crop[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('nikhilkrsingh2004@gmail.com');
  const [password, setPassword] = useState('');
  const [cropName, setCropName] = useState('');
  const [growthStage, setGrowthStage] = useState('vegetative');
  const [cropCatalog, setCropCatalog] = useState<CatalogCrop[]>([]);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [status, setStatus] = useState('');
  const [weather, setWeather] = useState<Weather | null>(null);
  const [weatherError, setWeatherError] = useState('');
  const [locationStatus, setLocationStatus] = useState('Location not checked');
  const [locationQuery, setLocationQuery] = useState('');
  const [locationMatches, setLocationMatches] = useState<Place[]>([]);
  const [selectedLocationId, setSelectedLocationId] = useState('');
  const [weatherRisks, setWeatherRisks] = useState<WeatherRisk[]>([]);
  const [weatherSignals, setWeatherSignals] = useState<WeatherSignal[]>([]);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [carePlan, setCarePlan] = useState<CarePlan | null>(null);
  const [coordinates, setCoordinates] = useState<{ latitude: number; longitude: number } | null>(null);
  const [intelligenceCrops, setIntelligenceCrops] = useState<IntelligenceCrop[]>([]);
  const [intelligenceResults, setIntelligenceResults] = useState<IntelligenceResult[]>([]);
  const [activePage, setActivePage] = useState<MainPage>('overview');
  const [assistantLanguage, setAssistantLanguage] = useState<'en' | 'hi' | 'hinglish'>('en');

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

  async function requestWeatherRisk() {
    if (!navigator.geolocation) {
      setLocationStatus('Browser location is unavailable. Search for a city or district below.');
      return;
    }
    setLocationStatus('Requesting location permission…');
    navigator.geolocation.getCurrentPosition(async (position) => {
      const latitude = position.coords.latitude;
      const longitude = position.coords.longitude;
      try {
        const localWeather = await fetchLocationWeather(latitude, longitude);
        setWeather(localWeather);
        setWeatherError('');
        setCoordinates({ latitude, longitude });
        setLocationStatus(`Location enabled · ${latitude.toFixed(3)}, ${longitude.toFixed(3)}`);
        if (!user) return;

        try {
          await api('/farmer/profile', { method: 'PUT', body: JSON.stringify({ location_consent: true }) });
          await api('/location', {
            method: 'POST',
            body: JSON.stringify({ latitude, longitude, accuracy: position.coords.accuracy }),
          });
          const result = await api<WeatherRiskResponse>('/weather/risk', {
            method: 'POST',
            body: JSON.stringify({ latitude, longitude, accuracy: position.coords.accuracy, weather: localWeather }),
          });
          setWeather(result.weather);
          setWeatherRisks(result.risks);
          setWeatherSignals(result.weather_signals ?? []);
          const alertData = await api<{ items: Alert[] }>('/alerts');
          setAlerts(alertData.items);
        } catch (error) {
          setWeatherError(`Local weather loaded. Saving location and crop risks failed: ${(error as Error).message}`);
        }
      } catch (error) {
        setWeatherError((error as Error).message);
        setLocationStatus('Could not load weather for this location.');
      }
    }, (error) => {
      setLocationStatus(error.code === 1 ? 'Location permission was denied. Search for a city or district below.' : 'Location could not be read. Search for a city or district below.');
      setWeatherError('Allow browser location or search for a town or district to check local weather.');
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 15 * 60 * 1000 });
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
      setLocationStatus('Location search is unavailable right now.');
      setWeatherError((error as Error).message);
    }
  }

  async function useSelectedLocation() {
    const place = locationMatches.find((item) => String(item.id) === selectedLocationId);
    if (!place) return;
    const locationName = [place.name, place.admin2, place.admin1].filter(Boolean).join(', ');
    try {
      const localWeather = await fetchLocationWeather(place.latitude, place.longitude);
      setWeather(localWeather);
      setWeatherError('');
      setCoordinates({ latitude: place.latitude, longitude: place.longitude });
      setLocationStatus(`${locationName} · ${place.latitude.toFixed(3)}, ${place.longitude.toFixed(3)}`);
      if (!user) return;
      try {
        await api('/farmer/profile', { method: 'PUT', body: JSON.stringify({ location_consent: true }) });
        await api('/location', { method: 'POST', body: JSON.stringify({ latitude: place.latitude, longitude: place.longitude, location_name: locationName }) });
        const result = await api<WeatherRiskResponse>('/weather/risk', {
          method: 'POST',
          body: JSON.stringify({ latitude: place.latitude, longitude: place.longitude, location: locationName, weather: localWeather }),
        });
        setWeather(result.weather);
        setWeatherRisks(result.risks);
        setWeatherSignals(result.weather_signals ?? []);
        setAlerts((await api<{ items: Alert[] }>('/alerts')).items);
      } catch (error) {
        setWeatherError(`Local weather loaded. Saving location and crop risks failed: ${(error as Error).message}`);
      }
    } catch (error) {
      setWeatherError((error as Error).message);
      setLocationStatus('Could not load weather for this place. Try another location.');
    }
  }

  async function createProfile(event: FormEvent) {
    event.preventDefault();
    if (!userType || (authMode === 'register' && !name.trim())) return;
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
    }
  }

  async function addCrop(event: FormEvent) {
    event.preventDefault();
    if (!cropName.trim()) return;
    if (!fieldId) {
      setStatus('A field is required before adding a crop.');
      return;
    }
    try {
      const crop = await api<Crop>('/crops', { method: 'POST', body: JSON.stringify({ field_id: fieldId, crop_name: cropName, current_stage: growthStage, status: 'active' }) });
      setCrops((current) => [crop, ...current]);
      if (coordinates) {
        const intelligenceCrop = await api<IntelligenceCrop>('/crops', { method: 'POST', body: JSON.stringify({ user_id: user?.id, crop_name: cropName, latitude: coordinates.latitude, longitude: coordinates.longitude, mode: userType, growth_stage: growthStage }) });
        setIntelligenceCrops((current) => [intelligenceCrop, ...current]);
        const analysis = await api<IntelligenceResult>(`/crops/${intelligenceCrop.id}/analyze`, { method: 'POST' });
        setIntelligenceResults((current) => [analysis, ...current.filter((item) => item.crop.id !== intelligenceCrop.id)]);
      }
      setCropName('');
      setStatus(`${crop.crop_name} added to your growing list.`);
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
    if (!question.trim()) return;
    try {
      const data = await api<{ answer: string }>('/chat', { method: 'POST', body: JSON.stringify({ message: question, language: assistantLanguage, diagnosis_context: diagnosis ? { crop: diagnosis.crop, disease: diagnosis.disease, symptoms: diagnosis.symptoms, model_status: diagnosis.model_status } : undefined }) });
      setAnswer(data.answer);
      if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(data.answer);
        utterance.lang = assistantLanguage === 'en' ? 'en-IN' : 'hi-IN';
        window.speechSynthesis.speak(utterance);
      }
    } catch (error) {
      setStatus((error as Error).message);
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
    try {
      const response = await fetch('/api/predict', { method: 'POST', body: form, credentials: 'include' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? 'Disease scan failed.');
      setDiagnosis(data);
      setStatus('Scan complete. Treat this as decision support, not certainty.');
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  const locationSearchControls = (
    <div className="location-search">
      <form onSubmit={searchLocation}>
        <label htmlFor="location-query">Or search an Indian town or district</label>
        <div className="location-search-row"><input id="location-query" value={locationQuery} onChange={(event) => setLocationQuery(event.target.value)} placeholder="e.g. Nashik, Maharashtra" /><button className="location-button" type="submit">Search</button></div>
      </form>
      {locationMatches.length > 0 && <div className="location-search-row"><select aria-label="Choose the matching location" value={selectedLocationId} onChange={(event) => setSelectedLocationId(event.target.value)}>{locationMatches.map((place) => <option key={place.id} value={place.id}>{[place.name, place.admin2, place.admin1].filter(Boolean).join(', ')}</option>)}</select><button className="location-button" type="button" onClick={useSelectedLocation}>Use selected place</button></div>}
    </div>
  );

  const localWeatherPanel = (
    <section className="local-weather-panel">
      <button className="location-button" onClick={requestWeatherRisk}>Use my location for weather</button>
      {locationSearchControls}
      <div className="weather-card">
        <span>LOCAL WEATHER</span>
        {weather ? <><strong>{weather.temperature ?? '--'}°</strong><p>{weather.humidity ?? '--'}% humidity · {weather.rainfall ?? '--'} mm rain</p><small>{weather.timezone || weather.provider}</small></> : <><strong>--</strong><p>{weatherError || 'Allow location access to load your local forecast.'}</p></>}
      </div>
      <small className="location-status">{locationStatus}</small>
      {weatherError && weather && <small className="weather-error">{weatherError}</small>}
    </section>
  );

  if (!userType) {
    return (
      <main className="welcome-shell">
        <section className="welcome-copy">
          <span className="kicker">AGRI INTELLIGENCE / INDIA</span>
          <h1>Know your crop before the problem arrives.</h1>
          <p>Track crop health, field conditions, and early risk signals in one calm workspace.</p>
        </section>
        <section className="choice-panel">
          <span className="eyebrow">START WITH YOUR CONTEXT</span>
          <h2>Who are you?</h2>
          <button className="choice farmer" onClick={() => setUserType('farmer')}><strong>Farmer</strong><span>Fields, seasons, soil, and crop risk</span></button>
          <button className="choice gardener" onClick={() => setUserType('gardener')}><strong>Home gardener</strong><span>Plants, care routines, and pest warnings</span></button>
          {localWeatherPanel}
        </section>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="profile-shell">
        <section className="profile-card">
          <span className="eyebrow">{userType === 'farmer' ? 'FARMER PROFILE' : 'GARDEN PROFILE'}</span>
          <h1>{authMode === 'register' ? 'Let’s set up your workspace.' : 'Welcome back.'}</h1>
          <p>{authMode === 'register' ? 'Your profile gives crop and alert features a place to belong.' : 'Sign in to continue tracking your crops.'}</p>
          <form onSubmit={createProfile}>
            {authMode === 'register' && <label>Your name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Ananya Sharma" /></label>}
            <label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
            <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" /></label>
            <button className="primary" type="submit">{authMode === 'register' ? 'Create workspace' : 'Sign in'}</button>
          </form>
          <button className="quiet auth-switch" onClick={() => setAuthMode(authMode === 'register' ? 'login' : 'register')}>{authMode === 'register' ? 'Already have an account? Sign in' : 'Need an account? Register'}</button>
          {localWeatherPanel}
          {status && <p className="notice">{status}</p>}
        </section>
      </main>
    );
  }

  const pageTabs: Array<[MainPage, string]> = [
    ['overview', 'Overview'], ['crops', 'My crops'], ['risk', 'Weather & risk'],
    ['diagnose', 'Diagnose & Ask Kheti'], ['tools', 'Farm tools'],
  ];
  const microphoneIcon = <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="2.5" width="6" height="12" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V22m-4 0h8"/></svg>;

  return (
    <main className="app-shell">
      <header className="topbar"><div className="brand"><span className="brand-dot" />Kheti Lens</div><span className="mode-label">{userType === 'farmer' ? 'Farmer workspace' : 'Home garden workspace'}</span><button className="quiet" onClick={logout}>Sign out</button></header>
      <nav className="app-page-nav" aria-label="Main sections">
        {pageTabs.map(([page, label]) => <button key={page} className={activePage === page ? 'selected' : ''} aria-current={activePage === page ? 'page' : undefined} onClick={() => setActivePage(page)}>{label}</button>)}
      </nav>
      {activePage !== 'tools' && <section className="page-intro"><div><span className="eyebrow">{user.name.toUpperCase()}</span><h1>{activePage === 'overview' ? 'Your farm at a glance' : activePage === 'crops' ? 'Your crops and plants' : activePage === 'risk' ? 'Weather and crop risk' : 'Diagnose a crop and ask for help'}</h1><p>Decision support for your growing space. Confirm uncertain actions with local agricultural experts.</p></div>{activePage !== 'diagnose' && <div className="weather-card"><span>LOCAL WEATHER</span>{weather ? <><strong>{weather.temperature ?? '--'}°</strong><p>{weather.humidity ?? '--'}% humidity · {weather.rainfall ?? '--'} mm rain</p><small>{weather.timezone || weather.provider}</small></> : <p>{weatherError || 'Allow location access or search for a town to load local weather.'}</p>}<button className="location-button" onClick={requestWeatherRisk}>{weather ? 'Refresh location risk' : 'Use my location for weather'}</button>{locationSearchControls}{locationStatus && <small className="location-status">{locationStatus}</small>}</div>}</section>}

      {activePage === 'overview' && <section className="page-card overview-page">
        <h2>Welcome, {user.name}</h2><p>{crops.length} crops tracked · {alerts.filter((item) => !item.is_read).length} unread alerts</p>
        <div className="overview-stats"><article><span>Crops tracked</span><strong>{crops.length}</strong><small>plants in your growing list</small></article><article><span>Unread alerts</span><strong>{alerts.filter((item) => !item.is_read).length}</strong><small>weather and crop updates</small></article><article><span>Workspace</span><strong>{userType === 'farmer' ? 'Farm' : 'Garden'}</strong><small>your saved growing profile</small></article></div>
        {weatherError && <p className="weather-error">{weatherError}</p>}
      </section>}

      {activePage === 'crops' && <section className="page-card">
        <div className="section-heading"><div><span className="eyebrow">GROWING LIST</span><h2>My crops and plants</h2></div><span className="count">{crops.length} tracked</span></div>
        {crops.length === 0 ? <div className="empty-state"><strong>{userType === 'farmer' ? 'Your first crop starts here.' : 'Your first plant starts here.'}</strong><p>Add a crop or plant to track it here.</p></div> : crops.map((crop) => <article className="crop-card" key={crop.id}><div><span className="crop-icon">✳</span><div><h3>{crop.crop_name}</h3><p>{crop.variety || 'Variety not specified'} · {crop.current_stage || 'Stage not specified'}</p></div></div><div className="crop-actions"><button className="care-button" onClick={() => showCarePlan(crop)}>Care plan</button><button className="delete-button" onClick={() => deleteCrop(crop)}>Delete</button></div></article>)}
        {carePlan && <section className="care-plan"><div className="care-plan-header"><div><span className="eyebrow">PERSONALISED CARE</span><h2>{carePlan.title}</h2><p>Current stage: {carePlan.stage}</p></div><button className="quiet" onClick={() => setCarePlan(null)}>Close</button></div><p>{carePlan.summary}</p><strong>Today</strong><ul>{carePlan.today.map((item) => <li key={item}>{item}</li>)}</ul><strong>Watch for</strong><ul>{carePlan.watch_for.map((item) => <li key={item}>{item}</li>)}</ul><p><strong>Next step:</strong> {carePlan.next_step}</p><p>{carePlan.context_note}</p><small>{carePlan.safety}</small></section>}
        <form onSubmit={addCrop} className="inline-form crop-add-form"><input list="crop-catalog-options" value={cropName} onChange={(event) => setCropName(event.target.value)} placeholder="Search crop or Indian alias" /><datalist id="crop-catalog-options">{cropCatalog.map((item) => <option key={item.crop_id} value={item.canonical_name}>{item.category} · {item.knowledge_status} · {item.aliases.join(', ')}</option>)}</datalist><select aria-label="Browse crops by category" value="" onChange={(event) => setCropName(event.target.value)}><option value="">Browse categories…</option>{Array.from(new Set(cropCatalog.map((item) => item.category))).map((category) => <optgroup key={category} label={category}>{cropCatalog.filter((item) => item.category === category).map((item) => <option key={item.crop_id} value={item.canonical_name}>{item.canonical_name} · {item.knowledge_status}</option>)}</optgroup>)}</select><select aria-label="Current growth stage" value={growthStage} onChange={(event) => setGrowthStage(event.target.value)}><option value="germination">Germination</option><option value="seedling">Seedling</option><option value="vegetative">Vegetative</option><option value="flowering">Flowering</option><option value="fruiting">Fruiting</option><option value="grain filling">Grain filling</option><option value="harvest">Harvest</option></select><button className="primary" type="submit">Add crop</button></form>
        {cropName && cropCatalog.find((item) => [item.canonical_name, ...item.aliases].some((alias) => alias.toLowerCase() === cropName.trim().toLowerCase()))?.knowledge_status === 'LIMITED' && <small className="location-status">This crop is recognized, but verified crop-specific risk thresholds are not available yet.</small>}
      </section>}

      {activePage === 'risk' && <section className="page-card">
        <div className="section-heading"><div><span className="eyebrow">EARLY WARNINGS</span><h2>Weather and crop risk</h2></div><span className="count">{alerts.filter((item) => !item.is_read).length} unread</span></div>
        {weatherSignals.map((signal) => <article className="weather-signal-card" key={`${signal.date}-${signal.category}-${signal.rainfall_mm}`}><div><span className="eyebrow">GENERAL WEATHER SIGNAL · {signal.date || 'FORECAST'}</span><h3>{signal.title}</h3><p>{signal.explanation}</p><p><strong>Suggested check:</strong> {signal.recommended_action}</p><a href={signal.source_url} target="_blank" rel="noreferrer">Source: {signal.source}</a></div><strong>{signal.rainfall_mm} mm</strong></article>)}
        {weatherRisks.map((risk) => <article className={`forecast-risk ${risk.level.toLowerCase()}`} key={`${risk.crop}-${risk.risk_window_hours}`}><div><span className="eyebrow">FORECAST · 48 HOURS · {risk.knowledge_status}</span><h3>{risk.crop}: {risk.summary || 'Weather conditions checked'}</h3><p>Expected rainfall: <strong>{risk.expected_rainfall} mm</strong> · Risk window: <strong>{risk.risk_window_hours} hours</strong></p>{risk.score === null && <small>Weather observations are available. A crop risk score will appear after verified crop-specific thresholds are added.</small>}<ul>{risk.reasons.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}</ul></div><strong className="forecast-level">{risk.level}{risk.score === null ? '' : ' RISK'}</strong></article>)}
        {intelligenceResults.map((item) => <article className={`forecast-risk ${item.risk.overall_risk.toLowerCase()}`} key={`intelligence-${item.crop.id}`}><div><span className="eyebrow">CROP RISK · {item.crop.city || 'SAVED LOCATION'} · {item.risk.knowledge_status}</span><h3>{item.crop.crop_name}: {item.risk.summary}</h3>{item.risk.alerts.slice(0, 2).map((alert) => <p key={alert.title}><strong>{alert.severity}:</strong> {alert.title} · {alert.expected_time}</p>)}{item.risk.limitations?.map((limitation) => <small key={limitation}>{limitation}</small>)}</div><strong className="forecast-level">{item.risk.overall_risk}</strong></article>)}
        {alerts.length === 0 ? <div className="quiet-state">No alerts yet. Refresh location risk to evaluate your saved crops.</div> : alerts.map((alert) => <article className={`alert-card ${alert.severity.toLowerCase()}`} key={alert.id}><span className="alert-mark" /><div><strong>{alert.title}</strong><p>{alert.message}</p></div></article>)}
      </section>}

      {activePage === 'diagnose' && <section className="page-card diagnose-page">
        <div className="diagnose-grid">
          <section className="diagnose-upload"><span className="eyebrow">CROP / PLANT DISEASE SCAN</span><h2>Upload a clear image</h2><p>Include the affected leaf or plant area in good light. The scan will identify likely disease and provide care guidance when available.</p><form onSubmit={scanPlant}><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setImageFile(event.target.files?.[0] ?? null)} /><button className="primary" type="submit">Analyze image</button></form>
            {diagnosis && <div className="diagnosis"><span className="eyebrow">SCAN RESULT · {diagnosis.model_status || 'decision support'}</span><h3>{diagnosis.crop || 'Crop not identified'}</h3><strong>{diagnosis.disease || 'Disease not identified'}</strong><small>Confidence: {diagnosis.confidence ? `${Math.round(diagnosis.confidence * 100)}%` : 'not available'}</small>{diagnosis.symptoms && <p><b>Observed symptoms:</b> {Array.isArray(diagnosis.symptoms) ? diagnosis.symptoms.join(', ') : diagnosis.symptoms}</p>}{diagnosis.treatment && <p><b>Care / cure guidance:</b> {diagnosis.treatment}</p>}{diagnosis.prevention && <p><b>Prevention:</b> {diagnosis.prevention}</p>}{diagnosis.recommended_action && <p><b>Recommended next step:</b> {diagnosis.recommended_action}</p>}{diagnosis.recommendations?.map((item) => <p key={item}>{item}</p>)}</div>}
          </section>
          <section className="diagnose-chat"><span className="eyebrow">ASK KHETI · FOLLOW-UP</span><h2>Ask about this scan</h2><p>Ask what symptoms mean or how to care for the affected crop. You can also ask a general crop question.</p><label>Language<select value={assistantLanguage} onChange={(event) => setAssistantLanguage(event.target.value as 'en'|'hi'|'hinglish')}><option value="en">English</option><option value="hi">Hindi</option><option value="hinglish">Hinglish</option></select></label><div className="chat-input-row"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={diagnosis ? `Ask about ${diagnosis.crop || 'this crop'} or its care…` : 'Ask about the crop or disease…'} /><button className="mic-button" type="button" onClick={startAssistantVoice} aria-label="Speak your question" title="Speak your question">{microphoneIcon}</button><button className="primary" onClick={askAgricultureAssistant}>Send</button></div>{answer && <article className="assistant-answer">{answer}</article>}</section>
        </div>
        <small className="scan-disclaimer">Image analysis is decision support, not a confirmed diagnosis. Do not apply pesticides or change treatment based only on an AI result; verify with a local agriculture expert.</small>
      </section>}
      {activePage === 'tools' && <PlatformPages userId={user.id} />}
      {status && <div className="toast" role="status">{status}</div>}
    </main>
  );
}
