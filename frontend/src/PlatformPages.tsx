import { FormEvent, useEffect, useRef, useState } from 'react';

type Page = 'tasks' | 'schemes' | 'money' | 'diary' | 'market' | 'voice';
type ChatMessage = { role: 'user' | 'assistant'; content: string };
type Item = Record<string, unknown>;
type MarketEstimateRecord = { commodity:string; variety:string|null; grade:string|null; state:string; district:string; market:string; reporting_date:string; minimum_price:string|null; modal_price:string|null; maximum_price:string|null; source_price_unit:string; source:string; source_url:string; fetched_at:string; freshness:string; stale:boolean; quantity_kg:string; minimum_price_per_kg:string|null; modal_price_per_kg:string|null; maximum_price_per_kg:string|null; minimum_value:string|null; expected_value:string|null; maximum_value:string|null };
type MarketEstimate = { status:string; provider:string; source_url:string; served_from?:string; retrieved_at:string; query:{commodity:string;state:string|null;district:string|null;market:string|null;variety:string|null;quantity:string;unit:string;quantity_kg:string}; comparison_note:string|null; message?:string; price_note:string; items:MarketEstimateRecord[] };
type MarketOptions = { status?:string; commodities:string[]; states:string[]; districts:string[]; markets:string[]; varieties:string[]; grades:string[]; coverage?:{records?:number; newest_observation?:string|null; last_fetched?:string|null} };
type SpeechRecognitionFailure = { error: string };
type SpeechRecognizer = { lang: string; onresult: ((event: SpeechRecognitionEvent) => void) | null; onerror: ((event: SpeechRecognitionFailure) => void) | null; onstart: (() => void) | null; onend: (() => void) | null; start: () => void };
type SpeechRecognizerConstructor = new () => SpeechRecognizer;

export function AssistantLauncher({onClick}:{onClick:()=>void}) {
  return <button type="button" className="cropai-launcher" onClick={onClick} aria-label="Open CropAI chat assistant" title="Chat with CropAI">
    <span className="cropai-launcher-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M6 7.5h20v14H15l-6 4v-4H6z"/><path d="M11 16c1.2-4.4 4.7-7.2 10.7-8-1.1 5.8-4.3 9.2-9 9.2"/></svg></span>
    <span className="cropai-launcher-copy"><strong>CropAI</strong><small>Chat with us</small></span><span className="cropai-launcher-pulse" aria-hidden="true"/>
  </button>;
}

function financeLabel(value: unknown, fallback: string): string {
  if (value === null || value === undefined) return fallback;
  const label = String(value).trim();
  if (!label || /^(undefined|null|nan)$/i.test(label)) return fallback;
  return label;
}

function hasFinanceValue(value: unknown): boolean {
  return financeLabel(value, '') !== '';
}

