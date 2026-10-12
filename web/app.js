/* Lernraum: browser workspace. All records come from the local server. */
'use strict';

const paths = {
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M9 21v-8h6v8"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  book: '<path d="M4 3h6a3 3 0 0 1 3 3v15a4 4 0 0 0-4-3H3V4a1 1 0 0 1 1-1z"/><path d="M20 3h-4a3 3 0 0 0-3 3v15a4 4 0 0 1 4-3h4V4a1 1 0 0 0-1-1z"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  cards: '<rect x="7" y="3" width="14" height="16" rx="3"/><path d="M3 7v11a3 3 0 0 0 3 3h11M11 8h6M11 12h4"/>',
  chart: '<path d="M4 3v18h17M8 15v3M13 10v8M18 5v13"/>',
  sparkle: '<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7zM20 2v4M18 4h4"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
  file: '<path d="M14 3H5a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V9zM14 3v6h6M8 13h8M8 17h5"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
  play: '<path d="m8 4 13 8-13 8z"/>',
  repeat: '<path d="m17 2 4 4-4 4M3 11V8a2 2 0 0 1 2-2h16M7 22l-4-4 4-4M21 13v3a2 2 0 0 1-2 2H3"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  bolt: '<path d="m13 2-9 12h7l-1 8 10-12h-7z"/>',
  edit: '<path d="m16 3 5 5M4 16 17 3a2 2 0 0 1 3 3L7 19l-4 1z"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  terminal: '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="m6 8 4 4-4 4M13 16h5"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 4V3H3v13h1"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  flask: '<path d="M9 3h6M10 3v7L4 20a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1l-6-10V3M7 15h10"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 11h18"/>',
};
function icon(name) { return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.book}</svg>`; }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }
const $ = (selector, parent = document) => parent.querySelector(selector);
const navItems = [['overview','Überblick','grid'],['modules','Meine Module','book'],['materials','Materialien','folder'],['questions','Fragenpool','cards'],['reviews','Antwortprüfungen','check'],['progress','Lernfortschritt','chart'],['ai','KI-Werkstatt','sparkle']];
const kinds = {lecture:'Vorlesung',practical:'Praktikum',other:'Weitere Einheit'};
const types = {multiple_choice:'Multiple Choice',free_text:'Freitext',image:'Bildfrage'};
const difficulties = {1:'Leicht',2:'Mittel',3:'Anspruchsvoll'};
const colors = {violet:'#7463df',blue:'#559bd8',green:'#5ba880',orange:'#e39a4d',rose:'#d87893'};
let state = {modules:[],units:[],materials:[],questions:[],attempts:[],answer_submissions:[],stats:{totals:{},modules:[],week:[],topics:[],recent_attempts:[]}};
let aiStatus = {configured:false,provider:null,model:null,reason:'Keine KI konfiguriert.'};
let route = {view:'overview',moduleId:'',tab:'overview',params:new URLSearchParams()};
let query = '';
let filterType = 'all';
let aiDrafts = [];
let aiDraftModule = '';
let study = null;
let pendingAction = false;
let refreshing = false;

async function api(path, body, method = 'POST') {
  const verb = body === undefined && method === 'POST' ? 'GET' : method;
  const options = verb === 'GET' ? {} : {method:verb,headers:{'Content-Type':'application/json','X-Lernraum-Client':'local'},body:JSON.stringify(body ?? {})};
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); } catch { throw new Error('Der lokale Server hat keine gültige Antwort gesendet.'); }
  if (!response.ok) throw new Error(data.error || 'Die Aktion konnte nicht abgeschlossen werden.');
  return data;
}
function toast(message, error = false) {
  const item = document.createElement('div');
  item.className = `toast ${error ? 'error' : 'success'}`;
  item.setAttribute('role', error ? 'alert' : 'status');
  item.innerHTML = `${icon(error ? 'close' : 'check')}<span>${esc(message)}</span>`;
  $('#toasts').append(item);
  setTimeout(() => item.remove(), error ? 8500 : 4200);
}
function openModal({title,description='',body='',footer='',wide=false}) {
  const dialog = $('#modal');
  dialog.className = wide ? 'modal-wide' : '';
  dialog.innerHTML = `<div class="modal-header"><div><h2 id="modal-title">${esc(title)}</h2>${description ? `<p>${esc(description)}</p>` : ''}</div><button class="icon-button modal-close" data-action="close-modal" aria-label="Schließen">${icon('close')}</button></div><div class="modal-body">${body}</div>${footer ? `<div class="modal-footer">${footer}</div>` : ''}`;
  if (!dialog.open) dialog.showModal();
  requestAnimationFrame(() => $('input:not([type=checkbox]):not([type=hidden]),select,textarea',dialog)?.focus());
}
function closeModal() { $('#modal').close(); }
function navigate(hash) {
  document.body.classList.remove('nav-open');
  query = ''; filterType = 'all';
  const next = hash.startsWith('#') ? hash : '#' + hash;
  if (location.hash === next) render(); else location.hash = next;
}
async function refresh() {
  state = await api('/api/state');
  LR.state = state;
  render();
}
const LR = window.LR = {state,api,refresh,icon,esc,toast,openModal,closeModal,navigate,dialogs:{}};
function parseRoute() {
  const [path,params=''] = (location.hash.slice(1) || 'overview').split('?');
  const [view,moduleId=''] = path.split('/');
  const search = new URLSearchParams(params);
  route = {view,moduleId:moduleId || search.get('module') || '',tab:search.get('tab') || 'overview',params:search};
}
const moduleBy = id => state.modules.find(m => m.id === id);
const moduleStats = id => state.stats.modules?.find(m => m.module_id === id) || {units:0,materials:0,questions:0,due_questions:0,mastery_percent:null,attempts:0};
const questionBy = id => state.questions.find(q => q.id === id);
const unitBy = id => state.units.find(u => u.id === id);
const pendingAnswers = () => (state.answer_submissions || []).filter(a=>a.status==='pending');
const awaitingReview = q => pendingAnswers().some(a=>a.question_id===q.id);
const due = q => q.reviewed && !awaitingReview(q) && (!q.due_at || new Date(q.due_at) <= new Date());
const dueCount = id => state.questions.filter(q => (!id || q.module_id === id) && due(q)).length;
const pct = value => value === null || value === undefined ? '—' : `${value}%`;
const bytes = value => value >= 1024*1024 ? `${(value/1024/1024).toFixed(1).replace('.',',')} MB` : `${Math.max(1,Math.round(value/1024))} KB`;
const date = value => value ? new Intl.DateTimeFormat('de-DE',{day:'numeric',month:'short',timeZone:'Europe/Berlin'}).format(new Date(value.length === 10 ? value + 'T12:00:00Z' : value)) : 'Ohne Datum';
const relDate = value => {
  if (!value) return 'Neu';
  const time = new Date(value) - new Date();
  if (time <= 0) return 'Jetzt fällig';
  if (time < 3600000) return `In ${Math.ceil(time/60000)} Min.`;
  if (time < 86400000) return `In ${Math.ceil(time/3600000)} Std.`;
  return `Am ${date(value)}`;
};
function button(label,action,style='primary',glyph='',extra='') { return `<button class="button ${style}" data-action="${action}" ${extra}>${glyph ? icon(glyph) : ''}${label}</button>`; }
function empty(title,text,glyph='folder',action='',label='') { return `<div class="empty-state"><span class="empty-icon">${icon(glyph)}</span><h3>${esc(title)}</h3><p>${esc(text)}</p>${action ? button(label,action,'secondary', 'plus') : ''}</div>`; }
function pageHeader(eyebrow,title,description,actions='') { return `<div class="page-header"><div><span class="eyebrow">${esc(eyebrow)}</span><h1>${esc(title)}</h1><p class="description">${esc(description)}</p></div><div class="header-actions">${actions}</div></div>`; }
function sourceLine(q) {
  const material = state.materials.find(m => m.id === q.source_material_id);
  return material ? `<button class="source-line" data-action="material-preview" data-id="${material.id}">${icon('file')}${esc(material.name)}${q.source_page ? ` · Seite ${q.source_page}` : ''}</button>` : '<span class="source-line">Eigene Lernfrage · ohne Quellenverweis</span>';
}
function statCard(glyph,label,value,caption,color='violet') { return `<div class="stat-card"><span class="stat-icon ${color}">${icon(glyph)}</span><div><span class="stat-caption">${esc(label)}</span><strong class="stat-value">${esc(value)}</strong><small>${esc(caption)}</small></div></div>`; }
function moduleCard(m) {
  const s = moduleStats(m.id);
  const progress = s.mastery_percent;
  return `<article class="module-card ${m.color}"><div class="module-card-head"><a class="module-icon" href="#module/${m.id}" aria-label="${esc(m.name)} öffnen">${icon('book')}</a><span class="badge gray">${esc(m.code || m.semester || 'MODUL')}</span><button class="icon-button" data-action="edit-module" data-id="${m.id}" aria-label="${esc(m.name)} bearbeiten">${icon('edit')}</button></div><a href="#module/${m.id}"><h3>${esc(m.name)}</h3><p class="module-description">${esc(m.description || 'Deine Vorlesungen, Praktika und Materialien an einem Ort.')}</p></a><div class="module-counts"><span>${icon('book')}${s.units} Einheiten</span><span>${icon('file')}${s.materials} Materialien</span><span>${icon('cards')}${s.questions} Fragen</span></div><div class="module-progress"><span>${progress === null ? 'Dein erster Schritt wartet' : 'Sicherheit · geübte Fragen'}</span><strong>${pct(progress)}</strong></div><div class="progress-track"><span class="progress-fill" style="width:${progress || 0}%"></span></div><div class="module-footer"><span>${dueCount(m.id) ? `<i class="status-dot"></i>${dueCount(m.id)} Fragen bereit` : 'Alles beginnt mit einer Vorlesung'}</span><a href="#module/${m.id}" aria-label="${esc(m.name)} öffnen">${icon('arrow')}</a></div></article>`;
}
function chart(week = state.stats.week || []) {
  const max = Math.max(3,...week.map(d => d.attempts));
  return `<div class="weekly-bars" role="img" aria-label="Lernaktivität der letzten sieben Tage: ${week.map(d=>`${date(d.date)}: ${d.attempts} Antworten`).join(', ')}">${week.map((d,i) => `<div class="bar-column"><span class="bar-number">${d.attempts || ''}</span><div class="bar-track"><div class="bar-fill ${i === week.length-1 ? 'today' : ''}" style="height:${d.attempts/max*100}%"></div></div><span class="chart-label">${new Intl.DateTimeFormat('de-DE',{weekday:'short',timeZone:'Europe/Berlin'}).format(new Date(d.date+'T12:00:00Z')).replace('.','')}</span></div>`).join('')}</div><div class="chart-legend"><i></i>Beantwortete Fragen <span>Letzte 7 Tage</span></div>`;
}
function renderOverview() {
  const totals = state.stats.totals;
  const ready = dueCount();
  const hasMaterials = state.materials.length > 0;
  const hasQuestions = state.questions.length > 0;
  const steps = [
    {done:state.units.length>0,title:'Gib deinem Semester Struktur',text:'Benenne deine Module und lege die erste Vorlesung an.',action:'new-unit',icon:'book'},
    {done:hasMaterials,title:'Bring deine Unterlagen mit',text:'Folien, Aufgaben und Notizen – alles findet seinen Platz.',action:'upload',icon:'upload'},
    {done:hasQuestions,title:'Mach aus Wissen Lernfragen',text:'Erstelle Fragen selbst oder gemeinsam mit deiner KI.',action:'new-question',icon:'cards'},
  ];
  const today = new Intl.DateTimeFormat('de-DE',{weekday:'long',day:'numeric',month:'long',timeZone:'Europe/Berlin'}).format(new Date());
  return pageHeader(today,'Hallo, neuer Lernfortschritt.','Dein Studium, sortiert. Dein nächster Schritt, ganz klar.',button('Lernsession starten','learn','primary','play')) + reviewNotice() +
    `<section class="dashboard-hero"><div class="hero-copy"><span class="hero-kicker">✦ DEIN RAUM FÜR AHA-MOMENTE</span><h2>Weniger Zettelchaos.<br>Mehr verstanden.</h2><p>Alles für deine Module an einem Ort.<br>Aus Unterlagen wird Wissen, das bleibt.</p><div class="hero-footer">${button(hasMaterials ? 'Zu meinen Materialien' : 'Erste Materialien hochladen',hasMaterials ? 'go-materials' : 'upload','hero-button','upload')}<span>In deinem Tempo. Auf deinem Rechner.</span></div></div><div class="hero-illustration" aria-hidden="true"><div class="hero-orbit"></div><div class="hero-card back"><span>01 / VERSTEHEN</span><div class="card-lines"><i></i><i></i><i></i></div></div><div class="hero-card front"><span>02 / VERKNÜPFEN</span><strong>A <em>↔</em> B</strong><small>Ein Gedanke. Viele Zusammenhänge.</small><div class="card-dots"><i></i><i></i><i></i></div></div><div class="floating-card"><span>✦</span> Das bleibt im Kopf.</div><div class="hero-spark s1">✦</div><div class="hero-spark s2">✧</div></div></section>` +
    `<div class="stats-grid">${statCard('book','Aktive Module',state.modules.length,'Dein Semester im Blick')}${statCard('cards','Bereit zum Lernen',ready,ready ? 'Neu oder zur Wiederholung' : 'Erstelle deine ersten Fragen','blue')}${statCard('target','Antwortsicherheit',pct(totals.mastery_percent),totals.attempts ? 'Nur bereits geübte Fragen' : 'Entsteht mit deinen Antworten','green')}${statCard('bolt','Dein Lernrhythmus',`${state.stats.streak || 0} Tage`,`${totals.attempts || 0} Antworten insgesamt`,'orange')}</div>` +
    `<div class="section-heading"><div><h2>Meine Module <span class="count-pill">${state.modules.length}</span></h2><p>Für jedes Fach ein eigener Lernraum.</p></div>${button('Modul hinzufügen','new-module','ghost','plus')}</div><div class="modules-grid">${state.modules.map(moduleCard).join('')}${!state.modules.length ? empty('Dein Semester beginnt hier','Lege dein erstes Modul an.','book','new-module','Modul anlegen') : ''}</div>` +
    `<div class="dashboard-grid"><section class="panel"><div class="panel-header"><div><h2>${totals.attempts ? 'Dein nächster Schritt' : 'Ein guter Anfang'}</h2><p>${totals.attempts ? 'Bleib an dem dran, was noch nicht sitzt.' : 'Drei kleine Schritte zu deinem Lernraum.'}</p></div><span class="badge violet">${steps.filter(s=>s.done).length}/3 bereit</span></div>${totals.attempts && ready ? `<div class="review-prompt"><span class="stat-icon violet">${icon('repeat')}</span><div><h3>${ready} Fragen warten auf dich</h3><p>Wiederhole jetzt, damit dein Wissen bleibt.</p></div>${button('Los geht’s','learn','primary','arrow')}</div>` : `<div class="getting-started">${steps.map((s,i) => `<button class="step-item ${s.done ? 'done' : ''}" data-action="${s.action}"><span class="step-number">${s.done ? icon('check') : i+1}</span><span><strong>${s.title}</strong><small>${s.text}</small></span>${icon('chevron')}</button>`).join('')}</div>`}</section><section class="panel"><div class="panel-header"><div><h2>Deine Lernwoche</h2><p>Jeder Schritt zählt.</p></div><a class="icon-button" href="#progress" aria-label="Lernfortschritt ansehen">${icon('arrow')}</a></div>${chart()}</section></div>`;
}
function renderModules() {
  return pageHeader('DEIN SEMESTER','Für jedes Fach ein Lernraum.','Vorlesungen, Praktika und Wissen – sinnvoll verbunden.',button('Modul anlegen','new-module','primary','plus')) + `<div class="modules-grid">${state.modules.map(moduleCard).join('')}</div>` + (!state.modules.length ? empty('Welche Module belegst du?','Erstelle eine Modulakte für jedes Fach.','book','new-module','Erstes Modul anlegen') : '');
}
function tabs(m) {
  const counts = moduleStats(m.id);
  return `<div class="section-tabs" role="navigation" aria-label="Modulbereiche">${[['overview','Übersicht',''],['units','Vorlesungen & Praktika',counts.units],['materials','Materialien',counts.materials],['questions','Lernfragen',counts.questions]].map(([tab,label,n])=>`<a class="tab-button ${route.tab === tab ? 'active' : ''}" href="#module/${m.id}?tab=${tab}" ${route.tab===tab?'aria-current="page"':''}>${label}${n !== '' ? `<span class="count-pill">${n}</span>` : ''}</a>`).join('')}</div>`;
}
function renderModule() {
  const m = moduleBy(route.moduleId);
  if (!m) return empty('Modul nicht gefunden','Wähle links eines deiner Module aus.','book','new-module','Modul anlegen');
  const s = moduleStats(m.id);
  let content;
  if (route.tab === 'units') content = `<div class="section-heading"><div><h2>Deine Einheiten</h2><p>Organisiere Vorlesungen, Praktika und Übungen.</p></div>${button('Einheit hinzufügen','new-unit','secondary','plus',`data-module="${m.id}"`)}</div>` + unitList(m.id);
  else if (route.tab === 'materials') content = materialsView(m.id, true);
  else if (route.tab === 'questions') content = questionsView(m.id, true);
  else content = `<div class="stats-grid">${statCard('book','Einheiten',s.units,'Vorlesungen und Praktika')}${statCard('file','Materialien',s.materials,'Originale und lesbarer Text','blue')}${statCard('cards','Lernfragen',s.questions,`${dueCount(m.id)} bereit zur Wiederholung`,'orange')}${statCard('target','Antwortsicherheit',pct(s.mastery_percent),'Nur bereits geübte Fragen','green')}</div><div class="dashboard-grid"><section class="panel"><div class="panel-header"><div><h2>Vorlesungen & Praktika</h2><p>Deine Materialien folgen deiner Struktur.</p></div>${button('Hinzufügen','new-unit','ghost','plus',`data-module="${m.id}"`)}</div>${unitList(m.id,true)}</section><section class="panel module-study-panel"><span class="stat-icon violet">${icon('target')}</span><h2>Verstanden ist gut.<br>Behalten ist besser.</h2><p>${s.questions ? `${dueCount(m.id)} Fragen sind jetzt bereit. Starte eine Lernsession und finde heraus, was schon sitzt.` : 'Erstelle deine ersten Lernfragen aus den Materialien dieses Moduls.'}</p>${button(s.questions ? 'Dieses Modul lernen' : 'Erste Frage erstellen',s.questions ? 'learn' : 'new-question','primary',s.questions ? 'play':'plus',`data-module="${m.id}"`)}<div class="module-study-foot">${icon('repeat')}Wiederholungen richten sich nach deinen Antworten.</div></section></div><section class="panel"><div class="panel-header"><div><h2>Zuletzt hinzugefügt</h2><p>Deine Unterlagen, immer griffbereit.</p></div>${button('Material hochladen','upload','ghost','upload',`data-module="${m.id}"`)}</div>${materialList(state.materials.filter(f=>f.module_id===m.id).slice(-4).reverse())}</section>`;
  return pageHeader(m.code || m.semester || 'MODULAKTE',m.name,m.description || 'Dein Raum für Vorlesungen, Praktika und alles dazwischen.',button('Bearbeiten','edit-module','secondary','edit',`data-id="${m.id}"`)+button('Lernen','learn','primary','play',`data-module="${m.id}"`)) + tabs(m) + content;
}
function unitList(moduleId,compact=false) {
  const units = state.units.filter(u=>u.module_id===moduleId);
  if (!units.length) return empty('Die erste Vorlesung wartet','Lege eine Einheit an und ordne deine Materialien dazu.','book','new-unit','Einheit hinzufügen');
  return `<div class="units-grid ${compact?'compact':''}">${units.map(u=>{const materials=state.materials.filter(f=>f.unit_ids.includes(u.id)); const questions=state.questions.filter(q=>q.unit_id===u.id); return `<article class="unit-card"><div class="unit-card-top"><span class="unit-kind badge ${u.kind==='practical'?'green':'violet'}">${icon(u.kind==='practical'?'flask':'book')}${kinds[u.kind]}</span><div class="row-actions"><button class="icon-button" data-action="edit-unit" data-id="${u.id}" aria-label="${esc(u.title)} bearbeiten">${icon('edit')}</button><button class="icon-button" data-action="delete-unit" data-id="${u.id}" aria-label="${esc(u.title)} löschen">${icon('trash')}</button></div></div><h3>${esc(u.title)}</h3><span class="unit-date">${icon('calendar')}${date(u.date)}</span>${u.notes ? `<p class="unit-notes">${esc(u.notes)}</p>` : ''}<div class="unit-footer"><span>${materials.length} Materialien · ${questions.length} Fragen</span>${button('Material','upload','ghost small','plus',`data-module="${moduleId}" data-unit="${u.id}"`)}</div>${materials.length ? `<div class="unit-files">${materials.slice(0,3).map(f=>`<button data-action="material-preview" data-id="${f.id}">${icon('file')}${esc(f.name)}</button>`).join('')}</div>` : ''}</article>`;}).join('')}</div>`;
}
function moduleFilter(moduleId,scope='global') {
  return `<select class="filter-select" data-filter="module" aria-label="Modul filtern" data-scope="${scope}"><option value="">Alle Module</option>${state.modules.map(m=>`<option value="${m.id}" ${moduleId===m.id?'selected':''}>${esc(m.name)}</option>`).join('')}</select>`;
}
function materialList(materials) {
  if (!materials.length) return empty('Noch Platz für deine Unterlagen','Lade Folien, Skripte, Aufgabenblätter oder eigene Notizen hoch.','folder','upload','Materialien hochladen');
  return `<div class="materials-list">${materials.map(f=>`<article class="material-row"><button class="file-icon ${f.mime.startsWith('image/')?'green':'violet'}" data-action="material-preview" data-id="${f.id}" aria-label="${esc(f.name)} ansehen">${icon(f.mime.startsWith('image/')?'image':'file')}</button><button class="file-info" data-action="material-preview" data-id="${f.id}"><strong>${esc(f.name)}</strong><span class="file-meta">${esc(moduleBy(f.module_id)?.name)} · ${bytes(f.size)}${f.page_count?` · ${f.page_count} Seiten`:''}<span>${f.unit_ids.length ? f.unit_ids.map(id=>esc(unitBy(id)?.title || '')).join(', ') : 'Noch keiner Einheit zugeordnet'}</span></span></button><span class="file-status badge ${f.extraction_status==='ready'?'green':'orange'}">${f.extraction_status==='ready'?'Text lesbar':f.extraction_status==='needs_ocr'?'Text ergänzen':'Original gespeichert'}</span><div class="row-actions"><a class="icon-button" href="${f.file_url}" target="_blank" rel="noopener" aria-label="${esc(f.name)} öffnen">${icon('download')}</a><button class="icon-button" data-action="delete-material" data-id="${f.id}" aria-label="${esc(f.name)} löschen">${icon('trash')}</button></div></article>`).join('')}</div>`;
}
function materialsView(moduleId,nested=false) {
  const materials = state.materials.filter(f=>(!moduleId||f.module_id===moduleId) && (!query||f.name.toLowerCase().includes(query.toLowerCase())) && (filterType==='all'||(filterType==='readable'?f.extraction_status==='ready':f.mime.startsWith('image/'))));
  return (nested ? `<div class="section-heading"><div><h2>Deine Materialsammlung</h2><p>Originaldateien und lesbarer Text für dich und deine KI.</p></div>${button('Hochladen','upload','primary','upload',`data-module="${moduleId}"`)}</div>` : pageHeader('DEINE WISSENSBASIS','Alles dabei. Alles an einem Ort.','Folien, Skripte, Aufgaben und Notizen aus allen Modulen.',button('Materialien hochladen','upload','primary','upload',moduleId?`data-module="${moduleId}"`:''))) + `<div class="toolbar"><div class="filter-group">${!nested?moduleFilter(moduleId):''}<select class="filter-select" data-filter="type" aria-label="Materialart"><option value="all" ${filterType==='all'?'selected':''}>Alle Materialien</option><option value="readable" ${filterType==='readable'?'selected':''}>Text lesbar</option><option value="images" ${filterType==='images'?'selected':''}>Bilder</option></select></div><label class="search-input">${icon('search')}<input data-filter="query" placeholder="Material suchen …" aria-label="Material suchen" value="${esc(query)}"></label></div><section class="panel list-panel" id="filtered-list">${materialList(materials)}</section><p class="form-help">PDF, DOCX, PPTX, TXT, Markdown, CSV und Bilder · bis 40 MB pro Datei. Bei Scans und Bildern kannst du lesbaren Text ergänzen.</p>`;
}
function questionList(questions) {
  if (!questions.length) return empty('Hier wächst dein Wissen','Erstelle deine erste Frage oder importiere geprüfte KI-Fragen.','cards','new-question','Frage erstellen');
  return `<div class="questions-list">${questions.map(q=>`<article class="question-row"><span class="question-type ${q.type==='multiple_choice'?'violet':q.type==='image'?'green':'blue'}">${icon(q.type==='image'?'image':'cards')}</span><button class="question-info" data-action="preview-question" data-id="${q.id}"><strong class="question-prompt">${esc(q.prompt)}</strong><span class="question-meta">${types[q.type]} · ${esc(q.topic || 'Ohne Thema')} · ${esc(moduleBy(q.module_id)?.name)}${q.unit_id ? ` · ${esc(unitBy(q.unit_id)?.title)}` : ''}</span></button><span class="badge ${!q.reviewed?'orange':q.attempt_count && q.mastery===100?'green':'gray'}">${!q.reviewed?'Noch prüfen':q.attempt_count ? `${q.mastery}% sicher`:'Neu'}</span><div class="row-actions"><button class="icon-button" data-action="edit-question" data-id="${q.id}" aria-label="Frage bearbeiten">${icon('edit')}</button><button class="icon-button" data-action="delete-question" data-id="${q.id}" aria-label="Frage löschen">${icon('trash')}</button></div></article>`).join('')}</div>`;
}
function questionsView(moduleId,nested=false) {
  const questions = state.questions.filter(q=>(!moduleId||q.module_id===moduleId) && (!query||`${q.prompt} ${q.topic}`.toLowerCase().includes(query.toLowerCase())) && (filterType==='all'||(filterType==='unreviewed'?!q.reviewed:q.type===filterType)));
  const attrs = moduleId ? `data-module="${moduleId}"` : '';
  return (nested ? `<div class="section-heading"><div><h2>Deine Lernfragen</h2><p>Fragen, die Verständnis sichtbar machen.</p></div>${button('Importieren','import-questions','secondary','download',attrs)}${button('Frage erstellen','new-question','primary','plus',attrs)}</div>` : pageHeader('VOM LESEN ZUM VERSTEHEN','Gute Fragen. Echtes Wissen.','Multiple Choice, Freitext und Bildfragen – mit nachvollziehbaren Quellen.',button('Importieren','import-questions','secondary','download',attrs)+button('Frage erstellen','new-question','primary','plus',attrs))) + `<div class="toolbar"><div class="filter-group">${!nested?moduleFilter(moduleId):''}<select class="filter-select" data-filter="type" aria-label="Fragemodell"><option value="all">Alle Fragemodelle</option>${Object.entries(types).map(([value,label])=>`<option value="${value}" ${filterType===value?'selected':''}>${label}</option>`).join('')}<option value="unreviewed" ${filterType==='unreviewed'?'selected':''}>Noch zu prüfen</option></select></div><div class="filter-group"><label class="search-input">${icon('search')}<input data-filter="query" placeholder="Frage oder Thema suchen …" aria-label="Fragen suchen" value="${esc(query)}"></label>${button('Export','export-questions','ghost small','download',attrs)}</div></div><section class="panel list-panel" id="filtered-list">${questionList(questions)}</section>`;
}

function renderLearn() {
  if (study) return renderSession();
  const selected = route.moduleId;
  const readyQuestions = state.questions.filter(q=>q.reviewed && !awaitingReview(q) && (!selected || q.module_id===selected));
  return pageHeader('DEIN FOKUSMOMENT','Ein bisschen lernen. Viel behalten.','Wähle dein Thema und starte eine Session, die zu deinem Tag passt.') + `<div class="learn-layout"><section class="panel learn-setup"><div class="panel-header"><div><h2>Was möchtest du heute lernen?</h2><p>Neue Fragen oder gezielte Wiederholung.</p></div><span class="stat-icon violet">${icon('target')}</span></div><form id="learn-form"><div class="field"><label for="learn-module">Modul</label><select id="learn-module" name="module_id"><option value="">Alle Module</option>${state.modules.map(m=>`<option value="${m.id}" ${selected===m.id?'selected':''}>${esc(m.name)}</option>`).join('')}</select></div><div class="field"><label>Lernmodus</label><div class="select-grid"><label class="select-card"><input type="radio" name="mode" value="due" ${route.params.get('mode')!=='weak'?'checked':''}>${icon('repeat')}<strong>Jetzt dran</strong><small>Neue und fällige Fragen</small></label><label class="select-card"><input type="radio" name="mode" value="weak" ${route.params.get('mode')==='weak'?'checked':''}>${icon('target')}<strong>Schwächen üben</strong><small>Was noch nicht sicher sitzt</small></label><label class="select-card"><input type="radio" name="mode" value="all">${icon('cards')}<strong>Alles mischen</strong><small>Einmal quer durchs Wissen</small></label></div></div><div class="form-grid"><div class="field"><label for="learn-count">Sessionlänge</label><select id="learn-count" name="count"><option value="5">5 Fragen · ein kleiner Schritt</option><option value="10" selected>10 Fragen · ein guter Fokus</option><option value="20">20 Fragen · tiefer eintauchen</option><option value="1000">Alle passenden Fragen</option></select></div><div class="field"><label for="learn-type">Fragemodell</label><select id="learn-type" name="type"><option value="all">Alle Fragemodelle</option>${Object.entries(types).map(([key,label])=>`<option value="${key}">${label}</option>`).join('')}</select></div></div><p id="learn-error" class="field-error" role="alert"></p><button class="button primary" type="submit">${icon('play')}Session starten</button><p class="form-help">${readyQuestions.length} geprüfte ${readyQuestions.length===1?'Frage':'Fragen'} ${selected?'in diesem Modul':'in deinem Lernraum'}. Ungeprüfte KI-Vorschläge werden erst nach deiner Prüfung verwendet.</p></form></section><aside class="learn-aside"><section class="panel"><span class="stat-icon green">${icon('bolt')}</span><h3>Wissen braucht Wiederholung.</h3><p>Unsichere Fragen kommen früher zurück. Sichere Antworten bekommen mehr Abstand.</p><div class="review-intervals"><span><i class="status-dot"></i>Unsicher <strong>10 Minuten</strong></span><span><i class="status-dot"></i>Teilweise <strong>1 Tag</strong></span><span><i class="status-dot"></i>Sicher <strong>Zunehmender Abstand</strong></span></div></section><section class="panel"><h3>Verständnis zählt.</h3><p>Multiple Choice wird automatisch geprüft. Freitext- und Bildantworten kannst du zur Prüfung speichern und im Codex-Chat prüfen lassen. Selbst vergleichen und die optionale API-Rückmeldung bleiben verfügbar.</p><a class="button ghost small" href="#reviews">Antwortprüfungen ansehen</a></section>${!state.questions.length?`<section class="panel"><h3>Noch keine Fragen?</h3><p>Dein erster Lernschritt beginnt mit einer guten Frage.</p>${button('Frage erstellen','new-question','secondary','plus')}</section>`:''}</aside></div>`;
}
function renderSession() {
  if (study.index >= study.questions.length) {
    const secure = study.results.filter(r=>r.rating===2).length;
    const partial = study.results.filter(r=>r.rating===1).length;
    const pending = study.results.filter(r=>r.status==='pending').length;
    const unsure = study.results.filter(r=>r.rating===0).length;
    return `<div class="session-complete panel"><div class="complete-symbol">${icon('check')}</div><span class="eyebrow">EIN SCHRITT WEITER</span><h1>Das war Zeit für dein Wissen.</h1><p>${study.results.length} ${study.results.length===1?'Frage':'Fragen'} beantwortet. Deine Antworten sind gespeichert.</p><div class="session-summary ${pending?'has-pending':''}"><div><strong>${secure}</strong><span>Sicher</span></div><div><strong>${partial}</strong><span>Teilweise</span></div><div><strong>${unsure}</strong><span>Noch üben</span></div>${pending?`<div><strong>${pending}</strong><span>Wartet auf Prüfung</span></div>`:''}</div><p>${pending?'Schreib im Codex-Chat: „Prüf meine offenen Antworten.“ Nach der Prüfung findest du das Feedback in der App.':'Unsichere Fragen werden früher zur Wiederholung eingeplant.'}</p><div class="header-actions">${pending?`<a class="button primary" href="#reviews">${icon('check')}Antwortprüfungen ansehen</a>`:button('Noch eine Session','reset-study','primary','repeat')}<a class="button secondary" href="#progress">${icon('chart')}Lernfortschritt ansehen</a>${pending?button('Noch eine Session','reset-study','secondary','repeat'):''}</div></div>`;
  }
  const q = study.questions[study.index];
  const selected = study.selected;
  const revealing = study.stage !== 'answer';
  const graded = study.stage === 'graded';
  const pending = study.stage === 'pending';
  const saved = graded || pending;
  const m = moduleBy(q.module_id);
  const image = state.materials.find(f=>f.id===q.image_material_id);
  const result = study.results[study.index];
  const correct = result?.rating === 2;
  const imageHtml = image ? `<div class="question-image"><img src="${image.file_url}" alt="Abbildung zur Lernfrage: ${esc(image.name)}"><a href="${image.file_url}" target="_blank" rel="noopener">Abbildung öffnen ${icon('arrow')}</a></div>` : '';
  const options = q.type === 'multiple_choice' ? `<div class="answer-options">${q.options.map((value,i)=>`<button class="answer-option ${i===selected?'selected':''} ${revealing&&i===q.correct_index?'correct':''} ${revealing&&i===selected&&i!==q.correct_index?'wrong':''}" data-action="select-answer" data-index="${i}" ${revealing||study.busy?'disabled':''}><span class="option-letter">${String.fromCharCode(65+i)}</span><span>${esc(value)}</span>${revealing&&i===q.correct_index?icon('check'):''}</button>`).join('')}</div>` : `<div class="field"><label for="study-answer">Deine Antwort</label><textarea id="study-answer" rows="5" maxlength="20000" data-study-answer placeholder="Erkläre es in deinen eigenen Worten …" ${revealing||study.busy?'readonly':''}>${esc(study.answer)}</textarea></div>`;
  const feedback = pending ? `<div class="feedback pending-feedback"><span class="badge violet">Wartet auf Prüfung</span><h3>Deine Antwort ist gespeichert.</h3><p>Schreib im zugehörigen Codex-Chat: „Prüf meine offenen Antworten.“ Die Prüfung berücksichtigt die Frage und deine Vorlesungsunterlagen. Die Rückmeldung erscheint hier in der App.</p><p class="form-help">Bis dahin erhält diese Antwort keine Bewertung. Du findest sie unter <a href="#reviews">Antwortprüfungen</a>.</p></div>` : revealing ? `<div class="feedback ${graded?(correct?'correct':'partial'):''}"><span class="badge ${graded?(correct?'green':'orange'):'violet'}">${graded?(q.type==='multiple_choice'?(correct?'Richtig beantwortet':'Noch einmal ansehen'):['Noch unsicher','Teilweise verstanden','Sicher verstanden'][result.rating]):'Vergleiche deine Antwort'}</span><h3>Musterantwort</h3><p class="answer-reference">${esc(q.answer)}</p>${q.explanation?`<p>${esc(q.explanation)}</p>`:''}${sourceLine(q)}${q.type!=='multiple_choice'&&!graded?`<p class="form-help">Du kannst die Antwort zur Prüfung speichern oder selbst einschätzen. Deine Einschätzung bestimmt die nächste Wiederholung.</p>${button('Zur Prüfung speichern','submit-free-answer','primary small','check',study.busy?'disabled':'')}${aiStatus.configured?button(study.busy?'KI prüft …':'KI-Rückmeldung anfordern','evaluate-answer','secondary small','sparkle',study.busy?'disabled':''):''}${study.evaluation?`<div class="ai-feedback"><strong>KI-Vorschlag: ${['Noch unsicher','Teilweise verstanden','Sicher verstanden'][study.evaluation.rating]}</strong><p>${esc(study.evaluation.feedback)}</p></div>`:''}<div class="ratings">${[0,1,2].map((rating)=>`<button class="rating-button rating-${rating}" data-action="rate-answer" data-rating="${rating}" ${study.busy?'disabled':''}><strong>${['Noch unsicher','Teilweise','Sicher'][rating]}</strong><span>${['In 10 Minuten','Morgen','Mit mehr Abstand'][rating]}</span></button>`).join('')}</div>`:''}</div>` : '';
  const actions = saved ? `<span class="form-help">${icon('check')}${pending?'Gespeichert · wartet auf Prüfung':`Gespeichert · nächste Wiederholung ${relDate(questionBy(q.id)?.due_at)}`}</span>${button(study.index+1===study.questions.length?'Session abschließen':'Nächste Frage','next-question','primary','arrow')}` : !revealing ? (q.type==='multiple_choice' ? `<span class="form-help">Wähle eine Antwort aus.</span>${button('Antwort prüfen','submit-choice','primary','check',study.busy?'disabled':'')}` : `<span class="form-help">Im Chat prüfen lassen oder mit der Musterantwort vergleichen.</span><div class="answer-action-buttons">${button('Selbst vergleichen','reveal-answer','secondary','book',study.busy?'disabled':'')}${button(study.busy?'Wird gespeichert …':'Zur Prüfung speichern','submit-free-answer','primary','check',study.busy?'disabled':'')}</div>`) : '<span class="form-help">Speichere zur Prüfung oder wähle eine Selbsteinschätzung.</span>';
  return `<div class="session-header"><a class="button ghost small" href="#learn" data-action="stop-study">${icon('close')}Session beenden</a><span>${study.index+1} von ${study.questions.length} Fragen</span><span class="badge violet">${esc(m?.name)}</span></div><div class="session-progress progress-track"><span class="progress-fill" style="width:${study.index/study.questions.length*100}%"></span></div><section class="learning-card session-card panel"><div class="study-meta"><span class="badge violet">${types[q.type]}</span><span class="badge gray">${esc(q.topic || 'Ohne Thema')}</span><span class="difficulty-pill">${difficulties[q.difficulty]}</span></div><h2>${esc(q.prompt)}</h2>${imageHtml}${options}${feedback}<div class="session-actions">${actions}</div></section>`;
}

function renderReviews() {
  const status = ['pending','reviewed','all'].includes(route.params.get('status')) ? route.params.get('status') : 'pending';
  const answers = (state.answer_submissions || []).filter(a=>!route.moduleId||questionBy(a.question_id)?.module_id===route.moduleId).sort((a,b)=>b.submitted_at.localeCompare(a.submitted_at));
  const pending = answers.filter(a=>a.status==='pending').length;
  const checked = answers.filter(a=>a.status==='reviewed').length;
  const visible = answers.filter(a=>status==='all'||a.status===status);
  const tabs = [['pending','Offen',pending],['reviewed','Geprüft',checked],['all','Alle',answers.length]];
  return pageHeader('VERSTÄNDNIS PRÜFEN','Antwortprüfungen','Deine Freitext- und Bildantworten mit persönlicher Rückmeldung.',button('Aktualisieren','refresh-reviews','ghost','repeat')+button('Prüfauftrag kopieren','copy-review-request','secondary','copy')) +
    `<section class="panel review-instructions"><span class="stat-icon violet">${icon('check')}</span><div><h2>Prüfung im Codex-Chat</h2><p>Speichere beim Lernen deine Antwort zur Prüfung. Schreib dann im zugehörigen Codex-Chat: <strong>„Prüf meine offenen Antworten.“</strong> Die KI liest deine Antworten und Unterlagen und hinterlegt eine Bewertung mit Erklärung.</p><p class="form-help">Das Speichern startet keine automatische Prüfung. Für diesen Weg brauchst du keinen API-Schlüssel. Offene Antworten zählen erst nach der Bewertung zum Lernstand.</p></div></section>` +
    `<div class="toolbar"><nav class="section-tabs" aria-label="Prüfstatus">${tabs.map(([value,label,count])=>`<a class="tab-button ${status===value?'active':''}" href="#reviews?${new URLSearchParams({...(route.moduleId?{module:route.moduleId}:{}),status:value})}" ${status===value?'aria-current="page"':''}>${label}<span class="count-pill">${count}</span></a>`).join('')}</nav>${moduleFilter(route.moduleId)}</div>` +
    (visible.length ? `<div class="answer-reviews">${visible.map(a=>{
      const q=questionBy(a.question_id), m=moduleBy(q?.module_id), unit=unitBy(q?.unit_id);
      const reviewed=a.status==='reviewed', shade=reviewed?(a.rating===2?'green':'orange'):'violet';
      return `<article class="panel answer-review-card"><div class="answer-review-heading"><div><span class="eyebrow">${esc(m?.name)}${unit?` · ${esc(unit.title)}`:''}</span><h2>${esc(q?.prompt)}</h2></div><span class="badge ${shade}">${reviewed?['Noch nicht richtig','Teilweise richtig','Richtig'][a.rating]:'Wartet auf Prüfung'}</span></div><p class="form-help">${types[q?.type]||'Antwort'} · gespeichert am ${date(a.submitted_at)}${reviewed?` · geprüft am ${date(a.reviewed_at)} von ${esc(a.reviewer)}`:''}</p><details class="answer-review-details" ${!reviewed?'open':''}><summary>Deine Antwort${reviewed?' und Rückmeldung':''}</summary><div class="submitted-answer"><h3>Deine Antwort</h3><p>${esc(a.answer)}</p></div>${reviewed?`<div class="review-feedback"><h3>Rückmeldung</h3><p>${esc(a.feedback)}</p></div><div class="answer-reference"><h3>Musterantwort</h3><p>${esc(q?.answer)}</p></div>`:'<p class="form-help">Noch nicht bewertet. Beauftrage die Prüfung im Codex-Chat, sobald du bereit bist.</p>'}${q?sourceLine(q):''}</details></article>`;
    }).join('')}</div>` : `<section class="panel">${empty(status==='reviewed'?'Noch keine geprüften Antworten':'Keine offenen Antworten',status==='reviewed'?'Die Bewertungen erscheinen hier nach der Prüfung im Chat.':'Wähle beim Lernen für Freitext oder Bildfragen „Zur Prüfung speichern“.','check','learn','Lernsession starten')}</section>`);
}
function reviewNotice(moduleId='') {
  const count=pendingAnswers().filter(a=>!moduleId||questionBy(a.question_id)?.module_id===moduleId).length;
  return count?`<section class="panel pending-review-notice"><span class="stat-icon violet">${icon('clock')}</span><div><strong>${count} ${count===1?'Antwort wartet':'Antworten warten'} auf Prüfung</strong><p>Schreib im Codex-Chat: „Prüf meine offenen Antworten.“ Bis zur Bewertung bleibt der Lernstand dieser Antworten offen.</p></div><a class="button secondary small" href="#reviews${moduleId?`?module=${moduleId}`:''}">Antworten ansehen ${icon('arrow')}</a></section>`:'';
}
function renderProgress() {
  const stats=state.stats, totals=stats.totals;
  const topics = (stats.topics || []).filter(t=>!route.moduleId||t.module_id===route.moduleId).sort((a,b)=>(a.mastery_percent ?? 101)-(b.mastery_percent ?? 101));
  return pageHeader('DEIN WISSEN WÄCHST','Sieh, was schon sitzt.','Dein Lernstand entsteht aus bewerteten Antworten. Offene Prüfaufträge bleiben unbewertet.',button('Schwächen üben','learn-weak','primary','target'))+reviewNotice(route.moduleId)+`<div class="stats-grid">${statCard('cards','Bewertete Antworten',totals.attempts||0,'Ohne offene Prüfaufträge')}${statCard('target','Antwortsicherheit',pct(totals.mastery_percent),'Nur bereits geübte Fragen','green')}${statCard('clock','Aktive Lernzeit',`${stats.study_minutes||0} Min.`,'Während der Antworten gemessen','blue')}${statCard('bolt','Lernrhythmus',`${stats.streak||0} Tage`,'Tage in Folge gelernt','orange')}</div><div class="progress-layout"><section class="panel"><div class="panel-header"><div><h2>Deine Lernwoche</h2><p>Beantwortete Fragen in den letzten sieben Tagen.</p></div><span class="badge violet">${(stats.week||[]).reduce((a,d)=>a+d.attempts,0)} Antworten</span></div>${chart()}</section><section class="panel"><div class="panel-header"><div><h2>Stand deiner Module</h2><p>Sicherheit und Umfang gehören zusammen.</p></div></div>${state.modules.length ? state.modules.map(m=>{const s=moduleStats(m.id); const practiced=state.questions.filter(q=>q.module_id===m.id&&q.attempt_count>0).length; return `<div class="topic-row"><span class="module-nav-dot" style="background:${colors[m.color]}"></span><div><a href="#module/${m.id}"><strong>${esc(m.name)}</strong></a><small>${practiced} von ${s.questions} Fragen geübt · ${s.attempts} Antworten</small></div><strong>${pct(s.mastery_percent)}</strong><div class="topic-progress progress-track"><span class="progress-fill" style="width:${s.mastery_percent||0}%"></span></div></div>`;}).join('') : empty('Deine Module fehlen noch','Lege ein Modul an und beginne zu lernen.','book')}</section></div><section class="panel"><div class="panel-header"><div><h2>Wo du ansetzen kannst</h2><p>Themen aus deinem Fragenpool, nach Antwortsicherheit sortiert.</p></div>${moduleFilter(route.moduleId)}</div>${topics.length ? topics.map(t=>`<div class="topic-row"><span class="stat-icon ${t.mastery_percent===null?'gray':t.mastery_percent<100?'orange':'green'}">${icon('target')}</span><div><strong>${esc(t.topic)}</strong><small>${esc(t.module_name)} · ${t.secure} von ${t.questions} Fragen sicher · ${t.attempts} Antworten</small></div><strong>${t.mastery_percent===null?'Noch offen':pct(t.mastery_percent)}</strong><button class="button ghost small" data-action="learn-topic" data-module="${t.module_id}" data-topic="${esc(t.topic)}">Üben ${icon('arrow')}</button></div>`).join('') : empty('Dein Lernstand beginnt mit einer Frage','Sobald du Fragen erstellst und übst, werden hier deine Themen sichtbar.','chart','new-question','Frage erstellen')}</section><section class="panel"><div class="panel-header"><div><h2>Zuletzt gelernt</h2><p>Die letzten gespeicherten Antworten.</p></div></div>${stats.recent_attempts?.length ? `<div class="questions-list">${stats.recent_attempts.filter(a=>!route.moduleId||a.module_id===route.moduleId).map(a=>`<div class="question-row"><span class="question-type ${a.rating===2?'green':'orange'}">${icon(a.rating===2?'check':'repeat')}</span><div class="question-info"><strong>${esc(a.prompt)}</strong><span class="question-meta">${esc(a.module_name)} · ${date(a.answered_at)} · ${types[a.type]}</span></div><span class="badge ${a.rating===2?'green':'orange'}">${['Noch unsicher','Teilweise','Sicher'][a.rating]}</span></div>`).join('')}</div>` : empty('Noch keine Antworten gespeichert','Deine erste Lernsession macht deinen Fortschritt sichtbar.','cards','learn','Lernsession starten')}</section><p class="form-help">Die Antwortsicherheit bezieht sich auf bereits geübte Fragen. Freitext und Bildfragen basieren auf einer gespeicherten Prüfung oder deiner Selbsteinschätzung. Offene Antworten beeinflussen die Antwortsicherheit noch nicht. Die Aktivitätsstatistik verwendet UTC-Kalendertage.</p>`;
}
function renderAI() {
  const selected = moduleBy(route.moduleId) || state.modules[0];
  const readable = selected ? state.materials.filter(m=>m.module_id===selected.id && m.extraction_status==='ready') : [];
  const command = `python cli.py context --module ${selected?.id||'MODUL-ID'} --output kontext.json`;
  return pageHeader('DEINE KI, DEIN LERNRAUM','Aus Unterlagen werden Aha-Momente.','Lass deine KI Fragen erstellen und Antworten prüfen – mit deinen Materialien als Grundlage.') + `<div class="ai-layout"><section class="panel ai-card"><div class="panel-header"><div><span class="eyebrow">IN DER APP</span><h2>Fragen aus deinen Materialien</h2></div><span class="stat-icon violet">${icon('sparkle')}</span></div><div class="connection-state ${aiStatus.configured?'connected':''}"><i class="status-dot"></i><div><strong>${aiStatus.configured ? `${aiStatus.provider==='ollama'?'Ollama':'OpenAI'} eingerichtet` : 'KI-Dienst noch nicht eingerichtet'}</strong><small>${esc(aiStatus.configured?aiStatus.model:aiStatus.reason)}</small></div>${button('Einrichten','ai-setup','ghost small','terminal')}</div><form id="ai-form"><div class="field"><label for="ai-module">Modul</label><select name="module_id" id="ai-module" data-ai-module>${state.modules.map(m=>`<option value="${m.id}" ${selected?.id===m.id?'selected':''}>${esc(m.name)}</option>`).join('')}</select></div><div class="field"><label>Materialien als Grundlage</label><div id="ai-materials" class="ai-materials">${readable.length ? readable.map(f=>`<label class="check-label"><input type="checkbox" name="material_ids" value="${f.id}" checked><span>${icon('file')}${esc(f.name)}</span></label>`).join('') : '<p class="form-help">Lade zuerst lesbare Materialien in dieses Modul hoch. Bei Bildern und Scans kannst du Text ergänzen.</p>'}</div></div><div class="form-grid"><div class="field"><label for="ai-count">Anzahl Fragen</label><select id="ai-count" name="count"><option value="5">5 Fragen</option><option value="10" selected>10 Fragen</option><option value="15">15 Fragen</option><option value="20">20 Fragen</option></select></div><div class="field"><label for="ai-difficulty">Schwierigkeit</label><select id="ai-difficulty" name="difficulty"><option value="1">Leicht</option><option value="2" selected>Mittel</option><option value="3">Anspruchsvoll</option></select></div></div><div class="field"><label>Fragemodelle</label><div class="filter-group"><label class="check-label"><input name="types" value="multiple_choice" type="checkbox" checked>Multiple Choice</label><label class="check-label"><input name="types" value="free_text" type="checkbox" checked>Freitext</label></div></div><p class="form-help ai-disclosure">${aiStatus.provider==='ollama'?'Die ausgewählten Texte werden an deinen konfigurierten Ollama-Dienst gesendet.':'Bei OpenAI werden die ausgewählten Materialtexte an die API gesendet. Dafür benötigst du einen API-Schlüssel; API-Nutzung kann Kosten verursachen.'} Du prüfst die Vorschläge vor dem Speichern.</p><p id="ai-error" class="field-error" role="alert"></p><button type="submit" class="button primary" ${!aiStatus.configured||!readable.length?'disabled':''}>${icon('sparkle')}Fragen vorschlagen lassen</button></form></section><section class="panel ai-card"><div class="panel-header"><div><span class="eyebrow">MIT DEINER EXTERNEN KI</span><h2>Dein Lernraum hat eine CLI.</h2></div><span class="stat-icon blue">${icon('terminal')}</span></div><p>Eine externe KI kann den Kontext eines Moduls lesen, Originaldateien öffnen, deinen Lernstand auswerten und neue Fragen einspielen.</p><div class="ai-examples"><div><span class="step-number">1</span><div><strong>Kontext bereitstellen</strong><p>Materialtexte, Quellen-IDs, vorhandene Fragen und Lernstand.</p></div></div><div><span class="step-number">2</span><div><strong>Gemeinsam Fragen entwickeln</strong><p>Gib deiner KI den Kontext und bitte um Fragen mit Quellenverweis.</p></div></div><div><span class="step-number">3</span><div><strong>Prüfen und übernehmen</strong><p>Importiere die geprüften Fragen direkt in die Modulakte.</p></div></div></div><div class="terminal"><span>IM ORDNER LERNRAUM</span><pre class="code-block">${esc(command)}</pre><button class="icon-button" data-action="copy-context-command" data-module="${selected?.id||''}" aria-label="Kontextbefehl kopieren">${icon('copy')}</button></div><div class="header-actions">${button('Kontext herunterladen','download-context','secondary small','download',selected?`data-module="${selected.id}" disabled="${false}"`.replace(' disabled="false"',''):'disabled')}${button('KI-Fragen importieren','import-questions','ghost small','cards',selected?`data-module="${selected.id}"`:'disabled')}</div><p class="form-help">Die externe KI wird durch deine CLI gestartet. Die App imitiert keine KI-Antworten.</p></section></div>${aiDrafts.length ? `<section class="panel ai-review"><div class="panel-header"><div><h2>${aiDrafts.length} Vorschläge zum Prüfen</h2><p>Kontrolliere Fragen, Lösungen und Quellen. Nur ausgewählte Vorschläge werden gespeichert.</p></div>${button('Ausgewählte speichern','save-proposals','primary','check')}</div><div class="ai-drafts">${aiDrafts.map((q,i)=>`<article class="review-question"><div class="review-question-head"><label class="check-label"><input type="checkbox" data-proposal-index="${i}" checked><strong>Vorschlag ${i+1} · ${types[q.type]}</strong></label>${button('Bearbeiten','edit-proposal','ghost small','edit',`data-index="${i}"`)}</div><h3>${esc(q.prompt)}</h3>${q.type==='multiple_choice'?`<ol type="A">${q.options.map((o,index)=>`<li class="${index===q.correct_index?'correct-proposal':''}">${esc(o)}${index===q.correct_index?' ✓':''}</li>`).join('')}</ol>`:''}<p><strong>Musterantwort:</strong> ${esc(q.answer)}</p><p>${esc(q.explanation)}</p>${sourceLine(q)}</article>`).join('')}</div><p class="form-help">Mit „Ausgewählte speichern“ bestätigst du, dass du diese Vorschläge geprüft hast.</p></section>`:''}`;
}
function render() {
  parseRoute();
  const active = route.view === 'module' ? 'modules' : route.view === 'learn' ? 'questions' : route.view;
  $('#main-nav').innerHTML = navItems.map(([view,label,glyph])=>`<a href="#${view}" ${active===view?'class="active" aria-current="page"':''}>${icon(glyph)}<span>${label}</span>${view==='questions'&&dueCount()?`<span class="nav-count">${dueCount()}</span>`:''}${view==='reviews'&&pendingAnswers().length?`<span class="nav-count">${pendingAnswers().length}</span>`:''}${view==='ai'?'<span class="nav-new">KI</span>':''}</a>`).join('');
  $('#module-nav').innerHTML = state.modules.map(m=>`<a href="#module/${m.id}" ${route.view==='module'&&route.moduleId===m.id?'class="active" aria-current="page"':''}><span class="module-nav-dot" style="background:${colors[m.color]}"></span><span class="module-nav-name">${esc(m.name)}</span><span class="module-nav-count">${moduleStats(m.id).questions}</span></a>`).join('');
  $('#breadcrumb').textContent = route.view==='module' ? moduleBy(route.moduleId)?.name || 'Modul' : route.view==='learn' ? 'Lernsession' : navItems.find(n=>n[0]===route.view)?.[1] || 'Überblick';
  $('#breadcrumb-icon').innerHTML = icon('home');
  $('#search-icon').innerHTML = icon('search');
  const renderers = {overview:renderOverview,modules:renderModules,module:renderModule,materials:()=>materialsView(route.moduleId),questions:()=>questionsView(route.moduleId),reviews:renderReviews,learn:renderLearn,progress:renderProgress,ai:renderAI};
  $('#main').innerHTML = (renderers[route.view] || renderOverview)();
}

function filteredList() {
  const node=$('#filtered-list');
  if (!node) return;
  if (route.view==='materials'||route.tab==='materials') node.innerHTML=materialList(state.materials.filter(f=>(!route.moduleId||f.module_id===route.moduleId)&&(!query||f.name.toLowerCase().includes(query.toLowerCase()))&&(filterType==='all'||(filterType==='readable'?f.extraction_status==='ready':f.mime.startsWith('image/')))));
  else node.innerHTML=questionList(state.questions.filter(q=>(!route.moduleId||q.module_id===route.moduleId)&&(!query||`${q.prompt} ${q.topic}`.toLowerCase().includes(query.toLowerCase()))&&(filterType==='all'||(filterType==='unreviewed'?!q.reviewed:q.type===filterType))));
}
function downloadJSON(value,name) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json;charset=utf-8'}));
  const a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function copy(value) {
  try { await navigator.clipboard.writeText(value); toast('In die Zwischenablage kopiert.'); }
  catch { openModal({title:'Befehl kopieren',description:'Markiere den Befehl und kopiere ihn.',body:`<textarea readonly rows="3">${esc(value)}</textarea>`}); }
}
function globalSearch() {
  openModal({title:'Deinen Lernraum durchsuchen',body:'<label class="search-input"><input id="global-search" placeholder="Modul, Vorlesung, Material oder Frage …" aria-label="Suchbegriff"></label><div id="search-results" class="search-results"><p class="form-help">Suche in deinen Modulnamen, Einheiten, Dateinamen und Lernfragen.</p></div>',wide:true});
  $('#global-search').addEventListener('input',event=>{
    const value=event.target.value.trim().toLocaleLowerCase('de');
    if (!value) { $('#search-results').innerHTML='<p class="form-help">Gib einen Suchbegriff ein.</p>'; return; }
    const results=[...state.modules.filter(m=>`${m.name} ${m.code} ${m.description}`.toLowerCase().includes(value)).map(m=>({glyph:'book',label:m.name,meta:'Modul',href:`#module/${m.id}`})),...state.units.filter(u=>`${u.title} ${u.notes}`.toLowerCase().includes(value)).map(u=>({glyph:u.kind==='practical'?'flask':'book',label:u.title,meta:`${kinds[u.kind]} · ${moduleBy(u.module_id)?.name}`,href:`#module/${u.module_id}?tab=units`})),...state.materials.filter(f=>f.name.toLowerCase().includes(value)).map(f=>({glyph:'file',label:f.name,meta:moduleBy(f.module_id)?.name,action:'material-preview',id:f.id})),...state.questions.filter(q=>`${q.prompt} ${q.topic}`.toLowerCase().includes(value)).map(q=>({glyph:'cards',label:q.prompt,meta:types[q.type],action:'preview-question',id:q.id}))].slice(0,30);
    $('#search-results').innerHTML=results.length ? results.map(r=>r.href?`<a class="search-result" href="${r.href}" data-action="search-navigation">${icon(r.glyph)}<span><strong>${esc(r.label)}</strong><small>${esc(r.meta)}</small></span>${icon('arrow')}</a>`:`<button class="search-result" data-action="${r.action}" data-id="${r.id}">${icon(r.glyph)}<span><strong>${esc(r.label)}</strong><small>${esc(r.meta)}</small></span>${icon('chevron')}</button>`).join('') : empty('Nichts gefunden','Versuche einen anderen Suchbegriff.','search');
  });
}
function previewQuestion(id) {
  const q=questionBy(id); if (!q) return;
  const image=state.materials.find(f=>f.id===q.image_material_id);
  openModal({title:types[q.type],description:`${moduleBy(q.module_id)?.name} · ${q.topic||'Ohne Thema'} · ${difficulties[q.difficulty]}`,wide:true,body:`<div class="question-preview"><h3>${esc(q.prompt)}</h3>${image?`<img src="${image.file_url}" alt="${esc(image.name)}">`:''}${q.type==='multiple_choice'?`<div class="answer-options">${q.options.map((o,i)=>`<div class="answer-option ${i===q.correct_index?'correct':''}"><span class="option-letter">${String.fromCharCode(65+i)}</span>${esc(o)}${i===q.correct_index?icon('check'):''}</div>`).join('')}</div>`:''}<div class="feedback"><h3>Musterantwort</h3><p>${esc(q.answer)}</p>${q.explanation?`<p>${esc(q.explanation)}</p>`:''}${sourceLine(q)}</div><p class="form-help">${q.reviewed?'Geprüft':'Noch nicht geprüft'} · ${q.attempt_count} Antworten · ${q.attempt_count?pct(q.mastery):'Noch ungeübt'} · ${relDate(q.due_at)}</p></div>`,footer:button('Bearbeiten','edit-question','secondary','edit',`data-id="${q.id}"`)+button('Dieses Modul lernen','learn','primary','play',`data-module="${q.module_id}"`)});
}
function setupAI() {
  openModal({title:'KI-Dienst einrichten',description:'Optional. Der externe CLI-Zugriff funktioniert bereits ohne API-Schlüssel.',wide:true,body:`<div class="setup-instructions"><h3>OpenAI</h3><p>Kopiere im Ordner <code>lernraum</code> die Datei <code>.env.example</code> nach <code>.env</code>. Trage einen verfügbaren Modellnamen und deinen eigenen API-Schlüssel ein.</p><pre class="code-block">LERNRAUM_AI_PROVIDER=openai\nLERNRAUM_AI_MODEL=DEIN_MODELL\nOPENAI_API_KEY=DEIN_SCHLUESSEL</pre><h3>Oder ein lokales Modell mit Ollama</h3><p>Starte Ollama auf deinem Rechner mit einem bereits installierten Modell und verwende:</p><pre class="code-block">LERNRAUM_AI_PROVIDER=ollama\nLERNRAUM_AI_MODEL=DEIN_INSTALLIERTES_MODELL\nLERNRAUM_OLLAMA_URL=http://127.0.0.1:11434</pre><p>Starte Lernraum danach neu. Zugangsdaten werden vom Server gelesen und erscheinen nicht im exportierten Lernkontext oder Backup.</p><p class="form-help">Eine konfigurierte Verbindung ist erst nach einer erfolgreichen Anfrage geprüft. Hier wurde noch kein kostenpflichtiger KI-Aufruf ausgeführt.</p></div>`});
}
async function recordAnswer(rating) {
  if (!study || study.busy || ['graded','pending'].includes(study.stage)) return;
  const session=study, q=session.questions[session.index];
  session.busy=true; render();
  try {
    const attempt=await api('/api/attempts',{question_id:q.id,answer:q.type==='multiple_choice'?String(session.selected):session.answer,rating,duration_seconds:Math.min(7200,Math.max(0,Math.round((performance.now()-session.questionStarted)/1000))),evaluation_source:q.type==='multiple_choice'?'automatic':session.evaluation?.rating===rating?'ai':'self'});
    session.results.push(attempt); session.stage='graded';
    state=await api('/api/state'); LR.state=state;
  } finally { session.busy=false; render(); }
}
async function submitFreeAnswer() {
  if (!study || study.busy || !['answer','feedback'].includes(study.stage)) return;
  const session=study, q=session.questions[session.index];
  if (q.type==='multiple_choice') return;
  if (!session.answer.trim()) return toast('Schreibe zuerst deine Antwort auf.',true);
  session.busy=true; render();
  try {
    const answer=await api('/api/answers',{question_id:q.id,answer:session.answer,duration_seconds:Math.min(7200,Math.max(0,Math.round((performance.now()-session.questionStarted)/1000)))});
    session.results.push(answer); session.stage='pending';
    state=await api('/api/state'); LR.state=state;
  } finally { session.busy=false; render(); }
}
async function handleAction(target,event) {
  const action=target.dataset.action, id=target.dataset.id, moduleId=target.dataset.module || route.moduleId || state.modules[0]?.id;
  const d=LR.dialogs;
  if (action==='close-modal') return closeModal();
  if (action==='toggle-menu') return document.body.classList.toggle('nav-open');
  if (action==='settings') return d.settings();
  if (action==='help') return d.help();
  if (action==='search') return globalSearch();
  if (action==='search-navigation') return closeModal();
  if (action==='new-module') return d.module();
  if (action==='edit-module') return d.module(id);
  if (action==='new-unit') return state.modules.length?d.unit(moduleId):d.module();
  if (action==='edit-unit') return d.unit(unitBy(id)?.module_id,id);
  if (action==='upload') return state.modules.length?d.upload(moduleId,target.dataset.unit):d.module();
  if (action==='material-preview') return d.material(id);
  if (action==='new-question') return state.modules.length?d.question(moduleId):d.module();
  if (action==='edit-question') return d.question(questionBy(id)?.module_id,id);
  if (action==='preview-question') return previewQuestion(id);
  if (action==='refresh-reviews') return refresh();
  if (action==='copy-review-request') return copy(`Prüf bitte meine offenen Freitext- und Bildantworten in Lernraum${route.moduleId?` im Modul „${moduleBy(route.moduleId)?.name}“`:''}. Prüfe sie anhand der Vorlesungsunterlagen und speichere Bewertung und erklärendes Feedback in der App.`);
  if (action==='import-questions') return state.modules.length?d.importQuestions(moduleId):d.module();
  if (action==='go-materials') return navigate('materials');
  if (action==='delete-module'||action==='delete-unit'||action==='delete-material'||action==='delete-question') {
    const entity={ 'delete-module':'modules','delete-unit':'units','delete-material':'materials','delete-question':'questions'}[action];
    const item=state[entity].find(v=>v.id===id);
    const label=item?.name || item?.title || item?.prompt || 'Eintrag';
    return d.confirm({title:'Eintrag löschen?',message:`„${label}“ wird gelöscht.${entity==='modules'?' Zugehörige Einheiten, Materialien, Fragen und Lernantworten werden ebenfalls entfernt.':entity==='units'?' Materialien und Fragen bleiben im Modul erhalten.':entity==='questions'?' Die Antworten auf diese Frage werden ebenfalls entfernt.':''}`,onConfirm:async()=>{await api(`/api/${entity}/${id}`,{},'DELETE'); await refresh(); toast('Eintrag gelöscht.');}});
  }
  if (action==='export-questions') { const selectedModule=target.dataset.module||route.moduleId; const data=await api('/api/questions/export'+(selectedModule?`?module_id=${selectedModule}`:'')); return downloadJSON(data,'lernraum-fragen.json'); }
  if (action==='download-context') return downloadJSON(await api(`/api/context?module_id=${moduleId}`),'lernraum-kontext.json');
  if (action==='copy-context-command') return copy(`python cli.py context --module ${moduleId} --output kontext.json`);
  if (action==='ai-setup') return setupAI();
  if (action==='learn'||action==='learn-weak'||action==='learn-topic') {
    event.preventDefault(); closeModal(); study=null;
    const params=new URLSearchParams(); if (target.dataset.module || route.view==='module') params.set('module',moduleId);
    if (action==='learn-weak') params.set('mode','weak');
    if (action==='learn-topic') params.set('topic',target.dataset.topic);
    return navigate('learn'+(params.size?'?'+params:''));
  }
  if (action==='stop-study') { event.preventDefault(); if(study?.busy) return toast('Deine Antwort wird gerade gespeichert.'); return d.confirm({title:'Session beenden?',confirmLabel:'Session beenden',confirmStyle:'secondary',message:'Deine bereits gespeicherten Antworten bleiben erhalten. Die aktuelle, noch nicht gespeicherte Antwort wird verworfen.',onConfirm:()=>{study=null;navigate('learn');}}); }
  if (action==='reset-study') { study=null;return render(); }
  if (action==='select-answer' && study?.stage==='answer' && !study.busy) { study.selected=Number(target.dataset.index); return render(); }
  if (action==='submit-choice' && study?.stage==='answer') { if (study.selected===null) return toast('Wähle zuerst eine Antwort aus.',true); return recordAnswer(2); }
  if (action==='submit-free-answer') return submitFreeAnswer();
  if (action==='reveal-answer' && study?.stage==='answer') { if (!study.answer.trim()) return toast('Schreibe zuerst deine Antwort auf.',true); study.stage='feedback'; return render(); }
  if (action==='rate-answer' && study?.stage==='feedback') return recordAnswer(Number(target.dataset.rating));
  if (action==='next-question' && ['graded','pending'].includes(study?.stage) && !study.busy) { study.index++;study.selected=null;study.answer='';study.stage='answer';study.evaluation=null;study.questionStarted=performance.now();render();window.scrollTo({top:0,behavior:'smooth'});return; }
  if (action==='evaluate-answer' && study?.stage==='feedback' && !study.busy) { study.busy=true;render();try {study.evaluation=await api('/api/ai/evaluate',{question_id:study.questions[study.index].id,answer:study.answer});}finally {study.busy=false;render();} return; }
  if (action==='edit-proposal') { const index=Number(target.dataset.index);return d.question(aiDraftModule,null,aiDrafts[index],edited=>{aiDrafts[index]={...edited,is_ai:true,reviewed:false};render();}); }
  if (action==='save-proposals') {
    const selected=[...document.querySelectorAll('[data-proposal-index]:checked')].map(input=>Number(input.dataset.proposalIndex));
    if (!selected.length) return toast('Wähle mindestens einen geprüften Vorschlag aus.',true);
    return d.confirm({title:'Geprüfte Fragen speichern?',confirmLabel:'Fragen speichern',confirmStyle:'primary',message:`${selected.length} ausgewählte Vorschläge werden als geprüfte Fragen in deinem Modul gespeichert.`,onConfirm:async()=>{await api('/api/questions/import',{module_id:aiDraftModule,questions:selected.map(i=>({...aiDrafts[i],reviewed:true,is_ai:true}))});aiDrafts=aiDrafts.filter((_,i)=>!selected.includes(i));await refresh();toast('Deine geprüften Fragen sind im Fragenpool.');}});
  }
}
document.addEventListener('click',event=>{
  const target=event.target.closest('[data-action]');
  if (!target || target.disabled) return;
  Promise.resolve(handleAction(target,event)).catch(error=>toast(error.message,true));
});
document.addEventListener('input',event=>{
  if (event.target.matches('[data-filter="query"]')) { query=event.target.value; filteredList(); }
  if (event.target.matches('[data-study-answer]') && study) study.answer=event.target.value;
});
document.addEventListener('change',event=>{
  const filter=event.target.dataset.filter;
  if (filter==='type') { filterType=event.target.value;filteredList(); }
  if (filter==='module') navigate(`${route.view}?${new URLSearchParams({module:event.target.value,...(route.view==='reviews'?{status:route.params.get('status')||'pending'}:{})})}`);
  if (event.target.matches('[data-ai-module]')) navigate(`ai?module=${event.target.value}`);
});
document.addEventListener('submit',event=>{
  if (event.target.id==='learn-form') {
    event.preventDefault();
    const form=new FormData(event.target), moduleId=form.get('module_id'),mode=form.get('mode'),type=form.get('type'),topic=route.params.get('topic');
    const candidates=state.questions.filter(q=>q.reviewed&&!awaitingReview(q)&&(!moduleId||q.module_id===moduleId)&&(type==='all'||q.type===type)&&(!topic||(q.topic||'Ohne Thema')===topic)&&(mode==='all'||(mode==='weak'?q.attempt_count>0&&q.mastery<100:due(q))));
    if (!candidates.length) { $('#learn-error').textContent=mode==='weak'?'Hier gibt es noch keine als unsicher bewerteten Fragen. Wähle „Jetzt dran“ oder „Alles mischen“.':'Für diese Auswahl gibt es keine passenden geprüften Fragen. Ändere den Lernmodus oder erstelle Fragen.';return; }
    for (let i=candidates.length-1;i>0;i--) {const j=Math.floor(Math.random()*(i+1));[candidates[i],candidates[j]]=[candidates[j],candidates[i]];}
    study={questions:candidates.slice(0,Number(form.get('count'))),index:0,selected:null,answer:'',stage:'answer',results:[],busy:false,evaluation:null,questionStarted:performance.now()};render();return;
  }
  if (event.target.id==='ai-form') {
    event.preventDefault(); if (pendingAction) return;
    const form=event.target, data=new FormData(form),ids=data.getAll('material_ids'),questionTypes=data.getAll('types');
    if (!ids.length||!questionTypes.length) {$('#ai-error').textContent='Wähle mindestens ein lesbares Material und ein Fragemodell aus.';return;}
    pendingAction=true;const submit=$('[type=submit]',form);submit.disabled=true;submit.innerHTML=`${icon('sparkle')}KI arbeitet …`;$('#ai-error').textContent='';
    api('/api/ai/generate',{module_id:data.get('module_id'),material_ids:ids,count:Number(data.get('count')),difficulty:Number(data.get('difficulty')),types:questionTypes}).then(result=>{aiDrafts=result.questions;aiDraftModule=data.get('module_id');render();$('.ai-review')?.scrollIntoView({behavior:'smooth',block:'start'});toast('Vorschläge sind bereit. Prüfe jetzt Fragen und Quellen.');}).catch(error=>{$('#ai-error') && ($('#ai-error').textContent=error.message);}).finally(()=>{pendingAction=false;if (submit.isConnected){submit.disabled=false;submit.innerHTML=`${icon('sparkle')}Fragen vorschlagen lassen`;}});
  }
});
document.addEventListener('keydown',event=>{
  if ((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k') {event.preventDefault();globalSearch();}
});
$('#modal').addEventListener('click',event=>{if (event.target===$('#modal')) {const rect=$('#modal').getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom) closeModal();}});
window.addEventListener('hashchange',()=>{query='';filterType='all';document.body.classList.remove('nav-open');render();window.scrollTo(0,0);});
async function refreshExternalChanges() {
  if (refreshing || document.hidden || $('#modal').open || pendingAction || ['learn','ai'].includes(route.view) || document.activeElement?.matches('input,textarea,select')) return;
  refreshing = true;
  try {
    const next = await api('/api/state');
    if (JSON.stringify(next) !== JSON.stringify(state)) { state = next; LR.state = state; render(); }
  } catch { /* A later foreground action shows an actionable connection error. */ }
  finally { refreshing = false; }
}
window.addEventListener('focus', refreshExternalChanges);
document.addEventListener('visibilitychange', refreshExternalChanges);
setInterval(refreshExternalChanges, 15000);
async function init() {
  try { const responses=await Promise.all([api('/api/state'),api('/api/ai/status')]);state=responses[0];aiStatus=responses[1];LR.state=state;render(); }
  catch (error) {$('#main').innerHTML=empty('Dein Lernraum ist gerade nicht erreichbar','Starte den lokalen Server mit start.ps1 oder python app.py. Lade danach diese Seite neu.','terminal')+`<p class="field-error">${esc(error.message)}</p>`;}
}
init();
