/* Dialogs and forms for Lernraum. Loaded after app.js; all server work goes through LR.api. */
(() => {
  'use strict';

  const LR = window.LR;
  if (!LR) {
    console.error('Lernraum dialogs: window.LR muss vor dialogs.js geladen werden.');
    return;
  }

  const COLORS = ['violet', 'blue', 'green', 'orange', 'rose'];
  const COLOR_LABELS = { violet: 'Violett', blue: 'Blau', green: 'Grün', orange: 'Orange', rose: 'Rosé' };
  const KINDS = ['lecture', 'practical', 'other'];
  const KIND_LABELS = { lecture: 'Vorlesung', practical: 'Praktikum', other: 'Sonstige Einheit' };
  const QUESTION_TYPES = ['multiple_choice', 'free_text', 'image'];
  const PREVIEW_IMAGE_MIMES = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/gif']);
  const MAX_FILE_BYTES = 40 * 1024 * 1024;
  const modal = () => document.querySelector('#modal');
  let actionHandlers = {};
  let submitHandlers = {};
  let listenersReady = false;

  const esc = (value) => LR.esc(value == null ? '' : String(value));
  const enc = (value) => encodeURIComponent(String(value));
  const messageOf = (error) => error?.message || String(error || 'Unbekannter Fehler');
  const modules = () => Array.isArray(LR.state?.modules) ? LR.state.modules : [];
  const units = () => Array.isArray(LR.state?.units) ? LR.state.units : [];
  const materials = () => Array.isArray(LR.state?.materials) ? LR.state.materials : [];
  const questions = () => Array.isArray(LR.state?.questions) ? LR.state.questions : [];

  function toast(message, error = false) {
    if (typeof LR.toast === 'function') LR.toast(message, error);
  }

  async function refreshAfterSave() {
    try { await LR.refresh(); }
    catch (error) { toast(`Die Änderung wurde gespeichert, aber die Ansicht konnte nicht aktualisiert werden: ${messageOf(error)}`, true); }
  }

  function setDialog(options, handlers = {}) {
    if (modal()?.dataset.busyUpload === 'true') {
      toast('Warte, bis der laufende Upload abgeschlossen ist.', true);
      return false;
    }
    bindListeners();
    actionHandlers = handlers.actions || {};
    submitHandlers = handlers.submit || {};
    LR.openModal(options);
    return true;
  }

  function bindListeners() {
    if (listenersReady) return;
    const dialog = modal();
    if (!dialog) return;
    listenersReady = true;
    const dispatch = (event) => {
      const dragEvent = ['dragenter', 'dragover', 'dragleave', 'drop'].includes(event.type);
      const selector = dragEvent ? '[data-dialog-action="upload-dropzone"]' : '[data-dialog-action]';
      const element = event.target.closest?.(selector);
      if (!element || !dialog.contains(element)) return;
      const callback = actionHandlers[element.dataset.dialogAction];
      if (typeof callback === 'function') callback(event, element);
    };
    dialog.addEventListener('click', dispatch);
    dialog.addEventListener('change', dispatch);
    dialog.addEventListener('input', dispatch);
    for (const eventName of ['dragenter', 'dragover', 'dragleave', 'drop']) dialog.addEventListener(eventName, dispatch);
    dialog.addEventListener('cancel', (event) => {
      if (dialog.dataset.busyUpload === 'true') {
        event.preventDefault();
        toast('Warte, bis der laufende Upload abgeschlossen ist.', true);
      }
    });
    dialog.addEventListener('click', (event) => {
      if (dialog.dataset.busyUpload !== 'true' || event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) {
        event.preventDefault();
        event.stopImmediatePropagation();
        toast('Warte, bis der laufende Upload abgeschlossen ist.', true);
      }
    }, true);
    dialog.addEventListener('submit', async (event) => {
      const form = event.target.closest?.('form[data-dialog-form]');
      if (!form || !dialog.contains(form)) return;
      event.preventDefault();
      if (form.dataset.busy === 'true') return;
      if (!form.reportValidity()) return;
      const callback = submitHandlers[form.dataset.dialogForm];
      if (typeof callback === 'function') {
        form.dataset.busy = 'true';
        try { await callback(event, form); }
        finally { if (form.isConnected) delete form.dataset.busy; }
      }
    });
  }

  function formError(form, message = '') {
    if (!form) return;
    const error = form.querySelector('[data-form-error]');
    if (!error) return;
    error.textContent = message;
    error.hidden = !message;
  }

  function submitButtonFor(form) {
    return form.querySelector('[type="submit"]') || Array.from(modal()?.querySelectorAll('button[type="submit"]') || []).find((button) => button.form === form) || null;
  }

  async function withBusy(form, callback, busyText = 'Speichert …') {
    const button = submitButtonFor(form);
    const oldText = button?.textContent;
    const controls = [...form.querySelectorAll('button,[type="submit"]'), ...(button && !form.contains(button) ? [button] : [])];
    const priorDisabled = controls.map((control) => control.disabled);
    if (button) {
      button.disabled = true;
      button.textContent = busyText;
    }
    controls.forEach((control) => { control.disabled = true; });
    formError(form, '');
    try {
      return await callback();
    } catch (error) {
      formError(form, messageOf(error));
      return false;
    } finally {
      controls.forEach((control, index) => { if (control.isConnected) control.disabled = priorDisabled[index]; });
      if (button?.isConnected) {
        button.textContent = oldText;
      }
    }
  }

  function closeAfterSave(form) {
    if (form?.isConnected && modal()?.contains(form)) LR.closeModal();
  }

  function closeButton(label = 'Schließen') {
    return `<button class="button secondary" type="button" data-dialog-action="close">${esc(label)}</button>`;
  }

  function moduleOptions(selected = '') {
    return `<option value="">Modul auswählen …</option>${modules().map((item) =>
      `<option value="${esc(item.id)}" ${item.id === selected ? 'selected' : ''}>${esc(item.name)}</option>`
    ).join('')}`;
  }

  function unitOptions(moduleId, selected = '', includeEmpty = true) {
    const list = units().filter((unit) => unit.module_id === moduleId);
    return `${includeEmpty ? '<option value="">Keine Einheit zugeordnet</option>' : ''}${list.map((unit) =>
      `<option value="${esc(unit.id)}" ${unit.id === selected ? 'selected' : ''}>${esc(unit.title)}</option>`
    ).join('')}`;
  }

  function materialOptions(moduleId, selected = '', imagesOnly = false) {
    const list = materials().filter((item) => item.module_id === moduleId && (!imagesOnly || PREVIEW_IMAGE_MIMES.has(String(item.mime || '').toLowerCase())));
    return `<option value="">Keine Quelle ausgewählt</option>${list.map((item) =>
      `<option value="${esc(item.id)}" ${item.id === selected ? 'selected' : ''}>${esc(item.name)}${item.extraction_status && item.extraction_status !== 'ready' ? ' · Text ergänzen' : ''}</option>`
    ).join('')}`;
  }

  function unitChecklist(moduleId, selectedIds = []) {
    const selected = new Set(selectedIds || []);
    const list = units().filter((unit) => unit.module_id === moduleId);
    if (!list.length) return '<p class="form-help">Für dieses Modul gibt es noch keine Einheiten. Du kannst das Material zuerst ohne Zuordnung speichern.</p>';
    return `<div class="form-grid">${list.map((unit) => `
      <label class="check-label"><input type="checkbox" name="unit_ids" value="${esc(unit.id)}" ${selected.has(unit.id) ? 'checked' : ''}>
        <span>${esc(unit.title)} <small>(${KIND_LABELS[unit.kind] || KIND_LABELS.other})</small></span></label>`).join('')}</div>`;
  }

  function module(id) {
    const existing = id ? modules().find((item) => item.id === id) : null;
    if (id && !existing) {
      toast('Das Modul wurde nicht gefunden. Aktualisiere die Ansicht und versuche es erneut.', true);
      return;
    }
    const formId = 'lr-module-form';
    const body = `
      <form id="${formId}" data-dialog-form="module" novalidate>
        <div class="field-error" data-form-error role="alert" hidden></div>
        <div class="form-grid">
          <div class="field full"><label for="module-name">Modulname</label><input id="module-name" name="name" required maxlength="120" value="${esc(existing?.name)}" placeholder="z. B. Lineare Algebra"></div>
          <div class="field"><label for="module-code">Kürzel</label><input id="module-code" name="code" maxlength="40" value="${esc(existing?.code)}" placeholder="z. B. LA"></div>
          <div class="field"><label for="module-semester">Semester</label><input id="module-semester" name="semester" maxlength="80" value="${esc(existing?.semester)}" placeholder="z. B. Wintersemester 2026/27"></div>
          <div class="field"><label for="module-color">Farbe</label><select id="module-color" name="color">${COLORS.map((color) => `<option value="${color}" ${color === (existing?.color || 'violet') ? 'selected' : ''}>${COLOR_LABELS[color]}</option>`).join('')}</select></div>
          <div class="field full"><label for="module-description">Beschreibung</label><textarea id="module-description" name="description" maxlength="1000" placeholder="Worum geht es in diesem Modul?">${esc(existing?.description)}</textarea></div>
        </div>
      </form>`;
    const footer = `${existing ? '<button class="button danger" type="button" data-dialog-action="delete-module">Modul löschen</button>' : ''}${closeButton()}<button class="button primary" type="submit" form="${formId}">${existing ? 'Änderungen speichern' : 'Modul anlegen'}</button>`;
    setDialog({ title: existing ? 'Modulakte bearbeiten' : 'Modulakte anlegen', description: 'Alle Vorlesungen, Praktika und Materialien dieses Moduls bleiben zusammen.', body, footer }, {
      actions: {
        close: () => LR.closeModal(),
        'delete-module': () => confirm({
          title: 'Modul löschen?',
          message: `„${existing.name}“ und die zugehörigen Daten werden gelöscht. Dieser Schritt kann nicht rückgängig gemacht werden.`,
          onConfirm: async () => {
            await LR.api(`/api/modules/${enc(existing.id)}`, {}, 'DELETE');
            LR.closeModal();
            await refreshAfterSave();
            toast('Modul gelöscht.');
          },
        }),
      },
      submit: {
        module: (event, form) => withBusy(form, async () => {
          const data = Object.fromEntries(new FormData(form).entries());
          const method = existing ? 'PATCH' : 'POST';
          const path = existing ? `/api/modules/${enc(existing.id)}` : '/api/modules';
          await LR.api(path, data, method);
          closeAfterSave(form);
          await refreshAfterSave();
          toast(existing ? 'Modulakte aktualisiert.' : 'Modulakte angelegt.');
          return true;
        }),
      },
    });
  }

  function unit(moduleId, id) {
    const existing = id ? units().find((item) => item.id === id) : null;
    if (id && !existing) {
      toast('Die Einheit wurde nicht gefunden. Aktualisiere die Ansicht und versuche es erneut.', true);
      return;
    }
    const selectedModule = moduleId || existing?.module_id || modules()[0]?.id || '';
    const formId = 'lr-unit-form';
    const dateValue = existing?.date ? String(existing.date).slice(0, 10) : '';
    const body = `
      <form id="${formId}" data-dialog-form="unit" novalidate>
        <div class="field-error" data-form-error role="alert" hidden></div>
        <div class="form-grid">
          <div class="field full"><label for="unit-module">Modul</label><select id="unit-module" name="module_id" required>${moduleOptions(selectedModule)}</select></div>
          <div class="field full"><label for="unit-title">Titel</label><input id="unit-title" name="title" required maxlength="180" value="${esc(existing?.title)}" placeholder="z. B. Vorlesung 4 · Eigenwerte"></div>
          <div class="field"><label for="unit-kind">Art</label><select id="unit-kind" name="kind">${KINDS.map((kind) => `<option value="${kind}" ${kind === (existing?.kind || 'lecture') ? 'selected' : ''}>${kind === 'lecture' ? 'Vorlesung' : kind === 'practical' ? 'Praktikum' : 'Sonstiges'}</option>`).join('')}</select></div>
          <div class="field"><label for="unit-date">Datum</label><input id="unit-date" name="date" type="date" value="${esc(dateValue)}"></div>
          <div class="field full"><label for="unit-notes">Notizen</label><textarea id="unit-notes" name="notes" maxlength="5000" placeholder="Eigene Notizen zur Einheit">${esc(existing?.notes)}</textarea></div>
        </div>
      </form>`;
    const footer = `${existing ? '<button class="button danger" type="button" data-dialog-action="delete-unit">Einheit löschen</button>' : ''}${closeButton()}<button class="button primary" type="submit" form="${formId}">${existing ? 'Änderungen speichern' : 'Einheit anlegen'}</button>`;
    setDialog({ title: existing ? 'Einheit bearbeiten' : 'Einheit anlegen', description: 'Ordne Materialien und Fragen einer Vorlesung oder einem Praktikum zu.', body, footer }, {
      actions: {
        close: () => LR.closeModal(),
        'delete-unit': () => confirm({
          title: 'Einheit löschen?',
          message: `„${existing.title}“ wird gelöscht. Zugeordnete Materialien bleiben im Modul erhalten.`,
          onConfirm: async () => {
            await LR.api(`/api/units/${enc(existing.id)}`, {}, 'DELETE');
            LR.closeModal();
            await refreshAfterSave();
            toast('Einheit gelöscht.');
          },
        }),
      },
      submit: {
        unit: (event, form) => withBusy(form, async () => {
          const data = Object.fromEntries(new FormData(form).entries());
          if (!data.date) delete data.date;
          const method = existing ? 'PATCH' : 'POST';
          const path = existing ? `/api/units/${enc(existing.id)}` : '/api/units';
          await LR.api(path, data, method);
          closeAfterSave(form);
          await refreshAfterSave();
          toast(existing ? 'Einheit aktualisiert.' : 'Einheit angelegt.');
          return true;
        }),
      },
    });
  }

  function upload(moduleId, unitId) {
    let currentModule = moduleId || modules()[0]?.id || '';
    let pendingFiles = [];
    let uploadInProgress = false;
    const formId = 'lr-upload-form';
    const body = () => `
      <form id="${formId}" data-dialog-form="upload" novalidate>
        <div class="field-error" data-form-error role="alert" hidden></div>
        <div class="form-grid">
          <div class="field full"><label for="upload-module">Modul</label><select id="upload-module" name="module_id" required data-dialog-action="upload-module-change">${moduleOptions(currentModule)}</select></div>
          <div class="field full"><span class="field-label">Einheiten</span><div data-unit-list>${unitChecklist(currentModule, unitId ? [unitId] : [])}</div><small class="form-help">Du kannst eine Datei mehreren Einheiten zuordnen.</small></div>
          <div class="field full"><label for="upload-name">Materialname (optional)</label><input id="upload-name" name="name" maxlength="180" placeholder="Standard: Dateiname; bei mehreren Dateien je Dateiname"></div>
          <div class="field full"><label class="dropzone" data-dialog-action="upload-dropzone" for="upload-files"><span><span class="dropzone-icon" aria-hidden="true">↑</span><strong>Dateien hier ablegen oder auswählen</strong><p>Bis zu 40 MiB pro Datei. Die Originaldateien bleiben erhalten.</p><input id="upload-files" type="file" multiple data-dialog-action="upload-files-change"></span></label><div class="upload-list" data-upload-list></div></div>
        </div>
      </form>`;

    function drawFiles() {
      const list = modal()?.querySelector('[data-upload-list]');
      if (!list) return;
      list.innerHTML = pendingFiles.length ? pendingFiles.map((entry) => `
        <div class="upload-item"><span class="file-icon">${esc((entry.file.name.split('.').pop() || 'FILE').slice(0, 4).toUpperCase())}</span><span class="file-info"><strong>${esc(entry.file.name)}</strong><small>${formatBytes(entry.file.size)}</small></span><button class="icon-button" type="button" aria-label="${esc(entry.file.name)} entfernen" data-dialog-action="upload-remove-file" data-file-key="${esc(entry.key)}">×</button></div>`).join('') : '<p class="form-help">Noch keine Dateien ausgewählt.</p>';
    }

    function refreshUnitList(selected = []) {
      const container = modal()?.querySelector('[data-unit-list]');
      if (container) container.innerHTML = unitChecklist(currentModule, selected);
    }

    function addFiles(fileList) {
      if (uploadInProgress) return;
      const error = modal()?.querySelector('[data-form-error]');
      const rejected = [];
      for (const file of Array.from(fileList || [])) {
        if (file.size > MAX_FILE_BYTES) {
          rejected.push(`${file.name} ist größer als 40 MiB`);
          continue;
        }
        if (!pendingFiles.some((entry) => entry.file.name === file.name && entry.file.size === file.size && entry.file.lastModified === file.lastModified)) {
          pendingFiles.push({ key: `${Date.now()}-${Math.random().toString(36).slice(2)}`, file });
        }
      }
      if (error) {
        error.textContent = rejected.join('. ');
        error.hidden = !rejected.length;
      }
      drawFiles();
    }

    setDialog({ title: 'Materialien hinzufügen', description: 'Lade Skripte, Folien, Aufgaben oder Notizen in deine Modulakte.', body: body(), footer: `${closeButton()}<button class="button primary" type="submit" form="${formId}">Dateien hochladen</button>`, wide: true }, {
      actions: {
        close: () => { if (uploadInProgress) toast('Warte, bis der laufende Upload abgeschlossen ist.', true); else LR.closeModal(); },
        'upload-module-change': (event, element) => {
          if (event.type !== 'change') return;
          currentModule = element.value;
          refreshUnitList([]);
        },
        'upload-remove-file': (event, element) => {
          pendingFiles = pendingFiles.filter((entry) => entry.key !== element.dataset.fileKey);
          drawFiles();
        },
        'upload-files-change': (event, input) => {
          if (event.type !== 'change') return;
          addFiles(input.files);
          input.value = '';
        },
        'upload-dropzone': (event, element) => {
          if (!['dragenter', 'dragover', 'dragleave', 'drop'].includes(event.type)) return;
          const dropzone = element.closest('.dropzone') || element;
          if (event.type === 'dragenter' || event.type === 'dragover') {
            event.preventDefault();
            dropzone.classList.add('dragover');
          } else if (event.type === 'dragleave') {
            event.preventDefault();
            if (!dropzone.contains(event.relatedTarget)) dropzone.classList.remove('dragover');
          } else if (event.type === 'drop') {
            event.preventDefault();
            dropzone.classList.remove('dragover');
            addFiles(event.dataTransfer?.files);
          }
        },
      },
      submit: {
        upload: async (event, form) => {
          if (!pendingFiles.length) {
            formError(form, 'Wähle mindestens eine Datei aus.');
            return;
          }
          const submitButton = submitButtonFor(form);
          const oldText = submitButton?.textContent;
          const controls = [...Array.from(form.querySelectorAll('input,select,textarea,button')), ...(submitButton ? [submitButton] : [])];
          const closeControls = Array.from(modal()?.querySelectorAll('[data-dialog-action="close"], [data-action="close-modal"]') || []);
          controls.push(...closeControls);
          const priorDisabled = controls.map((control) => control.disabled);
          uploadInProgress = true;
          if (modal()) modal().dataset.busyUpload = 'true';
          if (submitButton) submitButton.textContent = 'Lade hoch …';
          controls.forEach((control) => { control.disabled = true; });
          formError(form, '');
          let uploaded = 0;
          const selectedUnits = Array.from(form.querySelectorAll('input[name="unit_ids"]:checked')).map((input) => input.value);
          const customName = form.elements.name.value.trim();
          const customNameIsSingleFile = pendingFiles.length === 1;
          try {
            for (const entry of [...pendingFiles]) {
              try {
                const contentBase64 = await readBase64(entry.file);
                await LR.api('/api/materials', {
                  module_id: currentModule,
                  unit_ids: selectedUnits,
                  name: customName && customNameIsSingleFile ? customName : entry.file.name,
                  mime: entry.file.type || mimeFromName(entry.file.name),
                  content_base64: contentBase64,
                }, 'POST');
                pendingFiles = pendingFiles.filter((item) => item.key !== entry.key);
                uploaded += 1;
                drawFiles();
              } catch (error) {
                const message = `${entry.file.name}: ${messageOf(error)}. Diese Datei und die übrigen Dateien sind noch ausgewählt; bereits hochgeladene Dateien wurden aus der Warteschlange entfernt.`;
                formError(form, message);
                if (!modal()?.open) toast(message, true);
                break;
              }
            }
            if (uploaded) {
              try { await LR.refresh(); } catch (error) { toast(`Dateien wurden hochgeladen, die Ansicht konnte aber nicht aktualisiert werden: ${messageOf(error)}`, true); }
            }
            if (!pendingFiles.length && uploaded) {
              LR.closeModal();
              toast(`${uploaded} ${uploaded === 1 ? 'Datei wurde' : 'Dateien wurden'} hochgeladen.`);
            } else if (!uploaded && !form.querySelector('[data-form-error]')?.textContent) {
              formError(form, 'Es wurde keine Datei hochgeladen. Prüfe die Auswahl und versuche es erneut.');
            }
          } finally {
            uploadInProgress = false;
            if (modal()) delete modal().dataset.busyUpload;
            controls.forEach((control, index) => { if (control.isConnected) control.disabled = priorDisabled[index]; });
            if (submitButton?.isConnected) submitButton.textContent = oldText;
          }
        },
      },
    });
    drawFiles();
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function mimeFromName(name) {
    const extension = String(name).split('.').pop()?.toLowerCase();
    return ({
      pdf: 'application/pdf', txt: 'text/plain', md: 'text/markdown', csv: 'text/csv',
      docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', gif: 'image/gif',
    })[extension] || 'application/octet-stream';
  }

  function readBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error(`Datei ${file.name} konnte nicht gelesen werden.`));
      reader.onload = () => {
        const result = String(reader.result || '');
        const comma = result.indexOf(',');
        if (comma < 0) reject(new Error(`Datei ${file.name} konnte nicht in Base64 umgewandelt werden.`));
        else resolve(result.slice(comma + 1));
      };
      reader.readAsDataURL(file);
    });
  }

  async function material(id) {
    let item;
    try {
      item = await LR.api(`/api/materials/${enc(id)}`, undefined, 'GET');
    } catch (error) {
      toast(`Material konnte nicht geladen werden: ${messageOf(error)}`, true);
      return;
    }
    const fileUrl = item.file_url || `/api/materials/${enc(item.id)}/file`;
    const mime = String(item.mime || '').toLowerCase();
    let documentPreview = `<div class="preview-document"><div><strong>${esc(item.name)}</strong><br>${esc(item.extraction_message || 'Originaldatei ist verfügbar.')}</div></div>`;
    if (PREVIEW_IMAGE_MIMES.has(mime)) {
      documentPreview = `<div class="preview-document"><img src="${esc(fileUrl)}" alt="${esc(item.name)}" style="max-width:100%;max-height:300px;object-fit:contain"><span>${esc(item.name)}</span></div>`;
    } else if (mime === 'application/pdf') {
      documentPreview = `<div class="preview-document pdf-preview"><span class="pdf-file-icon">${LR.icon('file')}</span><span class="badge violet">PDF-ORIGINAL</span><strong>${esc(item.name)}</strong><p>${item.page_count || '—'} ${item.page_count === 1 ? 'Seite' : 'Seiten'} · unverändert gespeichert</p><small>Öffne das Original oder lies den Text mit Seitenangaben nebenan.</small></div>`;
    }
    const pages = Array.isArray(item.pages) ? item.pages : [];
    const previewText = pages.length
      ? pages.map((page) => `<section><strong>Seite ${esc(page.page)}</strong><pre>${esc(page.text || '')}</pre></section>`).join('\n\n')
      : esc(item.text || item.extraction_message || 'Für diese Datei liegt kein extrahierter Text vor.');
    const statusLabels = { ready: 'Text verfügbar', needs_ocr: 'Text fehlt · OCR nötig', unsupported: 'Format nicht unterstützt', error: 'Extraktion fehlgeschlagen' };
    const body = `
      <div class="material-preview">
        <div>${documentPreview}<p class="form-help">${esc(statusLabels[item.extraction_status] || item.extraction_status || 'Textstatus unbekannt')}${item.page_count ? ` · ${esc(item.page_count)} Seiten` : ''}</p><a class="button secondary small" href="${esc(fileUrl)}" target="_blank" rel="noopener noreferrer">Original öffnen</a></div>
        <div class="preview-text">${previewText}</div>
      </div>
      <p class="form-help">${esc(item.extraction_message || '')}</p>`;
    const footer = `${item.extraction_status === 'needs_ocr' ? '<button class="button secondary" type="button" data-dialog-action="transcribe">Text manuell ergänzen</button>' : ''}<button class="button danger" type="button" data-dialog-action="delete-material">Material löschen</button><button class="button secondary" type="button" data-dialog-action="edit-material">Bearbeiten</button>${closeButton()}`;
    setDialog({ title: item.name || 'Material', description: 'Originaldatei und ausgelesener Text der Quelle.', body, footer, wide: true }, {
      actions: {
        close: () => LR.closeModal(),
        'edit-material': () => editMaterial(item),
        transcribe: () => editMaterial(item, true),
        'delete-material': () => confirm({
          title: 'Material löschen?',
          message: `„${item.name}“ und die gespeicherte Originaldatei werden gelöscht. Fragen mit dieser Quelle müssen danach erneut geprüft werden. Ein noch verwendetes Fragebild kann erst nach Änderung der Bildfrage gelöscht werden.`,
          onConfirm: async () => {
            await LR.api(`/api/materials/${enc(item.id)}`, {}, 'DELETE');
            await refreshAfterSave();
            toast('Material gelöscht.');
          },
        }),
      },
    });
  }

  function editMaterial(item, startTextEdit = false) {
    const formId = 'lr-material-form';
    const body = `
      <form id="${formId}" data-dialog-form="material" novalidate>
        <div class="field-error" data-form-error role="alert" hidden></div>
        <div class="form-grid">
          <div class="field full"><label for="material-name">Materialname</label><input id="material-name" name="name" required maxlength="180" value="${esc(item.name)}"></div>
          <div class="field full"><span class="field-label">Einheiten</span><div data-unit-list>${unitChecklist(item.module_id, item.unit_ids || [])}</div></div>
          <div class="field full"><label class="check-label"><input type="checkbox" name="replace_text" data-dialog-action="toggle-manual-text" ${startTextEdit ? 'checked' : ''}><span>Extrahierten Text bewusst durch manuell bearbeiteten Text ersetzen</span></label><small class="form-help">Das Original bleibt unverändert. Zugehörige Fragen werden zur erneuten Prüfung markiert; Quellseiten außerhalb des neuen Textes werden entfernt.</small></div>
          <div class="field full"><label for="material-text">Manuell bearbeiteter Text</label><textarea id="material-text" name="text" maxlength="500000" ${startTextEdit ? '' : 'disabled'}>${esc(item.text || '')}</textarea></div>
        </div>
      </form>`;
    setDialog({ title: 'Material bearbeiten', description: 'Name und Zuordnung ändern oder Text ausdrücklich manuell ersetzen.', body, footer: `${closeButton()}<button class="button primary" type="submit" form="${formId}">Änderungen speichern</button>`, wide: true }, {
      actions: {
        close: () => LR.closeModal(),
        'toggle-manual-text': (event, checkbox) => {
          if (event.type !== 'change') return;
          const field = modal()?.querySelector('#material-text');
          if (field) field.disabled = !checkbox.checked;
        },
      },
      submit: {
        material: (event, form) => withBusy(form, async () => {
          const unitIds = Array.from(form.querySelectorAll('input[name="unit_ids"]:checked')).map((input) => input.value);
          const payload = { name: form.elements.name.value.trim(), unit_ids: unitIds };
          if (form.elements.replace_text.checked) payload.text = form.elements.text.value;
          await LR.api(`/api/materials/${enc(item.id)}`, payload, 'PATCH');
          closeAfterSave(form);
          await refreshAfterSave();
          toast('Material aktualisiert.');
          return true;
        }),
      },
    });
  }

  function question(moduleId, id, proposal, onSave) {
    const existing = id ? questions().find((item) => item.id === id) : null;
    if (id && !existing) {
      toast('Die Frage wurde nicht gefunden. Aktualisiere die Ansicht und versuche es erneut.', true);
      return;
    }
    const initial = proposal || existing || {};
    let initialModule = moduleId || initial.module_id || modules()[0]?.id || '';
    let type = QUESTION_TYPES.includes(initial.type) ? initial.type : 'multiple_choice';
    const initialOptions = Array.isArray(initial.options) ? initial.options : [];
    const optionText = initialOptions.join('\n');
    const formId = 'lr-question-form';
    const options = Array.from({ length: Math.max(initialOptions.length, 2) }, (_, index) => `<option value="${index}" ${initial.correct_index === index ? 'selected' : ''}>Option ${index + 1}</option>`).join('');
    const body = `
      <form id="${formId}" data-dialog-form="question" novalidate>
        <div class="field-error" data-form-error role="alert" hidden></div>
        <div class="form-grid">
          <div class="field"><label for="question-module">Modul</label><select id="question-module" name="module_id" required data-dialog-action="question-module-change">${moduleOptions(initialModule)}</select></div>
          <div class="field"><label for="question-unit">Einheit</label><select id="question-unit" name="unit_id">${unitOptions(initialModule, initial.unit_id || '')}</select></div>
          <div class="field"><label for="question-type">Fragetyp</label><select id="question-type" name="type" data-dialog-action="question-type-change">${QUESTION_TYPES.map((value) => `<option value="${value}" ${value === type ? 'selected' : ''}>${value === 'multiple_choice' ? 'Multiple Choice' : value === 'free_text' ? 'Freitext' : 'Bildfrage'}</option>`).join('')}</select></div>
          <div class="field"><label for="question-difficulty">Schwierigkeit</label><select id="question-difficulty" name="difficulty">${[1, 2, 3].map((n) => `<option value="${n}" ${n === (initial.difficulty || 2) ? 'selected' : ''}>${n} · ${n === 1 ? 'leicht' : n === 2 ? 'mittel' : 'anspruchsvoll'}</option>`).join('')}</select></div>
          <div class="field full"><label for="question-prompt">Frage</label><textarea id="question-prompt" name="prompt" required maxlength="5000" placeholder="Was soll gelernt oder erklärt werden?">${esc(initial.prompt)}</textarea></div>
          <div class="field full" data-question-options ${type === 'multiple_choice' ? '' : 'hidden'}><label for="question-options">Antwortoptionen</label><textarea id="question-options" name="options_text" data-dialog-action="question-options-change" placeholder="Eine Antwort pro Zeile">${esc(optionText)}</textarea><small class="form-help">Schreibe eine Antwort pro Zeile und wähle danach die richtige Option anhand ihres Textes aus.</small></div>
          <div class="field" data-question-correct ${type === 'multiple_choice' ? '' : 'hidden'}><label for="question-correct">Richtige Option</label><select id="question-correct" name="correct_index">${options}</select></div>
          <div class="field full" data-question-image ${type === 'image' ? '' : 'hidden'}><label for="question-image-material">Bildmaterial <span aria-hidden="true">*</span></label><select id="question-image-material" name="image_material_id">${materialOptions(initialModule, initial.image_material_id || '', true)}</select><small class="form-help">Die Bildfrage verweist auf ein Bildoriginal aus diesem Modul.</small></div>
          <div class="field full"><label for="question-answer">Musterlösung / erwartete Antwort</label><textarea id="question-answer" name="answer" maxlength="10000" placeholder="Bei Freitext: Kernaussage für den Abgleich">${esc(initial.answer)}</textarea></div>
          <div class="field full"><label for="question-explanation">Erklärung</label><textarea id="question-explanation" name="explanation" maxlength="10000" placeholder="Warum ist die Antwort richtig?">${esc(initial.explanation)}</textarea></div>
          <div class="field"><label for="question-topic">Thema</label><input id="question-topic" name="topic" maxlength="120" value="${esc(initial.topic)}"></div>
          <div class="field"><label for="question-source">Quellmaterial</label><select id="question-source" name="source_material_id">${materialOptions(initialModule, initial.source_material_id || '')}</select></div>
          <div class="field"><label for="question-source-page">Quellseite</label><input id="question-source-page" name="source_page" type="number" min="1" step="1" value="${esc(initial.source_page ?? '')}"></div>
          ${proposal ? '<div class="field full"><p class="form-help">Prüfe Frage und Lösung am Original. Die Änderungen bleiben bis zum Übernehmen in diesem Dialog und werden noch nicht gespeichert.</p></div>' : ''}
        </div>
      </form>`;
    const footer = `${existing ? '<button class="button danger" type="button" data-dialog-action="delete-question">Frage löschen</button>' : ''}${closeButton('Verwerfen')}
      <button class="button primary" type="submit" form="${formId}">${proposal ? 'Vorschlag übernehmen' : existing ? 'Frage speichern' : 'Frage anlegen'}</button>`;
    setDialog({ title: proposal ? 'Frage prüfen' : existing ? 'Frage bearbeiten' : 'Frage anlegen', description: 'Frage, Antwort, Schwierigkeit und Materialquelle festlegen.', body, footer, wide: true }, {
      actions: {
        close: () => LR.closeModal(),
        'question-module-change': (event, select) => {
          if (event.type !== 'change') return;
          initialModule = select.value;
          const form = select.form;
          form.elements.unit_id.innerHTML = unitOptions(initialModule, '');
          form.elements.source_material_id.innerHTML = materialOptions(initialModule, '');
          form.elements.image_material_id.innerHTML = materialOptions(initialModule, '', true);
          form.elements.source_page.value = '';
        },
        'question-type-change': (event, select) => { if (event.type === 'change') toggleQuestionType(select.form, select.value); },
        'question-options-change': (event, field) => { if (event.type === 'input' || event.type === 'change') updateCorrectOptions(field.form); },
        'delete-question': () => confirm({
          title: 'Frage löschen?',
          message: 'Die Frage und ihr Lernfortschritt werden dauerhaft gelöscht.',
          onConfirm: async () => {
            await LR.api(`/api/questions/${enc(existing.id)}`, {}, 'DELETE');
            LR.closeModal();
            await refreshAfterSave();
            toast('Frage gelöscht.');
          },
        }),
      },
      submit: {
        question: (event, form) => withBusy(form, async () => {
          const values = new FormData(form);
          const questionType = String(values.get('type'));
          const optionList = String(values.get('options_text') || '').split(/\r?\n/).map((option) => option.trim()).filter(Boolean);
          const correctValue = String(values.get('correct_index') || '');
          if (questionType === 'multiple_choice' && optionList.length < 2) throw new Error('Multiple Choice braucht mindestens zwei Antwortoptionen.');
          if (questionType === 'multiple_choice' && (!correctValue || Number(correctValue) >= optionList.length)) throw new Error('Wähle eine gültige richtige Antwortoption.');
          const imageId = String(values.get('image_material_id') || '');
          if (questionType === 'image' && !imageId) throw new Error('Wähle das Bildmaterial für die Bildfrage aus.');
          const rawPage = String(values.get('source_page') || '');
          const sourceId = String(values.get('source_material_id') || '');
          if (rawPage && !sourceId) throw new Error('Wähle ein Quellmaterial aus, bevor du eine Quellseite einträgst.');
          const answerText = String(values.get('answer') || '').trim();
          if (questionType !== 'multiple_choice' && !answerText) throw new Error('Freitext- und Bildfragen brauchen eine Musterlösung oder erwartete Antwort.');
          const data = {
            module_id: String(values.get('module_id')),
            unit_id: String(values.get('unit_id') || '') || null,
            type: questionType,
            prompt: String(values.get('prompt') || '').trim(),
            options: questionType === 'multiple_choice' ? optionList : [],
            correct_index: questionType === 'multiple_choice' ? Number(correctValue) : null,
            answer: answerText || (questionType === 'multiple_choice' ? optionList[Number(correctValue)] : ''),
            explanation: String(values.get('explanation') || '').trim(),
            topic: String(values.get('topic') || '').trim(),
            difficulty: Number(values.get('difficulty') || 2),
            source_material_id: sourceId || null,
            source_page: rawPage ? Number(rawPage) : null,
            image_material_id: questionType === 'image' ? imageId : null,
            is_ai: Boolean(initial.is_ai || proposal),
            reviewed: true,
          };
          if (proposal) {
            if (typeof onSave !== 'function') throw new Error('Der Vorschlag kann hier nicht übernommen werden, weil kein Speicherziel bereitsteht.');
            await onSave(data);
            closeAfterSave(form);
            toast('Vorschlag übernommen.');
            return true;
          }
          await LR.api(existing ? `/api/questions/${enc(existing.id)}` : '/api/questions', data, existing ? 'PATCH' : 'POST');
          closeAfterSave(form);
          await refreshAfterSave();
          toast(existing ? 'Frage aktualisiert.' : 'Frage angelegt.');
          return true;
        }),
      },
    });
    toggleQuestionType(modal()?.querySelector('#lr-question-form'), type);
  }

  function toggleQuestionType(form, type) {
    if (!form) return;
    form.querySelectorAll('[data-question-options], [data-question-correct], [data-question-image]').forEach((element) => { element.hidden = true; element.style.display = 'none'; });
    if (type === 'multiple_choice') {
      form.querySelector('[data-question-options]').hidden = false;
      form.querySelector('[data-question-options]').style.display = '';
      form.querySelector('[data-question-correct]').hidden = false;
      form.querySelector('[data-question-correct]').style.display = '';
      updateCorrectOptions(form);
    } else if (type === 'image') {
      form.querySelector('[data-question-image]').hidden = false;
      form.querySelector('[data-question-image]').style.display = '';
    }
    const imageSelect = form.elements.image_material_id;
    if (imageSelect) imageSelect.required = type === 'image';
    const answerField = form.elements.answer;
    if (answerField) answerField.required = type !== 'multiple_choice';
    const correctSelect = form.elements.correct_index;
    if (correctSelect) correctSelect.required = type === 'multiple_choice';
  }

  function updateCorrectOptions(form) {
    if (!form) return;
    const optionField = form.elements.options_text;
    const select = form.elements.correct_index;
    if (!optionField || !select) return;
    const lines = optionField.value.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
    const previous = select.value;
    select.innerHTML = lines.map((line, index) => `<option value="${index}">${optionLetter(index)} · ${esc(line.slice(0, 54))}</option>`).join('');
    if (!lines.length) select.innerHTML = '<option value="">Füge zuerst Antwortoptionen hinzu</option>';
    select.value = Number(previous) < lines.length ? previous : (lines.length ? '0' : '');
  }

  function optionLetter(index) {
    let number = index + 1;
    let label = '';
    while (number > 0) {
      number -= 1;
      label = String.fromCharCode(65 + (number % 26)) + label;
      number = Math.floor(number / 26);
    }
    return label;
  }

  function importQuestions(moduleId) {
    const formId = 'lr-import-form';
    const body = `
      <form id="${formId}" data-dialog-form="import" novalidate>
        <div class="field-error" data-form-error role="alert" hidden></div>
        <div class="form-grid">
          <div class="field"><label for="import-module">Modul</label><select id="import-module" name="module_id" required data-dialog-action="import-module-change">${moduleOptions(moduleId || modules()[0]?.id || '')}</select></div>
          <div class="field"><label for="import-unit">Einheit (optional)</label><select id="import-unit" name="unit_id">${unitOptions(moduleId || modules()[0]?.id || '', '')}</select></div>
          <div class="field full"><label for="import-file">JSON-Datei auswählen</label><input id="import-file" type="file" accept="application/json,.json" data-dialog-action="import-file-change"></div>
          <div class="field full"><label for="import-json">JSON-Fragen</label><textarea id="import-json" name="json" required maxlength="1000000" placeholder='{"questions":[{"type":"multiple_choice","prompt":"…","options":["…","…"],"correct_index":0,"source_material_id":"…","source_page":1}]}'></textarea><small class="form-help">Erlaubt ist ein JSON-Array oder ein Objekt mit einem questions-Array. Modul und Einheit werden aus den Feldern oben übernommen.</small></div>
          <div class="field full"><label class="check-label"><input type="checkbox" name="reviewed" required><span>Ich habe jede Frage, Musterlösung und Quellenangabe am Original geprüft.</span></label></div>
        </div>
      </form>`;
    const footer = `${closeButton()}<button class="button primary" type="submit" form="${formId}">Geprüfte Fragen importieren</button>`;
    setDialog({ title: 'Fragen importieren', description: 'Der Import ist transaktional: Die Fragen werden nur gespeichert, wenn alle Einträge gültig sind.', body, footer, wide: true }, {
      actions: {
        close: () => LR.closeModal(),
        'import-module-change': (event, select) => {
          if (event.type !== 'change') return;
          const unitSelect = select.form.elements.unit_id;
          unitSelect.innerHTML = unitOptions(select.value, '');
        },
        'import-file-change': async (event, input) => {
          if (event.type !== 'change') return;
          const selected = input.files?.[0];
          if (!selected) return;
          if (selected.size > 1024 * 1024) {
            formError(modal()?.querySelector(`#${formId}`), 'Die JSON-Datei ist größer als 1 MiB. Bitte teile sie in kleinere Importe auf.');
            input.value = '';
            return;
          }
          try {
            const textArea = modal()?.querySelector('#import-json');
            if (textArea) textArea.value = await selected.text();
          }
          catch (error) { formError(modal()?.querySelector(`#${formId}`), `Datei konnte nicht gelesen werden: ${messageOf(error)}`); }
        },
      },
      submit: {
        import: (event, form) => withBusy(form, async () => {
          if (!form.elements.reviewed.checked) throw new Error('Bestätige zuerst, dass du Fragen, Lösungen und Quellen geprüft hast.');
          let parsed;
          try { parsed = JSON.parse(form.elements.json.value); } catch (error) { throw new Error(`JSON-Fehler: ${error.message}`); }
          const list = Array.isArray(parsed) ? parsed : parsed?.questions;
          if (!Array.isArray(list) || !list.length) throw new Error('Das JSON muss mindestens eine Frage enthalten.');
          if (!list.every((item) => item && typeof item === 'object' && !Array.isArray(item))) throw new Error('Jeder Eintrag im questions-Array muss ein Objekt sein.');
          const reviewedQuestions = list.map((item) => {
            const fields = { ...item };
            delete fields.module_id;
            delete fields.unit_id;
            return { ...fields, reviewed: true };
          });
          await LR.api('/api/questions/import', {
            module_id: String(form.elements.module_id.value),
            unit_id: String(form.elements.unit_id.value || '') || null,
            questions: reviewedQuestions,
          }, 'POST');
          closeAfterSave(form);
          await refreshAfterSave();
          toast(`${reviewedQuestions.length} ${reviewedQuestions.length === 1 ? 'Frage importiert.' : 'Fragen importiert.'}`);
          return true;
        }),
      },
    });
  }

  function confirm(options) {
    const formId = 'lr-confirm-form';
    const body = `<form id="${formId}" data-dialog-form="confirm"><div class="field-error" data-form-error role="alert" hidden></div><p>${esc(options.message || '')}</p></form>`;
    setDialog({ title: options.title || 'Bitte bestätigen', body, footer: `${closeButton('Abbrechen')}<button class="button ${esc(options.confirmStyle || 'danger')}" type="submit" form="${formId}">${esc(options.confirmLabel || 'Löschen')}</button>` }, {
      actions: { close: () => { LR.closeModal(); options.onCancel?.(); } },
      submit: {
        confirm: (event, form) => withBusy(form, async () => {
          if (typeof options.onConfirm === 'function') await options.onConfirm();
          if (modal()?.querySelector(`#${formId}`) === form) LR.closeModal();
          return true;
        }, 'Wird ausgeführt …'),
      },
    });
  }

  async function settings() {
    const body = `
      <div class="form-grid">
        <div class="field full"><span class="field-label">KI-Verbindung</span><div class="connection-state offline" data-ai-status>Verbindungsstatus wird geladen …</div><p class="form-help">Modellname und API-Schlüssel werden ausschließlich serverseitig aus deiner lokalen .env-Datei oder Umgebung gelesen. Dieses Fenster fordert keinen Schlüssel an und zeigt ihn nie an.</p></div>
        <div class="field full"><span class="field-label">KI einrichten</span><p class="form-help">Setze lokal LERNRAUM_AI_PROVIDER=openai oder ollama und trage dein eigenes LERNRAUM_AI_MODEL ein. Für OpenAI kommt OPENAI_API_KEY hinzu; Ollama verwendet LERNRAUM_OLLAMA_URL (Standardadresse: http://127.0.0.1:11434). Danach den Server neu starten.</p></div>
        <div class="field full"><span class="field-label">Lokale Daten</span><p class="form-help">Datenbank und Originaldateien liegen im Ordner .data/. Sichere sie regelmäßig mit dem ZIP-Backup.</p><a class="button secondary" href="/api/backup" download="lernraum-backup.zip">Backup herunterladen</a></div>
      </div>`;
    setDialog({ title: 'Einstellungen', description: 'Dein Lernraum und deine Dateien bleiben auf diesem Rechner.', body, footer: closeButton() }, { actions: { close: () => LR.closeModal() } });
    try {
      const status = await LR.api('/api/ai/status', undefined, 'GET');
      const target = modal()?.querySelector('[data-ai-status]');
      if (target) {
        target.classList.toggle('offline', !status.configured);
        target.textContent = status.configured
          ? `Eingerichtet · ${status.provider || 'KI'} · ${status.model || 'Modell konfiguriert'}`
          : `Nicht eingerichtet · ${status.reason || 'Lege die KI-Konfiguration in der lokalen .env-Datei fest.'}`;
      }
    } catch (error) {
      const target = modal()?.querySelector('[data-ai-status]');
      if (target) target.textContent = `Status konnte nicht geladen werden: ${messageOf(error)}`;
    }
  }

  function help() {
    const body = `
      <ul class="help-checklist">
        <li><span><strong>1. Modulakte anlegen:</strong> Für jedes deiner Module ein eigenes Modul und darin Vorlesungen oder Praktika erstellen.</span></li>
        <li><span><strong>2. Material sammeln:</strong> Folien, Skripte und Aufgaben hochladen und einer oder mehreren Einheiten zuordnen.</span></li>
        <li><span><strong>3. Fragen lernen:</strong> Multiple Choice, Freitext und Bildfragen erstellen oder aus einem geprüften JSON importieren.</span></li>
        <li><span><strong>4. Antworten im Chat prüfen:</strong> Bei Freitext und Bildfragen „Zur Prüfung speichern“ wählen. Schreib danach im zugehörigen Codex-Chat „Prüf meine offenen Antworten“. Die Rückmeldung erscheint unter „Antwortprüfungen“. Ein API-Schlüssel ist für diesen Ablauf nicht nötig.</span></li>
        <li><span><strong>5. Optionale KI-Anbindung:</strong> KI-Status unter Einstellungen prüfen. Die KI erzeugt Vorschläge, die du vor dem Speichern anhand der Quellen prüfst.</span></li>
      </ul>
      <div class="review-question"><strong>Quellen und Scans</strong><p>Bei jeder KI-Frage sollten Material-ID und Seite aus dem Lernraum-Kontext erhalten bleiben. Scans ohne eingebetteten Text brauchen OCR oder eine manuelle Transkription; Lernraum behauptet nicht, OCR auszuführen.</p></div>
      <div class="review-question"><strong>Kommandozeile</strong><p>Öffne im Terminal den Ordner <code>lernraum</code> und starte <code>python cli.py --help</code>. Mit <code>python cli.py context --module … --unit … --output kontext.json</code> exportierst du Quellen und IDs für einen externen KI-Agenten. Importiere erst nach der Prüfung mit <code>python cli.py questions import DATEI.json --module … --reviewed</code>.</p></div>`;
    setDialog({ title: 'Hilfe', description: 'Ein kurzer Ablauf für deinen Lernraum.', body, footer: closeButton() }, { actions: { close: () => LR.closeModal() } });
  }

  LR.dialogs = { module, unit, upload, material, question, importQuestions, confirm, settings, help };
  bindListeners();
})();