function formatINR(value: string|null|undefined): string {
  if(value===null||value===undefined||value==='')return 'Not reported';
  return new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(Number(value));
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

export function PlatformPages({ userId, initialPage = 'tasks' }: { userId: number; initialPage?: Page }) {
  const [page, setPage] = useState<Page>(initialPage);
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
  const [voiceMessages, setVoiceMessages] = useState<ChatMessage[]>([]);
  const [voiceInput, setVoiceInput] = useState('');
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(true);
  const voiceMessagesEnd = useRef<HTMLDivElement|null>(null);
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
  const [estimateForm, setEstimateForm] = useState({commodity:'',quantity:'',unit:'quintal',state:'',district:'',market:'',variety:''});
  const [regionalCropSearch, setRegionalCropSearch] = useState('');
  const [regionalCropPickerOpen, setRegionalCropPickerOpen] = useState(false);
  const [estimate, setEstimate] = useState<MarketEstimate|null>(null);
  const [estimateBusy, setEstimateBusy] = useState(false);
  const [estimateError, setEstimateError] = useState('');
  const [estimateSort, setEstimateSort] = useState<'modal'|'gross'>('modal');
  const [estimateMeasure, setEstimateMeasure] = useState<'expected'|'minimum'|'maximum'>('expected');
  const [marketOptions, setMarketOptions] = useState<MarketOptions>({commodities:[],states:[],districts:[],markets:[],varieties:[],grades:[]});
  const [marketOptionsError, setMarketOptionsError] = useState('');

  useEffect(() => {
    setNotice('');
    const path = page === 'tasks' ? '/farm/actions/today' : page === 'money' ? `/farm/${recordKind}` : page === 'diary' ? '/farm/diary' : null;
    if (page !== 'tasks') setTaskSchemeDeadlines([]);
    if (page === 'tasks') request<{ items: Item[]; scheme_deadlines?: Item[] }>(path!).then((result) => { setItems(result.items); setTaskSchemeDeadlines(result.scheme_deadlines || []); }).catch((error: Error) => setNotice(error.message));
    else if (path) request<{ items: Item[] }>(path).then((result) => setItems(result.items)).catch((error: Error) => setNotice(error.message));
    if(page==='money') {
      request<{items:Item[]}>(`/users/${userId}/farms`).then(result=>setFinanceFarms(result.items)).catch((error:Error)=>setNotice(error.message));
      request<Record<string,unknown>>('/farm/profit-summary').then(setFinanceSummary).catch((error:Error)=>setNotice(error.message));
    }
  }, [page, recordKind]);

  useEffect(() => {
    voiceMessagesEnd.current?.scrollIntoView({behavior:'smooth',block:'end'});
  }, [voiceMessages, voiceBusy]);

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
    if(page!=='market')return;
    let active=true;
    setMarketOptionsError('');
    request<MarketOptions>('/markets/options').then(result=>{
      if(active) setMarketOptions({...result,commodities:result.commodities||[],states:result.states||[],districts:result.districts||[],markets:result.markets||[],varieties:result.varieties||[],grades:result.grades||[]});
    }).catch((error:Error)=>{
      if(active) setMarketOptionsError(error.message);
    });
    return ()=>{active=false;};
  },[page]);

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

  async function findMarketPrices(event:FormEvent){
    event.preventDefault();
    if(!estimateForm.commodity.trim()||!estimateForm.quantity.trim()){
      setEstimateError('Enter a crop and harvest quantity. Leave state and district blank to search across India.');return;
    }
    const feedLabel=(value:string)=>value.trim().toLocaleLowerCase().replace(/\b[a-z]/g,letter=>letter.toLocaleUpperCase());
    const stateAliases:Record<string,string>={'gujrat':'Gujarat','orissa':'Odisha'};
    const commodity=feedLabel(estimateForm.commodity);
    const state=stateAliases[estimateForm.state.trim().toLocaleLowerCase()]||feedLabel(estimateForm.state);
    const district=feedLabel(estimateForm.district);
    const market=feedLabel(estimateForm.market);
    if(commodity!==estimateForm.commodity.trim()||state!==estimateForm.state.trim()||district!==estimateForm.district.trim())setEstimateForm(current=>({...current,commodity,state,district}));
    const params=new URLSearchParams({commodity,quantity:estimateForm.quantity.trim(),unit:estimateForm.unit});
    if(state)params.set('state',state);
    if(district)params.set('district',district);
    if(market)params.set('market',market);
    if(estimateForm.variety.trim())params.set('variety',feedLabel(estimateForm.variety));
    setEstimateBusy(true);setEstimateError('');setEstimate(null);
    try{const result=await request<MarketEstimate>(`/markets/estimate?${params}`);setEstimate(result);}
    catch(error){setEstimateError((error as Error).message);}
    finally{setEstimateBusy(false);}
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

  async function deleteTask(id:string){
    if(!window.confirm('Delete this task? This cannot be undone.'))return;
    try{
      await request(`/tasks/${encodeURIComponent(id)}`,{method:'DELETE'});
      const result=await request<{items:Item[];scheme_deadlines?:Item[]}>('/farm/actions/today');
      setItems(result.items);setTaskSchemeDeadlines(result.scheme_deadlines||[]);setNotice('Task deleted.');
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

  async function ask(event?: FormEvent) {
    event?.preventDefault();
    const message = voiceInput.trim();
    if (!message || voiceBusy) return;
    setNotice('');
    setVoiceInput('');
    setVoiceMessages(current => [...current, {role:'user', content:message}]);
    setVoiceBusy(true);
    try {
      const result = await request<{ answer: string }>('/chat', { method: 'POST', body: JSON.stringify({ message, language: chatLanguage, conversation: voiceMessages.slice(-8) }) });
      setVoiceMessages(current => [...current, {role:'assistant', content:result.answer}]);
      if (speakReplies && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utterance=new SpeechSynthesisUtterance(result.answer);
        utterance.lang=chatLanguage==='en'?'en-IN':'hi-IN';
        window.speechSynthesis.speak(utterance);
      }
    } catch (error) { setNotice((error as Error).message); setVoiceMessages(current=>current.slice(0,-1)); setVoiceInput(message); }
    finally { setVoiceBusy(false); }
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

  function speakQuestion() {
    const speech = window as typeof window & { SpeechRecognition?: SpeechRecognizerConstructor; webkitSpeechRecognition?: SpeechRecognizerConstructor };
    const Recognition = speech.SpeechRecognition || speech.webkitSpeechRecognition;
    if (!Recognition) { setNotice('Voice input is not supported in this browser. Try Chrome or Edge, or type your question.'); return; }
    if (!window.isSecureContext) { setNotice('Microphone access requires a secure page. Open the app using localhost or HTTPS, then allow microphone access.'); return; }
    const recognition = new Recognition();
    recognition.lang = chatLanguage==='en'?'en-IN':'hi-IN';
    recognition.onstart = () => { setNotice('Listening… speak your question now.'); setIsListening(true); };
    recognition.onresult = (event) => setVoiceInput(event.results[0][0].transcript);
    recognition.onerror = (event) => {
      const messages:Record<string,string>={
        'not-allowed':'Microphone access is blocked. Allow microphone access for this site in your browser’s site settings, and check Windows microphone privacy settings.',
        'service-not-allowed':'The browser speech service is blocked. Check browser microphone permissions or use Chrome/Edge on localhost or HTTPS.',
        'audio-capture':'No microphone is available. Connect or enable a microphone, then try again.',
        'network':'The browser speech-recognition service could not connect. Check your internet connection, or type your question.',
        'no-speech':'No speech was detected. Tap the mic and speak clearly after the listening prompt.',
        'language-not-supported':'Speech recognition does not support the selected language in this browser. Choose another language or type your question.',
        'aborted':'Voice input was cancelled.',
      };
      setNotice(messages[event.error]||`Voice input failed (${event.error}). Check microphone permission, or type your question.`);
      setIsListening(false);
    };
    recognition.onend = () => setIsListening(false);
    try { recognition.start(); }
    catch (error) {
      setIsListening(false);
      const reason=(error as Error).name;
      setNotice(reason==='NotAllowedError'||reason==='SecurityError'?'Microphone access is blocked. Allow it in your browser’s site settings and use localhost or HTTPS.':'Could not start the microphone. Check that another app is not using it, then try again.');
    }
  }

  const estimateRows=[...(estimate?.items||[])].sort((a,b)=>{
    const key=estimateSort==='gross'?(estimateMeasure==='expected'?'expected_value':`${estimateMeasure}_value` as 'minimum_value'|'maximum_value'):'modal_price';
    const left=a[key]===null?Number.NEGATIVE_INFINITY:Number(a[key]);
    const right=b[key]===null?Number.NEGATIVE_INFINITY:Number(b[key]);
    return right-left;
  });
  const estimateSummaryField=`${estimateMeasure}_value` as 'expected_value'|'minimum_value'|'maximum_value';
  const marketCropChoices=marketOptions.commodities.map(commodity=>({commodity,label:commodity}));
  const filteredMarketCropChoices=marketCropChoices.filter(choice=>choice.label.toLocaleLowerCase().includes(regionalCropSearch.trim().toLocaleLowerCase())).slice(0,12);
  const marketCoverage=marketOptions.coverage;
  const estimateSummary=estimateForm.market.trim()?estimateRows.find(row=>row.market.toLocaleLowerCase()===estimateForm.market.trim().toLocaleLowerCase()):estimateRows.filter(row=>row[estimateSummaryField]!==null).sort((a,b)=>Number(b[estimateSummaryField])-Number(a[estimateSummaryField]))[0];
  const estimateSummaryValue=estimateSummary?.[`${estimateMeasure}_value` as 'expected_value'|'minimum_value'|'maximum_value'];
  const highestModal=estimateRows.filter(row=>row.modal_price!==null).reduce<MarketEstimateRecord|null>((highest,row)=>!highest||Number(row.modal_price)>Number(highest.modal_price)?row:highest,null);

  return <section className="platform-hub">
    <nav className="platform-nav" aria-label="Farm tools">
      {([['tasks','Tasks'],['schemes','Schemes'],['money','Farm finances'],['diary','Diary'],['market','Mandi Price Intelligence']] as [Page,string][]).map(([id,label]) => <button key={id} className={page===id?'selected':''} onClick={()=>setPage(id)}>{label}</button>)}
    </nav>
    <AssistantLauncher onClick={()=>setPage('voice')}/>
    {notice && <p className="notice" role="status">{notice}</p>}
    {page==='tasks' && <><h2>Today’s farm action plan</h2><p>Checklist items are generated from saved crop context and general care guidance. Weather and scheme deadlines are included only when verified inputs exist.</p><form className="inline-form" onSubmit={submit}><input required maxLength={160} placeholder="Add a task title" value={taskTitle} onChange={e=>setTaskTitle(e.target.value)}/><input required maxLength={2000} placeholder="What needs doing?" value={taskNote} onChange={e=>setTaskNote(e.target.value)}/><button className="primary">Save task</button></form>{taskSchemeDeadlines.length>0&&<section className="scheme-panel daily-deadlines"><h3>Verified scheme deadlines - next 30 days</h3><p>Only recently checked official records for your location are shown. Confirm details with the scheme authority.</p>{taskSchemeDeadlines.map(deadline=><article key={String(deadline.scheme_id)}><strong>{financeLabel(deadline.official_name,'Scheme name unavailable')}</strong><span>Due {financeLabel(deadline.deadline,'Date unavailable')} {Boolean(deadline.application_status)&&<em>- {financeLabel(deadline.application_status,'Status unavailable')}</em>}</span><a href={String(deadline.official_application_url)} target="_blank" rel="noreferrer">Open official application page</a></article>)}</section>}{items.map(item=><article className="platform-item" key={String(item.id)}><strong>{financeLabel(item.title,'Untitled task')}</strong><p>{financeLabel(item.recommendation,'No task details provided.')}</p>{financeLabel(item.reason,'')&&<p>{financeLabel(item.reason,'')}</p>}<small>{financeLabel(item.state,'State unavailable')} · {financeLabel(item.evidence_quality,'Evidence not recorded')}{item.due_date?` · Due ${financeLabel(item.due_date,'Date unavailable')}`:''}</small>{item.state==='open'&&<div className="task-actions"><button type="button" onClick={()=>updateTaskState(String(item.id),'complete')}>Mark complete</button><button type="button" onClick={()=>updateTaskState(String(item.id),'dismiss')}>Dismiss</button></div>}<div className="task-actions"><button type="button" className="task-delete" onClick={()=>deleteTask(String(item.id))}>Delete task</button></div></article>)}</>}
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
      {schemeDeadlines.length>0&&<section className="scheme-panel"><h3>Verified upcoming deadlines</h3>{schemeDeadlines.map(deadline=><p key={String(deadline.scheme_id)}><strong>{financeLabel(deadline.official_name,'Scheme name unavailable')}</strong> · {financeLabel(deadline.deadline,'Date unavailable')} · <a href={String(deadline.official_application_url||'#')} target="_blank" rel="noreferrer">Official application page</a></p>)}</section>}
      <section className="scheme-list"><h3>Scheme registry</h3>{schemeLoading?<p role="status">Loading schemes...</p>:items.length===0?<p>No schemes match these filters. Clear the filters to browse the full registry.</p>:items.map(item=><article className="scheme-card" key={String(item.scheme_id)}><div className="scheme-card-top"><div><span className={`scheme-status ${String(item.verification_status)}`}>{String(item.verification_status)}</span><h4>{String(item.official_name)}</h4></div><button type="button" onClick={()=>toggleSavedScheme(String(item.scheme_id))}>{savedSchemeIds.includes(String(item.scheme_id))?'Saved ✓':'Save scheme'}</button></div><p>{String(item.description||'Purpose and eligibility details have not been verified yet. Review the official source before relying on this scheme information.')}</p>{Boolean(item.benefit_description)&&<p><strong>Benefit:</strong> {String(item.benefit_description)}</p>}<div className="scheme-facts"><span>Application status: <strong>{String(item.application_status||'unknown')}</strong></span><span>{item.deadline?`Deadline: ${String(item.deadline)}`:'Deadline not verified — check the official portal.'}</span><span>Last source check: {item.last_checked_at?String(item.last_checked_at):'Not recorded'}</span></div><div className="scheme-actions"><button type="button" onClick={()=>openScheme(String(item.scheme_id))} disabled={schemeDetailBusy}>{schemeDetailBusy?'Loading...':'View scheme details'}</button><a href={String(item.official_application_url||item.official_source_url||item.url)} target="_blank" rel="noreferrer">Official portal ↗</a></div></article>)}</section>
      {schemeDetail&&<section className="scheme-panel scheme-detail"><div className="scheme-card-top"><div><span className="eyebrow">SCHEME DETAILS</span><h3>{String(schemeDetail.official_name)}</h3></div><button type="button" onClick={()=>setSchemeDetail(null)}>Close details</button></div><p>{String(schemeDetail.description||'No verified description is currently recorded.')}</p><p><strong>Eligibility criteria:</strong> {schemeQuestions(schemeDetail.eligibility_rules).map(rule=>rule.label).join(' ')||'No verified structured criteria recorded.'}</p><p><strong>Exclusions:</strong> {Array.isArray(schemeDetail.exclusion_rules)?(schemeDetail.exclusion_rules as unknown[]).map(String).join('; '):'No verified exclusions recorded.'}</p><p><strong>Application status:</strong> {String(schemeDetail.application_status)} · <strong>Deadline:</strong> {schemeDetail.deadline?String(schemeDetail.deadline):'Not verified'}</p><h4>Documents checklist</h4>{Array.isArray(schemeDetail.document_checklist)&&(schemeDetail.document_checklist as unknown[]).map((doc,index)=>{const data=doc as Record<string,unknown>;const label=String(data.item||`Document ${index+1}`);const id=String(schemeDetail.scheme_id);return <label className="scheme-checklist" key={label}><input type="checkbox" disabled={!savedSchemeIds.includes(id)} checked={Boolean(schemeChecklists[id]?.[label])} onChange={e=>updateSchemeChecklist(id,label,e.target.checked)}/><span><strong>{label}</strong><small>{String(data.note||data.status||'Confirm requirements on the official portal.')}</small></span></label>})}{!savedSchemeIds.includes(String(schemeDetail.scheme_id))&&Array.isArray(schemeDetail.document_checklist)&&schemeDetail.document_checklist.length>0&&<small>Save this scheme to track document checklist progress.</small>}<h4>How to apply</h4>{Array.isArray(schemeDetail.application_procedure)?<ol>{(schemeDetail.application_procedure as unknown[]).map((step,index)=><li key={index}>{String(step)}</li>)}</ol>:<p>Application steps are not verified. Use the official portal.</p>}<p><a href={String(schemeDetail.official_application_url||schemeDetail.official_source_url)} target="_blank" rel="noreferrer">Open official scheme source ↗</a></p>{Array.isArray(schemeDetail.updates)&&<><h4>Recorded source updates</h4>{(schemeDetail.updates as unknown[]).length?(schemeDetail.updates as unknown[]).map((update,index)=><p key={index}>Reviewed {String((update as Record<string,unknown>).recorded_at)} · <a href={String((update as Record<string,unknown>).evidence_url)} target="_blank" rel="noreferrer">Evidence ↗</a></p>):<small>No source change history is recorded.</small>}</>}</section>}
    </>}
    {page==='money' && <><h2>Farm finances</h2><div className="platform-nav"><button className={recordKind==='expenses'?'selected':''} onClick={()=>{setRecordKind('expenses');setFinanceEditId(null);}}>Expenses</button><button className={recordKind==='sales'?'selected':''} onClick={()=>{setRecordKind('sales');setFinanceEditId(null);}}>Sales</button></div><form className="inline-form" onSubmit={submit}><label>Farm<select value={financeFarmId} onChange={e=>{setFinanceFarmId(e.target.value);setFinanceCropId('');}}><option value="">Unassigned</option>{financeFarms.map(f=><option key={String(f.id)} value={String(f.id)}>{financeLabel(f.name,'Unnamed farm')}</option>)}</select></label><label>Crop<select value={financeCropId} onChange={e=>setFinanceCropId(e.target.value)}><option value="">Unassigned</option>{financeCrops.map(c=><option key={String(c.id)} value={String(c.id)}>{financeLabel(c.crop_name,'Unnamed crop')}{c.season?` · ${financeLabel(c.season,'Season not recorded')}`:''}</option>)}</select></label><label>Season<input maxLength={80} value={financeSeason} onChange={e=>setFinanceSeason(e.target.value)} placeholder="e.g. Kharif 2026"/></label>{recordKind==='expenses'&&<label>Category<select value={financeCategory} onChange={e=>setFinanceCategory(e.target.value)}>{[['seeds','Seeds'],['fertilizer','Fertilizer'],['crop_protection','Crop protection'],['labor','Labor'],['machinery','Machinery and fuel'],['irrigation','Irrigation'],['equipment_rental','Equipment rental'],['transport','Transport'],['other','Other']].map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>}{recordKind==='sales'&&<><label>Quantity<input required type="number" min="0.001" step="0.001" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label><label>Quantity unit<select value={financeQuantityUnit} onChange={e=>setFinanceQuantityUnit(e.target.value)}><option value="kg">kg</option><option value="quintal">quintal</option><option value="tonne">tonne</option></select></label><label>Price per unit<select value={financePriceUnit} onChange={e=>setFinancePriceUnit(e.target.value)}><option value="kg">INR/kg</option><option value="quintal">INR/quintal</option><option value="tonne">INR/tonne</option></select></label><label>Selling costs (INR)<input type="number" min="0" step="0.01" value={financeSellingCost} onChange={e=>setFinanceSellingCost(e.target.value)}/></label></>}<label>{recordKind==='expenses'?'Description':'Sale notes'}<input required maxLength={recordKind==='expenses'?500:1000} value={description} onChange={e=>setDescription(e.target.value)}/></label><label>{recordKind==='expenses'?'Amount (INR)':'Price (INR per selected unit)'}<input required type="number" min="0" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></label><label>Date<input required type="date" value={financeDate} onChange={e=>setFinanceDate(e.target.value)}/></label><button className="primary">{financeEditId?'Update':'Record'} {recordKind==='expenses'?'expense':'sale'}</button>{financeEditId&&<button type="button" onClick={()=>setFinanceEditId(null)}>Cancel edit</button>}</form><div className="finance-summary"><h3>Recorded farm return</h3><p>Expenses ₹{financeLabel(financeSummary.expenses,'0')} · Sales revenue ₹{financeLabel(financeSummary.gross_revenue,'0')} · Selling costs ₹{financeLabel(financeSummary.selling_costs,'0')} · Net return ₹{financeLabel(financeSummary.net_return,'0')}</p><p>Break-even price: {financeSummary.break_even_price_per_quintal?`₹${String(financeSummary.break_even_price_per_quintal)}/quintal`:'enter expected saleable output below'}</p><form className="inline-form" onSubmit={async e=>{e.preventDefault();try{await refreshProfit();}catch(error){setNotice((error as Error).message);}}}><label>Expected saleable output<input type="number" min="0.001" step="0.001" value={expectedOutput} onChange={e=>setExpectedOutput(e.target.value)}/></label><label>Output unit<select value={financeQuantityUnit} onChange={e=>setFinanceQuantityUnit(e.target.value)}><option value="kg">kg</option><option value="quintal">quintal</option><option value="tonne">tonne</option></select></label><label>Yield change %<input type="number" min="-100" max="500" value={yieldChange} onChange={e=>setYieldChange(e.target.value)}/></label><label>Price change %<input type="number" min="-100" max="500" value={priceChange} onChange={e=>setPriceChange(e.target.value)}/></label><button>Calculate scenario</button></form>{Boolean(financeSummary.scenario)&&<p>Scenario estimated net return: {financeLabel((financeSummary.scenario as Record<string,unknown>).estimated_net_return,'incomplete; record a sale price first')}</p>}{Array.isArray(financeSummary.breakdown)&&financeSummary.breakdown.map((group,index)=><p key={index}>{financeLabel(group.crop,'Crop not linked')} · {financeLabel(group.season,'Season not recorded')} · cost per acre {group.cost_per_acre==null?'unavailable':`₹${financeLabel(group.cost_per_acre,'unavailable')}`} · cost per quintal {group.cost_per_quintal==null?'unavailable':`₹${financeLabel(group.cost_per_quintal,'unavailable')}`}</p>)}</div>{items.filter(item=>[item.description,item.notes,item.amount,item.unit_price,item.incurred_on,item.sold_on].some(hasFinanceValue)).map((item,index)=>{const title=financeLabel(recordKind==='expenses'?item.description:item.notes,recordKind==='expenses'?'Farm expense':'Farm sale');const amountValue=financeLabel(recordKind==='expenses'?item.amount:item.unit_price,'Amount not recorded');const dateValue=financeLabel(recordKind==='expenses'?item.incurred_on:item.sold_on,'Date not recorded');const category=financeLabel(item.category,recordKind==='expenses'?'Expense':'Sale');return <article className="finance-record" key={financeLabel(item.id,`record-${index}`)}><div className="finance-record-copy"><strong>{title}</strong><span>{category.replace(/_/g,' ')}</span><small>{dateValue}{recordKind==='sales'&&item.quantity!=null?` · ${financeLabel(item.quantity,'')} ${financeLabel(item.quantity_unit,'')}`:''}</small></div><div className="finance-record-actions"><strong>₹{amountValue}</strong><div><button type="button" onClick={()=>editFinanceRecord(item)}>Edit</button><button type="button" onClick={()=>deleteFinanceRecord(financeLabel(item.id,''))}>Delete</button></div></div></article>})}</>}
    {page==='diary' && <><h2>Farm diary</h2><form className="inline-form" onSubmit={submit}><textarea required maxLength={4000} placeholder="Record an observation" value={diaryNote} onChange={e=>setDiaryNote(e.target.value)}/><button className="primary">Save entry</button></form>{items.map(item=><article className="platform-item" key={String(item.id)}>{financeLabel(item.entry_date,'Date not recorded')} · {financeLabel(item.notes,'No note recorded')}</article>)}</>}
    {page==='market' && <div className="mandi-page"><header><div><span className="eyebrow">AGMARKNET · data.gov.in</span><h2>Mandi Price Intelligence</h2><p>Compare reported market prices and estimate your harvest's gross value.</p></div><a href="https://www.enam.gov.in/web/dashboard/trade-data" target="_blank" rel="noreferrer">Open official e-NAM trade data ↗</a></header>
      <section className="market-estimator" aria-labelledby="estimate-heading">
        <div className="market-estimator-heading"><div><span className="eyebrow">HARVEST VALUE CHECK</span><h3 id="estimate-heading">Compare reported markets across India</h3><p>Search any commodity currently reported by AGMARKNET, or add a state and district to narrow the results. Reports are updated daily.</p></div><span className="provider-mark">DATA.GOV.IN<br/>AGMARKNET</span></div>
        <label className="estimate-demo">Choose a commodity in the current feed<select value="" onChange={event=>{const commodity=event.target.value;if(!commodity)return;setEstimateForm({...estimateForm,commodity,quantity:estimateForm.quantity||'12',unit:'kg',state:'',district:'',market:'',variety:''});setEstimate(null);setEstimateError('');}}><option value="">{marketOptions.commodities.length?`${marketOptions.commodities.length} commodities available`:'Commodity list is loading…'}</option>{marketOptions.commodities.map(commodity=><option key={commodity} value={commodity}>{commodity}</option>)}</select><small>{marketCoverage?.records?`${Number(marketCoverage.records).toLocaleString('en-IN')} AGMARKNET observations are stored${marketCoverage.newest_observation?`; newest report ${marketCoverage.newest_observation}`:''}.`:'Loading the latest commodity coverage from the mandi feed.'} Prices change as the feed updates.</small></label>
        {marketOptionsError&&<p className="estimate-error" role="alert">Commodity list unavailable: {marketOptionsError}. You can still type a commodity name below.</p>}
        <div className="estimate-demo regional-picker">
          <label htmlFor="regional-crop-search">Search all available commodities</label>
          <input id="regional-crop-search" type="search" role="combobox" aria-autocomplete="list" aria-expanded={regionalCropPickerOpen} aria-controls="regional-crop-suggestions" value={regionalCropSearch} onFocus={()=>setRegionalCropPickerOpen(true)} onChange={event=>{setRegionalCropSearch(event.target.value);setRegionalCropPickerOpen(true);}} onKeyDown={event=>{if(event.key==='Escape')setRegionalCropPickerOpen(false);if(event.key==='Enter'&&regionalCropPickerOpen&&filteredMarketCropChoices[0]){event.preventDefault();const choice=filteredMarketCropChoices[0];setEstimateForm(current=>({...current,commodity:choice.commodity,quantity:current.quantity||'12',unit:'kg',state:'',district:'',market:'',variety:''}));setRegionalCropSearch(choice.label);setRegionalCropPickerOpen(false);setEstimate(null);setEstimateError('');}}} placeholder="Search onion, wheat, tomato, paddy…" autoComplete="off" />
          {regionalCropPickerOpen&&<ul className="regional-suggestions" id="regional-crop-suggestions" role="listbox">{filteredMarketCropChoices.length?filteredMarketCropChoices.map(choice=><li role="option" aria-selected="false" key={choice.commodity}><button type="button" onClick={()=>{setEstimateForm(current=>({...current,commodity:choice.commodity,quantity:current.quantity||'12',unit:'kg',state:'',district:'',market:'',variety:''}));setRegionalCropSearch(choice.label);setRegionalCropPickerOpen(false);setEstimate(null);setEstimateError('');}}><strong>{choice.commodity}</strong><span>Search every reported mandi · all India</span></button></li>):<li className="regional-suggestions-empty">{marketOptions.commodities.length?'No matching commodity. Try a shorter search.':'The commodity list is still loading; you can type the name manually.'}</li>}</ul>}
          <small>Every commodity in the current feed is listed. Pick one, then narrow to a state, district, or mandi if you want a local comparison.</small>
        </div>
        <form className="estimate-form" onSubmit={findMarketPrices}>
          <label>Crop or commodity<input required value={estimateForm.commodity} onChange={e=>setEstimateForm({...estimateForm,commodity:e.target.value})} placeholder="e.g. Onion"/></label>
          <label>Harvest quantity<input required type="number" min="0.001" max="1000000000" step="any" value={estimateForm.quantity} onChange={e=>setEstimateForm({...estimateForm,quantity:e.target.value})} placeholder="e.g. 12"/></label>
          <label>Unit<select value={estimateForm.unit} onChange={e=>setEstimateForm({...estimateForm,unit:e.target.value})}><option value="quintal">Quintals</option><option value="kg">Kilograms</option></select></label>
          <label>State <span className="optional-label">Optional · leave blank for all India</span><input list="market-state-options" value={estimateForm.state} onChange={e=>setEstimateForm({...estimateForm,state:e.target.value})} placeholder="Any state"/><datalist id="market-state-options">{marketOptions.states.map(state=><option key={state} value={state}/>)}</datalist></label>
          <label>District <span className="optional-label">Optional · blank searches every district in the selected state</span><input list="market-district-options" value={estimateForm.district} onChange={e=>setEstimateForm({...estimateForm,district:e.target.value})} placeholder="Any district"/><datalist id="market-district-options">{marketOptions.districts.map(district=><option key={district} value={district}/>)}</datalist></label>
          <label>Variety <span className="optional-label">Optional</span><input list="market-variety-options" value={estimateForm.variety} onChange={e=>setEstimateForm({...estimateForm,variety:e.target.value})} placeholder="Any reported variety"/><datalist id="market-variety-options">{marketOptions.varieties.map(variety=><option key={variety} value={variety}/>)}</datalist></label>
          <label>Mandi <span className="optional-label">Optional</span><input list="market-mandi-options" value={estimateForm.market} onChange={e=>setEstimateForm({...estimateForm,market:e.target.value})} placeholder="Compare all in district"/><datalist id="market-mandi-options">{marketOptions.markets.map(market=><option key={market} value={market}/>)}</datalist></label>
          <button className="estimate-all-india" type="button" onClick={()=>setEstimateForm(current=>({...current,state:'',district:'',market:''}))}>Use all India scope</button>
          <button className="primary estimate-submit" type="submit" disabled={estimateBusy}>{estimateBusy?'Fetching reported prices…':'Find Market Prices'}</button>
        </form>
        {estimateError&&<p className="estimate-error" role="alert">{estimateError}</p>}
        {estimateBusy&&<p className="estimate-loading" role="status">Requesting the latest available provider records. Reported prices may be from an earlier market date.</p>}
        {estimate&&<div className="estimate-results">
          <div className="estimate-freshness" role="status"><strong>{estimate.status==='empty'?'No matching reported prices':estimate.items.some(row=>row.stale)?'Older reported observations':'Prices retrieved from data.gov.in'}</strong><span>{estimate.status==='empty'?'No market reporting date is available':`Market date: ${estimate.items.map(row=>row.reporting_date).sort().reverse()[0]}`} · Retrieved: {new Date(estimate.retrieved_at).toLocaleString('en-IN')}</span></div>
          {estimate.status==='empty'?<div className="estimate-empty" role="status"><strong>No prices found for this search</strong><p>{estimate.message||'The official feed returned no matching market reports. Try a crop or location shown in the available choices.'}</p><small>No harvest value was calculated because there is no reported price to use.</small></div>:<>
          {estimate.comparison_note&&<p className="comparison-note">{estimate.comparison_note}</p>}
          <div className="estimate-summary"><div><span className="eyebrow">{estimateForm.market?`ESTIMATE · ${estimateForm.market.toUpperCase()}`:`HIGHEST REPORTED ${estimateMeasure==='expected'?'MODAL':estimateMeasure.toUpperCase()} PRICE`}</span><strong>{formatINR(estimateSummaryValue)}</strong><small>Gross estimate for {estimate.query.quantity} {estimate.query.unit} of {estimate.query.commodity}{estimateSummary?` at ${estimateSummary.market}, ${estimateSummary.district}`:''}</small></div><label>Estimate using<select value={estimateMeasure} onChange={e=>setEstimateMeasure(e.target.value as typeof estimateMeasure)}><option value="expected">Modal price</option><option value="minimum">Minimum price</option><option value="maximum">Maximum price</option></select></label></div>
          <div className="estimate-table-heading"><div><span className="eyebrow">MATCHING OBSERVATIONS</span><h4>{estimate.items.length} market{estimate.items.length===1?'':'s'} found</h4></div><div className="estimate-sort" aria-label="Sort market observations"><button type="button" className={estimateSort==='modal'?'selected':''} onClick={()=>setEstimateSort('modal')}>Modal price</button><button type="button" className={estimateSort==='gross'?'selected':''} onClick={()=>setEstimateSort('gross')}>Gross value</button></div></div>
          <div className="estimate-table-wrap"><table className="estimate-table"><thead><tr><th scope="col">Mandi</th><th scope="col">Variety / grade</th><th scope="col">Min / modal / max<br/><small>₹ per quintal</small></th><th scope="col">Estimated gross range</th><th scope="col">Reported</th><th scope="col">Source</th></tr></thead><tbody>{estimateRows.map(row=><tr key={`${row.market}-${row.reporting_date}-${row.variety}-${row.grade}`}><td><strong>{row.market}</strong>{highestModal===row&&<span className="highest-price">Highest modal</span>}<small>{row.district}, {row.state}</small></td><td>{row.variety||'Not specified'}<small>{row.grade||'Grade not reported'}</small></td><td>{formatINR(row.minimum_price)}<small>{formatINR(row.modal_price)} modal</small>{formatINR(row.maximum_price)}<small>{row.source_price_unit}</small></td><td><strong>{formatINR(row.minimum_value)}</strong><small>{formatINR(row.expected_value)} modal</small>{formatINR(row.maximum_value)}</td><td>{row.reporting_date}<small>{row.stale?'Older report':'Recent report'}</small></td><td><a href={row.source_url} target="_blank" rel="noreferrer">data.gov.in ↗</a></td></tr>)}</tbody></table></div>
          </>}
          <p className="estimate-source">Source: {estimate.provider} · {estimate.served_from==='live'?'Live provider response':'Stored daily feed'} · Retrieved at {new Date(estimate.retrieved_at).toLocaleString('en-IN')}. {estimate.status==='empty'?'No matching report was returned for these filters.':'The reporting date is supplied by the market feed; retrieval time is when this app last stored or requested the records.'}</p>
        </div>}
        <p className="estimate-disclaimer">Prices are estimates based on reported market data. Actual selling prices may vary by quality, variety, quantity, market conditions, and applicable deductions. No transport or transaction costs are deducted.</p>
      </section>

    </div>}
    {page==='voice' && <div className="voice-chat">
      <header className="voice-chat-heading"><div><span className="eyebrow">GEMINI FARM ASSISTANT</span><h2>Talk with Kheti assistant</h2><p>Ask about crops, plant care, or farming. Choose Hindi, English, or Hinglish; use the mic to dictate and hear spoken replies.</p></div><span className="voice-status">English · हिन्दी · Hinglish</span></header>
      <div className="voice-chat-options"><label>Reply language<select value={chatLanguage} onChange={e=>setChatLanguage(e.target.value as 'en'|'hi'|'hinglish')}><option value="en">English</option><option value="hi">Hindi</option><option value="hinglish">Hinglish</option></select></label><label className="speak-toggle"><input type="checkbox" checked={speakReplies} onChange={e=>setSpeakReplies(e.target.checked)}/> Read replies aloud</label><button type="button" className="quiet" onClick={()=>{setVoiceMessages([]);setNotice('');window.speechSynthesis?.cancel();}}>New conversation</button></div>
      <div className="voice-messages" aria-live="polite" aria-label="Conversation with the farm assistant">{voiceMessages.length===0?<div className="voice-empty"><span aria-hidden="true">✳</span><strong>How can I help your farm today?</strong><p>Try “My tomato leaves have brown spots. What should I check?”</p></div>:voiceMessages.map((item,index)=><article className={`voice-message ${item.role}`} key={`${index}-${item.role}`}><small>{item.role==='user'?'You':'Kheti assistant'}</small><p>{item.content}</p>{item.role==='assistant'&&<button type="button" className="voice-read-button" onClick={()=>{if('speechSynthesis'in window){window.speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(item.content);utterance.lang=chatLanguage==='en'?'en-IN':'hi-IN';window.speechSynthesis.speak(utterance);}}}>▶ Listen</button>}</article>)}{voiceBusy&&<article className="voice-message assistant" role="status"><small>Kheti assistant</small><p className="voice-thinking"><i/><i/><i/> Thinking…</p></article>}<div ref={voiceMessagesEnd}/></div>
      <form className="voice-compose" onSubmit={ask}><textarea rows={2} maxLength={4000} value={voiceInput} onChange={e=>setVoiceInput(e.target.value)} placeholder={chatLanguage==='hi'?'अपना सवाल लिखें…':'Ask your farming question…'} aria-label="Your message"/><button className={`mic-button${isListening?' listening':''}`} type="button" onClick={speakQuestion} aria-label={isListening?'Listening for your message':'Dictate your message'} title={isListening?'Listening…':'Dictate your message'} aria-pressed={isListening}><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="2.5" width="6" height="12" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V22m-4 0h8"/></svg></button><button type="submit" className="primary" disabled={voiceBusy||!voiceInput.trim()}>{voiceBusy?'Sending…':'Send message'} <span aria-hidden="true">↑</span></button></form>
      <p className="voice-footnote">For urgent crop disease or chemical treatment decisions, verify advice with a local agricultural expert.</p>
    </div>}
  </section>;
}
