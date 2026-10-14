import { FormEvent, useEffect, useState } from 'react';
import { marketViewState } from './marketViewState.js';

type Page = 'home' | 'tasks' | 'schemes' | 'money' | 'diary' | 'market' | 'voice' | 'profile' | 'irrigation' | 'harvest';
type Item = Record<string, unknown>;
type MarketRecord = { id:number; commodity:string; variety:string|null; grade:string|null; state:string; district:string; mandi:string; observed_on:string; minimum_price:string|null; modal_price:string|null; maximum_price:string|null; price_unit:string; source_url:string; freshness:string };
type SpeechRecognizer = { lang: string; onresult: ((event: SpeechRecognitionEvent) => void) | null; onerror: (() => void) | null; start: () => void };
type SpeechRecognizerConstructor = new () => SpeechRecognizer;

function financeLabel(value: unknown, fallback: string): string {
  if (value === null || value === undefined) return fallback;
  const label = String(value).trim();
  if (!label || /^(undefined|null|nan)$/i.test(label)) return fallback;
  return label;
}

function hasFinanceValue(value: unknown): boolean {
  return financeLabel(value, '') !== '';
}

function schemeQuestions(value: unknown): Array<{field:string;label:string}> {
  if(!value||typeof value!=='object')return [];
  const rules=value as Record<string,unknown>;
  const all=[rules.required,rules.excluded_if,rules.official_review_if].flatMap(group=>Array.isArray(group)?group:[]);
  const seen=new Set<string>();
  return all.flatMap(rule=>{
    if(!rule||typeof rule!=='object')return [];
    const item=rule as Record<string,unknown>;
    const field=typeof item.field==='string'?item.field:'';
    if(!field||seen.has(field))return [];
    seen.add(field);
    return [{field,label:typeof item.label==='string'?item.label:field}];
  });
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) }, ...options });
  const data = response.status===204?null:await response.json().catch(()=>({}));
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

export function PlatformPages({ userId }: { userId: number }) {
  const [page, setPage] = useState<Page>('home');
  const [items, setItems] = useState<Item[]>([]);
  const [taskSchemeDeadlines, setTaskSchemeDeadlines] = useState<Item[]>([]);
  const [notice, setNotice] = useState('');
  const [taskTitle, setTaskTitle] = useState('');
  const [taskNote, setTaskNote] = useState('');
  const [amount, setAmount] = useState('');
  const [recordKind, setRecordKind] = useState<'expenses' | 'sales'>('expenses');
  const [quantity, setQuantity] = useState('');
  const [description, setDescription] = useState('');
  const [financeCategory, setFinanceCategory] = useState('other');
  const [financeSeason, setFinanceSeason] = useState('');
  const [financeFarmId, setFinanceFarmId] = useState('');
  const [financeCropId, setFinanceCropId] = useState('');
  const [financeFarms, setFinanceFarms] = useState<Item[]>([]);
  const [financeCrops, setFinanceCrops] = useState<Item[]>([]);
  const [financeQuantityUnit, setFinanceQuantityUnit] = useState('quintal');
  const [financePriceUnit, setFinancePriceUnit] = useState('quintal');
  const [financeDate, setFinanceDate] = useState(new Date().toISOString().slice(0,10));
  const [financeSellingCost, setFinanceSellingCost] = useState('0');
  const [financeEditId, setFinanceEditId] = useState<number|null>(null);
  const [financeSummary, setFinanceSummary] = useState<Record<string,unknown>>({});
  const [expectedOutput, setExpectedOutput] = useState('');
  const [yieldChange, setYieldChange] = useState('0');
  const [priceChange, setPriceChange] = useState('0');
  const [diaryNote, setDiaryNote] = useState('');
  const [answer, setAnswer] = useState('');
  const [question, setQuestion] = useState('');
  const [chatLanguage, setChatLanguage] = useState<'en'|'hi'|'hinglish'>('en');
  const [schemeMatch, setSchemeMatch] = useState('');
  const [schemeAnswers, setSchemeAnswers] = useState<Record<string,boolean|undefined>>({});
  const [schemeResults, setSchemeResults] = useState<Item[]>([]);
  const [schemeSearch, setSchemeSearch] = useState('');
  const [schemeLevel, setSchemeLevel] = useState('');
  const [schemeState, setSchemeState] = useState('');
  const [schemeVerification, setSchemeVerification] = useState('');
  const [schemeApplicationStatus, setSchemeApplicationStatus] = useState('');
  const [schemeLoading, setSchemeLoading] = useState(false);
  const [schemeMatchBusy, setSchemeMatchBusy] = useState(false);
  const [schemeDetailBusy, setSchemeDetailBusy] = useState(false);
  const [schemeDetail, setSchemeDetail] = useState<Item|null>(null);
  const [savedSchemeIds, setSavedSchemeIds] = useState<string[]>([]);
  const [schemeChecklists, setSchemeChecklists] = useState<Record<string,Record<string,boolean>>>({});
  const [schemeDeadlines, setSchemeDeadlines] = useState<Item[]>([]);
  const [advisoryCrops,setAdvisoryCrops] = useState<Item[]>([]);
  const [selectedAdvisoryCrop,setSelectedAdvisoryCrop] = useState('');
  const [soilMoistureStatus,setSoilMoistureStatus] = useState('');
  const [forecastRainfall,setForecastRainfall] = useState('');
  const [advisoryResult,setAdvisoryResult] = useState<Record<string,unknown>|null>(null);
  const [advisoryBusy,setAdvisoryBusy] = useState(false);
  const [harvestTargetDate,setHarvestTargetDate] = useState('');
  const [profile, setProfile] = useState<{name:string;state:string|null;district:string|null;preferred_language:string;location_consent_at?:string|null}>({name:'',state:'',district:'',preferred_language:'en'});
  const [marketItems, setMarketItems] = useState<MarketRecord[]>([]);
  const [marketPoints, setMarketPoints] = useState<{date:string;modal_price:number}[]>([]);
  const [marketTrends, setMarketTrends] = useState<Record<string,number|null>>({});
  const [marketStatus, setMarketStatus] = useState<Record<string,unknown>>({});
  const [marketChoices, setMarketChoices] = useState<{commodities:string[];states:string[];varieties:string[];grades:string[]}>({commodities:[],states:[],varieties:[],grades:[]});
  const [marketFilters, setMarketFilters] = useState({commodity:'',variety:'',grade:'',state:'',district:'',mandi:'',date_from:'',date_to:''});
  const [marketBusy, setMarketBusy] = useState(false);
  const [marketForecast, setMarketForecast] = useState<Record<string,unknown>|null>(null);
  const [marketCompare, setMarketCompare] = useState<MarketRecord[]>([]);
  const [marketCompareBusy, setMarketCompareBusy] = useState(false);
  const [marketCompareMessage, setMarketCompareMessage] = useState('');
  const marketState = marketViewState({loading:marketBusy,error:Boolean(notice)&&page==='market',items:marketItems});
  const marketLastIngestion = marketStatus.last_ingestion && typeof marketStatus.last_ingestion === 'object' ? marketStatus.last_ingestion as Record<string,unknown> : null;
  const marketEmptyMessage = marketLastIngestion?.error_message ? `Market sync failed: ${String(marketLastIngestion.error_message)}` : marketStatus.configured ? 'No stored observations yet. Run the backend market sync after outbound access to data.gov.in is available.' : 'No stored price observations. Configure DATA_GOV_IN_API_KEY on the backend and run the documented market refresh command.';

  useEffect(() => {
    setNotice('');
    const path = page === 'tasks' ? '/farm/actions/today' : page === 'money' ? `/farm/${recordKind}` : page === 'diary' ? '/farm/diary' : null;
    if (page !== 'tasks') setTaskSchemeDeadlines([]);
    if (page === 'tasks') request<{ items: Item[]; scheme_deadlines?: Item[] }>(path!).then((result) => { setItems(result.items); setTaskSchemeDeadlines(result.scheme_deadlines || []); }).catch((error: Error) => setNotice(error.message));
    else if (path) request<{ items: Item[] }>(path).then((result) => setItems(result.items)).catch((error: Error) => setNotice(error.message));
    if(page==='profile'||page==='voice') request<typeof profile>('/farmer/profile').then(setProfile).catch((error:Error)=>setNotice(error.message));
    if(page==='market') request<Record<string,unknown>>('/markets/status').then(setMarketStatus).catch((error:Error)=>setNotice(error.message));
    if(page==='market') request<typeof marketChoices>('/markets/options').then(setMarketChoices).catch((error:Error)=>setNotice(error.message));
    if(page==='money') {
      request<{items:Item[]}>(`/users/${userId}/farms`).then(result=>setFinanceFarms(result.items)).catch((error:Error)=>setNotice(error.message));
      request<Record<string,unknown>>('/farm/profit-summary').then(setFinanceSummary).catch((error:Error)=>setNotice(error.message));
    }
  }, [page, recordKind]);

  useEffect(()=>{
    if(page!=='schemes')return;
    const params=new URLSearchParams();
    if(schemeSearch.trim())params.set('q',schemeSearch.trim());
    if(schemeLevel)params.set('level',schemeLevel);
    if(schemeState.trim())params.set('state',schemeState.trim());
    if(schemeVerification)params.set('verification_status',schemeVerification);
    if(schemeApplicationStatus)params.set('application_status',schemeApplicationStatus);
    setSchemeLoading(true);
    request<{items:Item[]}>(`/schemes?${params}`).then(result=>setItems(result.items)).catch((error:Error)=>setNotice(error.message)).finally(()=>setSchemeLoading(false));
  },[page,schemeSearch,schemeLevel,schemeState,schemeVerification,schemeApplicationStatus]);

  useEffect(()=>{
    if(page!=='schemes')return;
    request<{items:Item[]}>('/schemes/saved').then(result=>{
      setSavedSchemeIds(result.items.map(item=>String(item.scheme_id)));
      setSchemeChecklists(Object.fromEntries(result.items.map(item=>[String(item.scheme_id),item.checklist_state&&typeof item.checklist_state==='object'?item.checklist_state as Record<string,boolean>:{}])));
    }).catch((error:Error)=>setNotice(error.message));
    request<{items:Item[]}>('/schemes/deadlines').then(result=>setSchemeDeadlines(result.items)).catch((error:Error)=>setNotice(error.message));
  },[page]);

  useEffect(()=>{
    if(page!=='irrigation'&&page!=='harvest')return;
    let active=true;
    (async()=>{
      try{
        const farms=(await request<{items:Item[]}>(`/users/${userId}/farms`)).items;
        const fields=(await Promise.all(farms.map(farm=>request<{items:Item[]}>(`/farms/${String(farm.id)}/fields`)))).flatMap(result=>result.items);
        const crops=(await Promise.all(fields.map(field=>request<{items:Item[]}>(`/fields/${String(field.id)}/crops`)))).flatMap(result=>result.items);
        if(active){setAdvisoryCrops(crops);if(!selectedAdvisoryCrop&&crops.length)setSelectedAdvisoryCrop(String(crops[0].id));}
      }catch(error){if(active)setNotice((error as Error).message);}
    })();
    return()=>{active=false;};
  },[page,userId]);

  useEffect(()=>{
    if(page!=='harvest'||!selectedAdvisoryCrop)return;
    const crop=advisoryCrops.find(item=>String(item.id)===selectedAdvisoryCrop);
    setHarvestTargetDate(String(crop?.expected_harvest_date||''));
    request<Record<string,unknown>>(`/crops/${selectedAdvisoryCrop}/harvest-window`).then(setAdvisoryResult).catch((error:Error)=>setNotice(error.message));
  },[page,selectedAdvisoryCrop,advisoryCrops]);

  useEffect(()=>{
    if(page!=='money'||!financeFarmId){setFinanceCrops([]);return;}
    request<{items:Item[]}>(`/farms/${financeFarmId}/fields`).then(async result=>{
      const crops=await Promise.all(result.items.map(field=>request<{items:Item[]}>(`/fields/${String(field.id)}/crops`)));
      setFinanceCrops(crops.flatMap(item=>item.items));
    }).catch((error:Error)=>setNotice(error.message));
  },[page,financeFarmId]);

  useEffect(()=>{
    if(page!=='money')return;
    const params=new URLSearchParams();
    if(financeFarmId)params.set('farm_id',financeFarmId);
    if(financeCropId)params.set('crop_id',financeCropId);
    if(financeSeason.trim())params.set('season',financeSeason.trim());
    request<{items:Item[]}>(`/farm/${recordKind}?${params}`).then(result=>setItems(result.items)).catch((error:Error)=>setNotice(error.message));
  },[page,recordKind,financeFarmId,financeCropId,financeSeason]);

  useEffect(()=>{
    if(page!=='money')return;
    refreshProfit().catch((error:Error)=>setNotice(error.message));
  },[page,financeFarmId,financeCropId,financeSeason,expectedOutput,financeQuantityUnit,yieldChange,priceChange]);

  useEffect(() => {
    if(page!=='market') return;
    const query = new URLSearchParams(Object.entries(marketFilters).filter(([,value])=>Boolean(value)));
    setNotice('');
    setMarketBusy(true);
    Promise.all([
      request<{items:MarketRecord[]}>(`/markets/prices?${query}`),
      request<{points:{date:string;modal_price:number}[];changes_percent:Record<string,number|null>}>(`/markets/trends?${query}`),
      request<Record<string,unknown>>(`/markets/forecast?${query}`),
    ]).then(([pricesResult,trendsResult,forecastResult])=>{
      setMarketItems(pricesResult.items);setMarketPoints(trendsResult.points);setMarketTrends(trendsResult.changes_percent);setMarketForecast(forecastResult);
    }).catch((error:Error)=>setNotice(error.message)).finally(()=>setMarketBusy(false));
  }, [page, marketFilters]);

  async function compareMandis(){
    if(!marketFilters.commodity){setNotice('Select a commodity to compare mandis.');return;}
    setMarketCompareBusy(true);
    setMarketCompareMessage('');
    setMarketCompare([]);
    try{const result=await request<{items:MarketRecord[];message?:string}>('/markets/compare',{method:'POST',body:JSON.stringify(marketFilters)});setMarketCompare(result.items||[]);setMarketCompareMessage(result.message||((result.items||[]).length?'':'No matching observations exist for at least two mandis on the same date and price unit.'));}
    catch(error){setNotice((error as Error).message);}
    finally{setMarketCompareBusy(false);}
  }

  async function refreshProfit(){
    const params=new URLSearchParams();
    if(financeFarmId)params.set('farm_id',financeFarmId);
    if(financeCropId)params.set('crop_id',financeCropId);
    if(financeSeason.trim())params.set('season',financeSeason.trim());
    if(expectedOutput) {params.set('expected_quantity',expectedOutput);params.set('expected_quantity_unit',financeQuantityUnit);params.set('yield_change_percent',yieldChange);params.set('price_change_percent',priceChange);}
    const result=await request<Record<string,unknown>>(`/farm/profit-summary?${params}`);
    setFinanceSummary(result);
  }

  function editFinanceRecord(item:Item){
    setFinanceEditId(Number(item.id));
    setFinanceFarmId(item.farm_id==null?'':String(item.farm_id));
    setFinanceCropId(item.crop_id==null?'':String(item.crop_id));
    setFinanceSeason(String(item.season||''));
    setDescription(String(recordKind==='expenses'?item.description:item.notes||''));
    setAmount(String(recordKind==='expenses'?item.amount:item.unit_price||''));
    setQuantity(String(item.quantity||''));
    setFinanceCategory(String(item.category||'other'));
    setFinanceQuantityUnit(String(item.quantity_unit||'quintal'));
    setFinancePriceUnit(String(item.price_unit||item.quantity_unit||'quintal'));
    setFinanceDate(String(recordKind==='expenses'?item.incurred_on:item.sold_on||new Date().toISOString().slice(0,10)));
    setFinanceSellingCost(String(item.selling_cost||'0'));
  }

  async function deleteFinanceRecord(id:string){
    try{
      await request(`/farm/${recordKind}/${id}`,{method:'DELETE'});
      setItems((await request<{items:Item[]}>(`/farm/${recordKind}`)).items);
      await refreshProfit();
      setNotice('Record deleted.');
    }catch(error){setNotice((error as Error).message);}
  }

  async function updateTaskState(id:string,state:'complete'|'dismiss'){
    try{
      await request(`/farm/actions/${id}/${state}`,{method:'POST',body:JSON.stringify({})});
      setItems((await request<{items:Item[]}>('/farm/actions/today')).items);
    }catch(error){setNotice((error as Error).message);}
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      if (page === 'tasks') await request('/tasks', { method: 'POST', body: JSON.stringify({ title: taskTitle, recommendation: taskNote }) });
      if (page === 'money' && recordKind==='expenses') await request(`/farm/expenses${financeEditId?`/${financeEditId}`:''}`, { method: financeEditId?'PUT':'POST', body: JSON.stringify({ category: financeCategory, description, amount, incurred_on: financeDate, farm_id: financeFarmId||null, crop_id: financeCropId||null, season: financeSeason||null }) });
      if (page === 'money' && recordKind==='sales') await request(`/farm/sales${financeEditId?`/${financeEditId}`:''}`, { method: financeEditId?'PUT':'POST', body: JSON.stringify({ quantity, quantity_unit: financeQuantityUnit, price_unit: financePriceUnit, unit_price: amount, selling_cost: financeSellingCost, sold_on: financeDate, notes: description, farm_id: financeFarmId||null, crop_id: financeCropId||null, season: financeSeason||null }) });
      if (page === 'diary') await request('/farm/diary', { method: 'POST', body: JSON.stringify({ notes: diaryNote }) });
      setNotice('Saved.');
      setTaskTitle(''); setTaskNote(''); setDescription(''); setAmount(''); setQuantity(''); setDiaryNote(''); setFinanceSellingCost('0');
      if (page === 'tasks') setItems((await request<{ items: Item[] }>('/farm/actions/today')).items);
      if (page === 'money') { const filters=new URLSearchParams();if(financeFarmId)filters.set('farm_id',financeFarmId);if(financeCropId)filters.set('crop_id',financeCropId);if(financeSeason.trim())filters.set('season',financeSeason.trim());setItems((await request<{ items: Item[] }>(`/farm/${recordKind}?${filters}`)).items); await refreshProfit(); setFinanceEditId(null); }
      if (page === 'diary') setItems((await request<{ items: Item[] }>('/farm/diary')).items);
    } catch (error) { setNotice((error as Error).message); }
  }

  async function ask() {
    try {
      const result = await request<{ answer: string }>('/chat', { method: 'POST', body: JSON.stringify({ message: question, language: chatLanguage }) });
      setAnswer(result.answer);
      if ('speechSynthesis' in window) {
        const utterance=new SpeechSynthesisUtterance(result.answer);
        utterance.lang=chatLanguage==='en'?'en-IN':'hi-IN';
        window.speechSynthesis.speak(utterance);
      }
    } catch (error) { setNotice((error as Error).message); }
  }

  async function checkSchemes() {
    setSchemeMatchBusy(true);
    setSchemeMatch('');
    setSchemeResults([]);
    try {
      const answers=Object.fromEntries(Object.entries(schemeAnswers).filter(([,value])=>value!==undefined));
      const result = await request<{ status: string; summary: string; results: Item[]; answers_saved: boolean }>('/schemes/match', { method: 'POST', body: JSON.stringify({ answers }) });
      setSchemeResults(result.results||[]);
      setSchemeMatch(result.results?.length ? result.summary : 'No schemes could be evaluated. Verify that the scheme registry is loaded and that a recently checked scheme has published eligibility rules.');
    } catch (error) { setNotice((error as Error).message); }
    finally { setSchemeMatchBusy(false); }
  }

  async function openScheme(schemeId:string){
    setSchemeDetailBusy(true);
    setSchemeDetail(null);
    try{const result=await request<{scheme:Item;updates:Item[]}>(`/schemes/${encodeURIComponent(schemeId)}`);setSchemeDetail({...result.scheme,updates:result.updates});}
    catch(error){setNotice((error as Error).message);}
    finally { setSchemeDetailBusy(false); }
  }

  async function toggleSavedScheme(schemeId:string){
    try{
      if(savedSchemeIds.includes(schemeId)){
        await request(`/schemes/saved/${encodeURIComponent(schemeId)}`,{method:'DELETE'});
        setSavedSchemeIds(ids=>ids.filter(id=>id!==schemeId));
      }else{
        await request('/schemes/saved',{method:'POST',body:JSON.stringify({scheme_id:schemeId})});
        setSavedSchemeIds(ids=>[...ids,schemeId]);
      }
    }catch(error){setNotice((error as Error).message);}
  }

  async function updateSchemeChecklist(schemeId:string,key:string,checked:boolean){
    try{await request(`/schemes/saved/${encodeURIComponent(schemeId)}`,{method:'PATCH',body:JSON.stringify({checklist_state:{[key]:checked}})});setSchemeChecklists(current=>({...current,[schemeId]:{...(current[schemeId]||{}),[key]:checked}}));}
    catch(error){setNotice((error as Error).message);}
  }

  async function requestIrrigationAdvice(event:FormEvent){
    event.preventDefault();
    if(!selectedAdvisoryCrop){setNotice('Add a crop before requesting an irrigation prompt.');return;}
    setAdvisoryBusy(true);setAdvisoryResult(null);setNotice('');
    try{
      const body:Record<string,unknown>={crop_id:Number(selectedAdvisoryCrop),soil_moisture_status:soilMoistureStatus};
      if(forecastRainfall.trim())body.forecast_rainfall=forecastRainfall;
      const result=await request<Record<string,unknown>>('/advisories/irrigation',{method:'POST',body:JSON.stringify(body)});
      setAdvisoryResult(result);
    }catch(error){setNotice((error as Error).message);}
    finally{setAdvisoryBusy(false);}
  }

  async function saveHarvestPlanningDate(event:FormEvent){
    event.preventDefault();
    if(!selectedAdvisoryCrop||!harvestTargetDate)return;
    setAdvisoryBusy(true);setNotice('');
    try{
      const result=await request<Record<string,unknown>>('/advisories/harvest-window',{method:'POST',body:JSON.stringify({crop_id:Number(selectedAdvisoryCrop),expected_harvest_date:harvestTargetDate})});
      setAdvisoryResult(result);
    }catch(error){setNotice((error as Error).message);}
    finally{setAdvisoryBusy(false);}
  }

  async function saveProfile(event:FormEvent){
    event.preventDefault();
    try{const saved=await request<typeof profile>('/farmer/profile',{method:'PUT',body:JSON.stringify(profile)});setProfile(saved);setNotice('Profile saved.');}
    catch(error){setNotice((error as Error).message);}
  }

  async function changeLocationConsent(consented:boolean){
    try{
      if(consented) await request('/farmer/profile',{method:'PUT',body:JSON.stringify({location_consent:true})});
      else await request('/location',{method:'DELETE'});
      setProfile({...profile,location_consent_at:consented?new Date().toISOString():null});
      setNotice(consented?'Location consent saved. Use the location weather button to share coordinates.':'Saved location deleted and consent withdrawn.');
    }catch(error){setNotice((error as Error).message);}
  }

  function speakQuestion() {
    const speech = window as typeof window & { SpeechRecognition?: SpeechRecognizerConstructor; webkitSpeechRecognition?: SpeechRecognizerConstructor };
    const Recognition = speech.SpeechRecognition || speech.webkitSpeechRecognition;
    if (!Recognition) { setNotice('Voice input is not supported by this browser. You can still type your question.'); return; }
    const recognition = new Recognition();
    recognition.lang = chatLanguage==='en'?'en-IN':'hi-IN';
    recognition.onresult = (event) => setQuestion(event.results[0][0].transcript);
    recognition.onerror = () => setNotice('Voice input could not be completed. Check microphone permission or type your question.');
    recognition.start();
  }

  return <section className="platform-hub">
    <nav className="platform-nav" aria-label="Farm tools">
      {([['home','Dashboard'],['tasks','Tasks'],['schemes','Schemes'],['irrigation','Irrigation advisor'],['harvest','Harvest planner'],['money','Farm finances'],['diary','Diary'],['market','Mandi Price Intelligence'],['voice','Voice assistant'],['profile','Profile']] as [Page,string][]).map(([id,label]) => <button key={id} className={page===id?'selected':''} onClick={()=>setPage(id)}>{label}</button>)}
    </nav>
    {notice && <p className="notice" role="status">{notice}</p>}
    {page==='home' && <p>Farm workspace for account {userId}. Crop scans, weather, and risk alerts are on the dashboard above.</p>}
    {page==='tasks' && <><h2>Today’s farm action plan</h2><p>Checklist items are generated from saved crop context and general care guidance. Weather and scheme deadlines are included only when verified inputs exist.</p><form className="inline-form" onSubmit={submit}><input required maxLength={160} placeholder="Add a task title" value={taskTitle} onChange={e=>setTaskTitle(e.target.value)}/><input required maxLength={2000} placeholder="What needs doing?" value={taskNote} onChange={e=>setTaskNote(e.target.value)}/><button className="primary">Save task</button></form>{taskSchemeDeadlines.length>0&&<section className="scheme-panel daily-deadlines"><h3>Verified scheme deadlines - next 30 days</h3><p>Only recently checked official records for your location are shown. Confirm details with the scheme authority.</p>{taskSchemeDeadlines.map(deadline=><article key={String(deadline.scheme_id)}><strong>{String(deadline.official_name)}</strong><span>Due {String(deadline.deadline)} {Boolean(deadline.application_status)&&<em>- {String(deadline.application_status)}</em>}</span><a href={String(deadline.official_application_url)} target="_blank" rel="noreferrer">Open official application page</a></article>)}</section>}{items.map(item=><article className="platform-item" key={String(item.id)}><strong>{String(item.title)}</strong><p>{String(item.recommendation)}</p>{Boolean(item.reason)&&<p>{String(item.reason)}</p>}<small>{String(item.state)} · {String(item.evidence_quality)}{item.due_date?` · Due ${String(item.due_date)}`:''}</small>{item.state==='open'&&<div className="task-actions"><button type="button" onClick={()=>updateTaskState(String(item.id),'complete')}>Mark complete</button><button type="button" onClick={()=>updateTaskState(String(item.id),'dismiss')}>Dismiss</button></div>}</article>)}</>}
    {page==='schemes' && <>
      <div className="scheme-heading"><div><span className="eyebrow">OFFICIAL PROGRAMMES</span><h2>Government benefits finder</h2><p>Browse schemes and compare your answers with published criteria. The responsible department makes the final decision.</p></div><a href="https://www.india.gov.in/topics/agriculture" target="_blank" rel="noreferrer">National Portal of India ↗</a></div>
      <div className="scheme-filters"><label>Search schemes<input value={schemeSearch} onChange={e=>setSchemeSearch(e.target.value)} placeholder="Name or purpose"/></label><label>Government level<select value={schemeLevel} onChange={e=>setSchemeLevel(e.target.value)}><option value="">All levels</option><option value="central">Central</option><option value="state">State</option></select></label><label>State scope<input value={schemeState} onChange={e=>setSchemeState(e.target.value)} placeholder="Any state"/></label><label>Source review<select value={schemeVerification} onChange={e=>setSchemeVerification(e.target.value)}><option value="">Any review status</option><option value="verified">Verified</option><option value="stale">Stale</option><option value="unverified">Unverified</option></select></label><label>Application status<select value={schemeApplicationStatus} onChange={e=>setSchemeApplicationStatus(e.target.value)}><option value="">Any application status</option><option value="open">Open</option><option value="closed">Closed</option><option value="continuous">Continuous</option><option value="unknown">Unknown</option></select></label></div>
      <section className="scheme-panel"><h3>Eligibility check</h3><p>Answers are used for this check only and are not saved. Choose “Not sure” to leave a rule unresolved.</p>
        {items.filter(item=>item.verification_status==='verified').flatMap(item=>schemeQuestions(item.eligibility_rules).map(question=>({schemeId:String(item.scheme_id),schemeName:String(item.official_name),...question}))).map(question=><label className="scheme-question" key={`${question.schemeId}-${question.field}`}><span>{question.label}</span><select value={schemeAnswers[question.field]===undefined?'':schemeAnswers[question.field]?'yes':'no'} onChange={e=>setSchemeAnswers(current=>({...current,[question.field]:e.target.value===''?undefined:e.target.value==='yes'}))}><option value="">Not sure / skip</option><option value="yes">Yes</option><option value="no">No</option></select></label>)}
        {!items.some(item=>item.verification_status==='verified')&&<p>No current eligibility rules are verified for the filtered schemes. You can still review official scheme links below.</p>}
        <button className="primary" type="button" onClick={checkSchemes} disabled={schemeMatchBusy}>{schemeMatchBusy?'Checking...':'Check against verified rules'}</button>
        {schemeMatch&&<p className="scheme-disclaimer" role="status">{schemeMatch}</p>}
        {schemeResults.map(result=><article className="scheme-result" key={String(result.scheme_id)}><div><strong>{String(result.official_name)}</strong><span className={`scheme-status ${String(result.status)}`}>{String(result.status).replace(/_/g,' ')}</span></div>{Array.isArray(result.reasons)&&result.reasons.map((reason,index)=><p key={index}>{String(reason)}</p>)}{Array.isArray(result.missing_information)&&result.missing_information.map((missing,index)=><small key={index}>Needs confirmation: {String((missing as Record<string,unknown>).question)}</small>)}<a href={String(result.official_application_url||result.official_source_url)} target="_blank" rel="noreferrer">Confirm with official department ↗</a></article>)}
      </section>
      {schemeDeadlines.length>0&&<section className="scheme-panel"><h3>Verified upcoming deadlines</h3>{schemeDeadlines.map(deadline=><p key={String(deadline.scheme_id)}><strong>{String(deadline.official_name)}</strong> · {String(deadline.deadline)} · <a href={String(deadline.official_application_url||'#')} target="_blank" rel="noreferrer">Official application page</a></p>)}</section>}
      <section className="scheme-list"><h3>Scheme registry</h3>{schemeLoading?<p role="status">Loading schemes...</p>:items.length===0?<p>No schemes match these filters. Clear the filters to browse the full registry.</p>:items.map(item=><article className="scheme-card" key={String(item.scheme_id)}><div className="scheme-card-top"><div><span className={`scheme-status ${String(item.verification_status)}`}>{String(item.verification_status)}</span><h4>{String(item.official_name)}</h4></div><button type="button" onClick={()=>toggleSavedScheme(String(item.scheme_id))}>{savedSchemeIds.includes(String(item.scheme_id))?'Saved ✓':'Save scheme'}</button></div><p>{String(item.description||'Purpose and eligibility details have not been verified yet. Review the official source before relying on this scheme information.')}</p>{Boolean(item.benefit_description)&&<p><strong>Benefit:</strong> {String(item.benefit_description)}</p>}<div className="scheme-facts"><span>Application status: <strong>{String(item.application_status||'unknown')}</strong></span><span>{item.deadline?`Deadline: ${String(item.deadline)}`:'Deadline not verified — check the official portal.'}</span><span>Last source check: {item.last_checked_at?String(item.last_checked_at):'Not recorded'}</span></div><div className="scheme-actions"><button type="button" onClick={()=>openScheme(String(item.scheme_id))} disabled={schemeDetailBusy}>{schemeDetailBusy?'Loading...':'View scheme details'}</button><a href={String(item.official_application_url||item.official_source_url||item.url)} target="_blank" rel="noreferrer">Official portal ↗</a></div></article>)}</section>
      {schemeDetail&&<section className="scheme-panel scheme-detail"><div className="scheme-card-top"><div><span className="eyebrow">SCHEME DETAILS</span><h3>{String(schemeDetail.official_name)}</h3></div><button type="button" onClick={()=>setSchemeDetail(null)}>Close details</button></div><p>{String(schemeDetail.description||'No verified description is currently recorded.')}</p><p><strong>Eligibility criteria:</strong> {schemeQuestions(schemeDetail.eligibility_rules).map(rule=>rule.label).join(' ')||'No verified structured criteria recorded.'}</p><p><strong>Exclusions:</strong> {Array.isArray(schemeDetail.exclusion_rules)?(schemeDetail.exclusion_rules as unknown[]).map(String).join('; '):'No verified exclusions recorded.'}</p><p><strong>Application status:</strong> {String(schemeDetail.application_status)} · <strong>Deadline:</strong> {schemeDetail.deadline?String(schemeDetail.deadline):'Not verified'}</p><h4>Documents checklist</h4>{Array.isArray(schemeDetail.document_checklist)&&(schemeDetail.document_checklist as unknown[]).map((doc,index)=>{const data=doc as Record<string,unknown>;const label=String(data.item||`Document ${index+1}`);const id=String(schemeDetail.scheme_id);return <label className="scheme-checklist" key={label}><input type="checkbox" disabled={!savedSchemeIds.includes(id)} checked={Boolean(schemeChecklists[id]?.[label])} onChange={e=>updateSchemeChecklist(id,label,e.target.checked)}/><span><strong>{label}</strong><small>{String(data.note||data.status||'Confirm requirements on the official portal.')}</small></span></label>})}{!savedSchemeIds.includes(String(schemeDetail.scheme_id))&&Array.isArray(schemeDetail.document_checklist)&&schemeDetail.document_checklist.length>0&&<small>Save this scheme to track document checklist progress.</small>}<h4>How to apply</h4>{Array.isArray(schemeDetail.application_procedure)?<ol>{(schemeDetail.application_procedure as unknown[]).map((step,index)=><li key={index}>{String(step)}</li>)}</ol>:<p>Application steps are not verified. Use the official portal.</p>}<p><a href={String(schemeDetail.official_application_url||schemeDetail.official_source_url)} target="_blank" rel="noreferrer">Open official scheme source ↗</a></p>{Array.isArray(schemeDetail.updates)&&<><h4>Recorded source updates</h4>{(schemeDetail.updates as unknown[]).length?(schemeDetail.updates as unknown[]).map((update,index)=><p key={index}>Reviewed {String((update as Record<string,unknown>).recorded_at)} · <a href={String((update as Record<string,unknown>).evidence_url)} target="_blank" rel="noreferrer">Evidence ↗</a></p>):<small>No source change history is recorded.</small>}</>}</section>}
    </>}
    {page==='irrigation' && <section className="advisory-page"><span className="eyebrow">FIELD OBSERVATION</span><h2>Irrigation advisor</h2><p>This tool uses your field moisture observation as a prompt. It does not measure soil moisture remotely or prescribe a crop-specific water amount.</p>{advisoryCrops.length===0?<div className="empty-state"><strong>No saved crops yet</strong><p>Add a crop in My crops before requesting an irrigation prompt.</p></div>:<><label>Crop<select value={selectedAdvisoryCrop} onChange={e=>{setSelectedAdvisoryCrop(e.target.value);setAdvisoryResult(null);}}>{advisoryCrops.map(crop=><option key={String(crop.id)} value={String(crop.id)}>{String(crop.crop_name)}{crop.current_stage?` - ${String(crop.current_stage)}`:''}</option>)}</select></label><form onSubmit={requestIrrigationAdvice}><label>Root-zone soil moisture you observed<select required value={soilMoistureStatus} onChange={e=>setSoilMoistureStatus(e.target.value)}><option value="">Choose an observation</option><option value="dry">Dry</option><option value="adequate">Adequate</option><option value="wet">Wet</option></select></label><label>Forecast rainfall (mm), optional<input type="number" min="0" max="1000" step="0.1" value={forecastRainfall} onChange={e=>setForecastRainfall(e.target.value)} placeholder="Enter a forecast you checked"/></label><small>Forecast values are supplied by you and are not independently verified here. Check <a href="https://mausam.imd.gov.in/responsive/agromet_adv_ser_block_current_en.php" target="_blank" rel="noreferrer">IMD district agromet advisories</a> and local crop guidance.</small><button className="primary" disabled={advisoryBusy}>{advisoryBusy?'Checking...':'Review irrigation conditions'}</button></form></>}{advisoryResult&&page==='irrigation'&&<article className="advisory-result"><span className={`scheme-status ${String(advisoryResult.status)}`}>{String(advisoryResult.status).replace(/_/g,' ')}</span><h3>{String(advisoryResult.timing||'No recommendation available')}</h3><p>{String(advisoryResult.reason||'')}</p><small>Evidence: {String(advisoryResult.evidence_quality||'insufficient')} - checked {String(advisoryResult.checked_at||'now')}</small>{Array.isArray(advisoryResult.limitations)&&<ul>{advisoryResult.limitations.map((note,index)=><li key={index}>{String(note)}</li>)}</ul>}</article>}</section>}
    {page==='harvest' && <section className="advisory-page"><span className="eyebrow">HARVEST PLANNING</span><h2>Harvest planner</h2><p>Save a date you or your local advisor expect. CropAI will show it as a planning target, not a maturity prediction, because verified crop- and variety-specific duration evidence is not configured.</p>{advisoryCrops.length===0?<div className="empty-state"><strong>No saved crops yet</strong><p>Add a crop in My crops before recording a harvest target.</p></div>:<><label>Crop<select value={selectedAdvisoryCrop} onChange={e=>{setSelectedAdvisoryCrop(e.target.value);setAdvisoryResult(null);}}>{advisoryCrops.map(crop=><option key={String(crop.id)} value={String(crop.id)}>{String(crop.crop_name)}{crop.variety?` - ${String(crop.variety)}`:''}</option>)}</select></label><form onSubmit={saveHarvestPlanningDate}><label>Expected harvest date<input required type="date" value={harvestTargetDate} onChange={e=>setHarvestTargetDate(e.target.value)}/></label><button className="primary" disabled={advisoryBusy}>{advisoryBusy?'Saving...':'Save planning date'}</button></form><p>Current status: <strong>{String(advisoryResult?.status||'Loading')}</strong>{advisoryResult?.expected_harvest_date?` - Planning target ${String(advisoryResult.expected_harvest_date)}`:''}</p>{advisoryResult&&<p>{String(advisoryResult.planning_note||'No reliable estimated range is available.')}</p>}</>}<p><a href="https://mausam.imd.gov.in/responsive/agromet_adv_ser_block_current_en.php" target="_blank" rel="noreferrer">Check current IMD district advisories</a></p></section>}
    {page==='money' && <><h2>Farm finances</h2><div className="platform-nav"><button className={recordKind==='expenses'?'selected':''} onClick={()=>{setRecordKind('expenses');setFinanceEditId(null);}}>Expenses</button><button className={recordKind==='sales'?'selected':''} onClick={()=>{setRecordKind('sales');setFinanceEditId(null);}}>Sales</button></div><form className="inline-form" onSubmit={submit}><label>Farm<select value={financeFarmId} onChange={e=>{setFinanceFarmId(e.target.value);setFinanceCropId('');}}><option value="">Unassigned</option>{financeFarms.map(f=><option key={String(f.id)} value={String(f.id)}>{String(f.name)}</option>)}</select></label><label>Crop<select value={financeCropId} onChange={e=>setFinanceCropId(e.target.value)}><option value="">Unassigned</option>{financeCrops.map(c=><option key={String(c.id)} value={String(c.id)}>{String(c.crop_name)}{c.season?` · ${String(c.season)}`:''}</option>)}</select></label><label>Season<input maxLength={80} value={financeSeason} onChange={e=>setFinanceSeason(e.target.value)} placeholder="e.g. Kharif 2026"/></label>{recordKind==='expenses'&&<label>Category<select value={financeCategory} onChange={e=>setFinanceCategory(e.target.value)}>{[['seeds','Seeds'],['fertilizer','Fertilizer'],['crop_protection','Crop protection'],['labor','Labor'],['machinery','Machinery and fuel'],['irrigation','Irrigation'],['equipment_rental','Equipment rental'],['transport','Transport'],['other','Other']].map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>}{recordKind==='sales'&&<><label>Quantity<input required type="number" min="0.001" step="0.001" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label><label>Quantity unit<select value={financeQuantityUnit} onChange={e=>setFinanceQuantityUnit(e.target.value)}><option value="kg">kg</option><option value="quintal">quintal</option><option value="tonne">tonne</option></select></label><label>Price per unit<select value={financePriceUnit} onChange={e=>setFinancePriceUnit(e.target.value)}><option value="kg">INR/kg</option><option value="quintal">INR/quintal</option><option value="tonne">INR/tonne</option></select></label><label>Selling costs (INR)<input type="number" min="0" step="0.01" value={financeSellingCost} onChange={e=>setFinanceSellingCost(e.target.value)}/></label></>}<label>{recordKind==='expenses'?'Description':'Sale notes'}<input required maxLength={recordKind==='expenses'?500:1000} value={description} onChange={e=>setDescription(e.target.value)}/></label><label>{recordKind==='expenses'?'Amount (INR)':'Price (INR per selected unit)'}<input required type="number" min="0" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></label><label>Date<input required type="date" value={financeDate} onChange={e=>setFinanceDate(e.target.value)}/></label><button className="primary">{financeEditId?'Update':'Record'} {recordKind==='expenses'?'expense':'sale'}</button>{financeEditId&&<button type="button" onClick={()=>setFinanceEditId(null)}>Cancel edit</button>}</form><div className="finance-summary"><h3>Recorded farm return</h3><p>Expenses ₹{String(financeSummary.expenses??'0')} · Sales revenue ₹{String(financeSummary.gross_revenue??'0')} · Selling costs ₹{String(financeSummary.selling_costs??'0')} · Net return ₹{String(financeSummary.net_return??'0')}</p><p>Break-even price: {financeSummary.break_even_price_per_quintal?`₹${String(financeSummary.break_even_price_per_quintal)}/quintal`:'enter expected saleable output below'}</p><form className="inline-form" onSubmit={async e=>{e.preventDefault();try{await refreshProfit();}catch(error){setNotice((error as Error).message);}}}><label>Expected saleable output<input type="number" min="0.001" step="0.001" value={expectedOutput} onChange={e=>setExpectedOutput(e.target.value)}/></label><label>Output unit<select value={financeQuantityUnit} onChange={e=>setFinanceQuantityUnit(e.target.value)}><option value="kg">kg</option><option value="quintal">quintal</option><option value="tonne">tonne</option></select></label><label>Yield change %<input type="number" min="-100" max="500" value={yieldChange} onChange={e=>setYieldChange(e.target.value)}/></label><label>Price change %<input type="number" min="-100" max="500" value={priceChange} onChange={e=>setPriceChange(e.target.value)}/></label><button>Calculate scenario</button></form>{Boolean(financeSummary.scenario)&&<p>Scenario estimated net return: {String((financeSummary.scenario as Record<string,unknown>).estimated_net_return??'incomplete; record a sale price first')}</p>}{Array.isArray(financeSummary.breakdown)&&financeSummary.breakdown.map((group,index)=><p key={index}>{String(group.crop)} · {String(group.season)} · cost per acre {group.cost_per_acre==null?'unavailable':`₹${String(group.cost_per_acre)}`} · cost per quintal {group.cost_per_quintal==null?'unavailable':`₹${String(group.cost_per_quintal)}`}</p>)}</div>{items.filter(item=>[item.description,item.notes,item.amount,item.unit_price,item.incurred_on,item.sold_on].some(hasFinanceValue)).map((item,index)=>{const title=financeLabel(recordKind==='expenses'?item.description:item.notes,recordKind==='expenses'?'Farm expense':'Farm sale');const amountValue=financeLabel(recordKind==='expenses'?item.amount:item.unit_price,'Amount not recorded');const dateValue=financeLabel(recordKind==='expenses'?item.incurred_on:item.sold_on,'Date not recorded');const category=financeLabel(item.category,recordKind==='expenses'?'Expense':'Sale');return <article className="finance-record" key={financeLabel(item.id,`record-${index}`)}><div className="finance-record-copy"><strong>{title}</strong><span>{category.replace(/_/g,' ')}</span><small>{dateValue}{recordKind==='sales'&&item.quantity!=null?` · ${financeLabel(item.quantity,'')} ${financeLabel(item.quantity_unit,'')}`:''}</small></div><div className="finance-record-actions"><strong>₹{amountValue}</strong><div><button type="button" onClick={()=>editFinanceRecord(item)}>Edit</button><button type="button" onClick={()=>deleteFinanceRecord(financeLabel(item.id,''))}>Delete</button></div></div></article>})}</>}
    {page==='diary' && <><h2>Farm diary</h2><form className="inline-form" onSubmit={submit}><textarea required maxLength={4000} placeholder="Record an observation" value={diaryNote} onChange={e=>setDiaryNote(e.target.value)}/><button className="primary">Save entry</button></form>{items.map(item=><article className="platform-item" key={String(item.id)}>{String(item.entry_date)} · {String(item.notes)}</article>)}</>}
    {page==='market' && <div className="mandi-page"><header><div><span className="eyebrow">AGMARKNET · data.gov.in</span><h2>Mandi Price Intelligence</h2><p>Observed wholesale market prices. They are not guaranteed farm-gate prices or MSP rates.</p></div><a href="https://www.enam.gov.in/web/dashboard/trade-data" target="_blank" rel="noreferrer">Open official e-NAM trade data ↗</a></header>
      <div className="mandi-status" role="status">{marketStatus.configured?'data.gov.in credentials configured':'Official data feed not configured'} · Latest observation: {String(marketStatus.newest_observation||'none available')} · Stored observations: {String(marketStatus.records??0)}{marketItems[0]?.freshness==='stale'?' · Showing stale observations':''}</div>
      <div className="mandi-filters"><label>Crop / commodity<input list="market-commodities" value={marketFilters.commodity} onChange={e=>setMarketFilters({...marketFilters,commodity:e.target.value})} placeholder="Choose or type a crop"/><datalist id="market-commodities">{marketChoices.commodities.map(v=><option key={v} value={v}/>)}</datalist></label><label>Variety<input list="market-varieties" value={marketFilters.variety} onChange={e=>setMarketFilters({...marketFilters,variety:e.target.value})} placeholder="All varieties"/><datalist id="market-varieties">{marketChoices.varieties.map(v=><option key={v} value={v}/>)}</datalist></label><label>Grade<input list="market-grades" value={marketFilters.grade} onChange={e=>setMarketFilters({...marketFilters,grade:e.target.value})} placeholder="All grades"/><datalist id="market-grades">{marketChoices.grades.map(v=><option key={v} value={v}/>)}</datalist></label><label>State<input list="market-states" value={marketFilters.state} onChange={e=>setMarketFilters({...marketFilters,state:e.target.value})} placeholder="All states"/><datalist id="market-states">{marketChoices.states.map(v=><option key={v} value={v}/>)}</datalist></label>{(['district','mandi'] as const).map(key=><label key={key}>{key==='mandi'?'Mandi':'District'}<input value={marketFilters[key]} onChange={e=>setMarketFilters({...marketFilters,[key]:e.target.value})} placeholder={`Filter ${key}`}/></label>)}<label>From<input type="date" value={marketFilters.date_from} onChange={e=>setMarketFilters({...marketFilters,date_from:e.target.value})}/></label><label>To<input type="date" value={marketFilters.date_to} onChange={e=>setMarketFilters({...marketFilters,date_to:e.target.value})}/></label></div>
      {marketBusy&&<p role="status">Loading mandi observations…</p>}
      <div className="mandi-cards"><article><small>Latest observed modal</small><strong>{marketItems[0]?.modal_price?`₹${marketItems[0].modal_price}`:'—'}</strong><span>{marketItems[0]?`Min ₹${marketItems[0].minimum_price??'—'} · Max ₹${marketItems[0].maximum_price??'—'}`:'No observation'} / {marketItems[0]?.price_unit||'INR/quintal'}</span><span>{marketItems[0]?`Observed ${marketItems[0].observed_on}`:''}</span></article><article><small>7-day trend</small><strong>{marketTrends['7_day']==null?'—':`${marketTrends['7_day']>0?'+':''}${marketTrends['7_day']}%`}</strong><span>Based on available observed dates</span></article><article><small>30-day trend</small><strong>{marketTrends['30_day']==null?'—':`${marketTrends['30_day']>0?'+':''}${marketTrends['30_day']}%`}</strong><span>Based on available observed dates</span></article></div>
      {marketFilters.commodity&&marketFilters.mandi&&<p>Daily change: {marketTrends.daily_change==null?'insufficient observations':`${marketTrends.daily_change>0?'+':''}${marketTrends.daily_change}%`}. Year-over-year seasonal comparisons appear only when a comparable observation from roughly one year earlier exists.</p>}
      <section className="mandi-panel"><h3>Historical modal price</h3>{marketPoints.length>1?<><svg className="mandi-chart" viewBox="0 0 720 190" role="img" aria-label="Historical mandi modal prices"><polyline fill="none" stroke="#2b6844" strokeWidth="3" points={marketPoints.map((point,index)=>`${index*700/Math.max(1,marketPoints.length-1)+10},${180-((point.modal_price-Math.min(...marketPoints.map(p=>p.modal_price)))/(Math.max(...marketPoints.map(p=>p.modal_price))-Math.min(...marketPoints.map(p=>p.modal_price))||1))*155}`).join(' ')}/></svg><p>{marketPoints[0].date} → {marketPoints[marketPoints.length-1].date} · ₹/quintal</p></>:<p>No historical observations available for these filters.</p>}</section>
      <section className="mandi-panel"><h3>Comparable mandis</h3><button type="button" onClick={compareMandis} disabled={marketCompareBusy||!marketFilters.commodity}>{marketCompareBusy?'Comparing...':'Compare available mandis'}</button>{marketCompare.length?marketCompare.map(row=><p key={`${row.mandi}-${row.observed_on}`}>{row.mandi}, {row.state} · ₹{row.modal_price}/{row.price_unit} · {row.observed_on}</p>):<p>{marketCompareMessage||(!marketFilters.commodity?'Choose a commodity before comparing mandis.':'Run the comparison to rank matching observations.')}</p>}</section>
      <section className="mandi-panel"><h3>Forecast</h3>{marketForecast?.status==='available'?<><p>{String(marketForecast.model)} · walk-forward MAE ₹{String((marketForecast.backtest as Record<string,unknown>)?.mae)}/quintal</p><p>{String(marketForecast.warning)}</p></>:<p>Insufficient history for a reliable forecast. {String(marketForecast?.message||'No validated forecast is available.')}</p>}</section>
      <section className="mandi-panel"><h3>Latest observations</h3>{marketState==='ready'?marketItems.map(row=><article className="platform-item" key={row.id}><strong>{row.commodity}{row.variety?` · ${row.variety}`:''}</strong><p>{row.mandi}, {row.district}, {row.state} · {row.observed_on}</p><small>Min ₹{row.minimum_price??'—'} · Modal ₹{row.modal_price??'—'} · Max ₹{row.maximum_price??'—'} / {row.price_unit} · {row.freshness}</small><p><a href={row.source_url} target="_blank" rel="noreferrer">Source: data.gov.in</a></p></article>):marketState==='loading'?<p role="status">Loading observations…</p>:marketState==='error'?<p role="alert">Could not load market observations. {notice}</p>:<p role="status">{marketEmptyMessage}</p>}</section>
      <p className="mandi-note">Prices are reported at mandi level. MSP is separate and is not represented by these observations. Seasonal comparison appears only when sufficient multi-year data exists.</p>
    </div>}
    {page==='voice' && <><h2>Ask the agriculture assistant</h2><p>Voice stays in your browser. Speech input/output follows the selected language where your browser supports it.</p><label>Language<select value={chatLanguage} onChange={e=>setChatLanguage(e.target.value as 'en'|'hi'|'hinglish')}><option value="en">English</option><option value="hi">Hindi</option><option value="hinglish">Hinglish</option></select></label><div className="chat-input-row"><input value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ask in your selected language"/><button className="mic-button" type="button" onClick={speakQuestion} aria-label="Dictate your question" title="Dictate your question"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="2.5" width="6" height="12" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V22m-4 0h8"/></svg></button><button type="button" className="primary" onClick={ask}>Send</button></div>{answer&&<p className="assistant-answer">{answer}</p>}</>}
    {page==='profile' && <><h2>Farmer profile</h2><form className="inline-form" onSubmit={saveProfile}><label>Name<input required maxLength={120} value={profile.name||''} onChange={e=>setProfile({...profile,name:e.target.value})}/></label><label>State<input maxLength={100} value={profile.state||''} onChange={e=>setProfile({...profile,state:e.target.value})}/></label><label>District<input maxLength={100} value={profile.district||''} onChange={e=>setProfile({...profile,district:e.target.value})}/></label><label>Language<select value={profile.preferred_language||'en'} onChange={e=>setProfile({...profile,preferred_language:e.target.value})}><option value="en">English</option><option value="hi">Hindi</option><option value="hinglish">Hinglish</option></select></label><button className="primary">Save profile</button></form><label><input type="checkbox" checked={Boolean(profile.location_consent_at)} onChange={e=>changeLocationConsent(e.target.checked)}/> I consent to saving my location for farm alerts.</label><p>Browser permission is requested only when you choose the location weather action. Unchecking deletes the saved coordinates.</p></>}
  </section>;
}
