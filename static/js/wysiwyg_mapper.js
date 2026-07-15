/**
 * WYSIWYG Template Field Mapper
 *
 * Renders SVG template with coloured field overlays, supports drag-and-drop
 * repositioning, field type / font / colour editing, and live sample-data preview.
 *
 * Dependencies (loaded externally):
 *   - Interact.js  (drag / resize)
 *   - Pickr        (colour picker)
 *
 * No jQuery required.
 */

'use strict';

/* ------------------------------------------------------------------ */
/*  Constants                                                           */
/* ------------------------------------------------------------------ */

const FIELD_COLORS = {
  recipient_name:  '#4CAF50',
  certificate_id:  '#2196F3',
  issuance_date:   '#9C27B0',
  course_title:    '#FF5722',
  qr_code_zone:    '#FF9800',
  custom_text:     '#607D8B',
  unknown:         '#9E9E9E',
};

const SAMPLE_DATA = {
  recipient_name:  'John Doe',
  certificate_id:  'CERT-000001',
  issuance_date:   'January 1, 2026',
  course_title:    'Advanced Professional Development',
  custom_text:     'Sample Text',
  unknown:         'Sample Text',
};

const DEBOUNCE_MS = 400;

/* ------------------------------------------------------------------ */
/*  Utility helpers                                                      */
/* ------------------------------------------------------------------ */

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function confClass(confidence) {
  if (confidence >= 0.7) return 'confidence-high';
  if (confidence >= 0.4) return 'confidence-medium';
  return 'confidence-low';
}

function confLabel(confidence) {
  if (confidence >= 0.7) return `${Math.round(confidence * 100)}% confident`;
  if (confidence >= 0.4) return `${Math.round(confidence * 100)}% — review recommended`;
  return `${Math.round(confidence * 100)}% — manual review required`;
}

/* ------------------------------------------------------------------ */
/*  TemplateMapper class                                                 */
/* ------------------------------------------------------------------ */

class TemplateMapper {
  /**
   * @param {string} containerId  - ID of the root DOM element
   * @param {{ certTypeId: number, apiBase: string }} options
   */
  constructor(containerId, options) {
    this.container   = document.getElementById(containerId);
    this.certTypeId  = options.certTypeId;
    this.apiBase     = options.apiBase;

    this.svgRoot     = null;       // The live <svg> element in the DOM
    this.fields      = {};         // field_id → field data object
    this.overlays    = {};         // field_id → overlay <div>
    this.selectedId  = null;       // Currently selected field_id
    this.colorPicker = null;       // Pickr instance

    this._syncPosition = debounce(this._syncPositionToServer.bind(this), DEBOUNCE_MS);

    this._buildPropertyPanel();
    this._loadAnalysis();
  }

  /* ---------------------------------------------------------------- */
  /*  Initialisation                                                    */
  /* ---------------------------------------------------------------- */

  _buildPropertyPanel() {
    // Property panel is already in the HTML; just wire up listeners.
    const panel = document.getElementById('propertyPanel');
    if (!panel) return;

    document.getElementById('fieldType')?.addEventListener('change', (e) => {
      if (this.selectedId) this.changeFieldType(this.selectedId, e.target.value);
    });

    document.getElementById('fontFamily')?.addEventListener('change', (e) => {
      if (this.selectedId) this.changeFont(this.selectedId, e.target.value);
    });

    document.getElementById('fontSize')?.addEventListener('change', (e) => {
      if (this.selectedId) this._changeFontSize(this.selectedId, parseFloat(e.target.value));
    });

    document.getElementById('posX')?.addEventListener('change', (e) => {
      if (this.selectedId) this.moveField(this.selectedId, parseFloat(e.target.value), this.fields[this.selectedId]?.y ?? 0);
    });

    document.getElementById('posY')?.addEventListener('change', (e) => {
      if (this.selectedId) this.moveField(this.selectedId, this.fields[this.selectedId]?.x ?? 0, parseFloat(e.target.value));
    });

    // Colour picker initialisation (Pickr)
    const colorEl = document.getElementById('textColor');
    if (colorEl && window.Pickr) {
      this.colorPicker = Pickr.create({
        el: colorEl,
        theme: 'classic',
        default: '#000000',
        components: { preview: true, opacity: false, hue: true,
                      interaction: { hex: true, input: true, save: true } },
      });
      this.colorPicker.on('save', (color) => {
        if (this.selectedId && color) {
          this.changeColor(this.selectedId, color.toHEXA().toString());
        }
      });
    }

    // Populate platform font list
    this._populateFontList();
  }

  _populateFontList() {
    const select = document.getElementById('fontFamily');
    if (!select) return;
    fetch(`${this.apiBase}/match-fonts`, { method: 'POST' })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || !data.fonts) return;
        select.innerHTML = '';
        data.fonts.forEach(f => {
          const opt = document.createElement('option');
          opt.value = f.matched_font;
          opt.textContent = f.matched_font;
          select.appendChild(opt);
        });
      })
      .catch(() => {
        // Fallback: common fonts
        ['Playfair Display', 'Montserrat', 'Lora', 'Cinzel', 'Great Vibes',
         'Roboto', 'Open Sans', 'Dancing Script'].forEach(name => {
          const opt = document.createElement('option');
          opt.value = name; opt.textContent = name;
          select.appendChild(opt);
        });
      });
  }

  /* ---------------------------------------------------------------- */
  /*  Load SVG + analysis from server                                   */
  /* ---------------------------------------------------------------- */

  loadTemplate(svgUrl) {
    fetch(svgUrl)
      .then(r => r.text())
      .then(svgText => {
        const preview = document.getElementById('svgPreview');
        if (!preview) return;
        preview.innerHTML = svgText;
        this.svgRoot = preview.querySelector('svg');
        if (this.svgRoot) {
          this.svgRoot.style.width  = '100%';
          this.svgRoot.style.height = 'auto';
          this.svgRoot.style.display = 'block';
        }
        this._overlayFields();
      })
      .catch(err => console.error('loadTemplate error:', err));
  }

  _loadAnalysis() {
    fetch(`${this.apiBase}/analyze`, { method: 'POST' })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;

        // Merge scored_fields into this.fields
        (data.scored_fields || []).forEach(sf => {
          const existing = this.fields[sf.field_id] || {};
          this.fields[sf.field_id] = { ...existing, ...sf };
        });

        // Also pull raw field geometry from mapping endpoint
        return fetch(`${this.apiBase}/mapping`).then(r => r.ok ? r.json() : null);
      })
      .then(mapping => {
        if (!mapping) return;
        (mapping.fields || []).forEach(f => {
          this.fields[f.field_id] = { ...(this.fields[f.field_id] || {}), ...f };
        });
        this._renderFieldList();
        this._overlayFields();
      })
      .catch(err => console.error('_loadAnalysis error:', err));
  }

  /* ---------------------------------------------------------------- */
  /*  Field list sidebar                                                */
  /* ---------------------------------------------------------------- */

  _renderFieldList() {
    const selector = document.getElementById('fieldSelector');
    if (!selector) return;
    selector.innerHTML = '';

    Object.values(this.fields).forEach(field => {
      const div = document.createElement('div');
      div.className = 'field-list-item';
      div.dataset.fieldId = field.field_id;

      const color = FIELD_COLORS[field.field_type] || FIELD_COLORS.unknown;
      const conf  = field.confidence ?? 0;

      div.innerHTML = `
        <span class="field-dot" style="background:${color}"></span>
        <span class="field-name">${field.field_id}</span>
        <span class="confidence-badge ${confClass(conf)}">${Math.round(conf * 100)}%</span>
      `;
      div.addEventListener('click', () => this.highlightField(field.field_id));
      selector.appendChild(div);
    });
  }

  /* ---------------------------------------------------------------- */
  /*  SVG overlays                                                      */
  /* ---------------------------------------------------------------- */

  _overlayFields() {
    // Remove stale overlays
    Object.values(this.overlays).forEach(el => el.remove());
    this.overlays = {};

    if (!this.svgRoot) return;

    const containerRect = this.svgRoot.getBoundingClientRect();
    const vb = this.svgRoot.viewBox.baseVal;
    const scaleX = containerRect.width  / (vb.width  || 842);
    const scaleY = containerRect.height / (vb.height || 595);

    Object.values(this.fields).forEach(field => {
      const bb = field.bounding_box;
      if (!bb) return;

      const overlay = document.createElement('div');
      overlay.className = 'field-overlay';
      overlay.dataset.fieldId = field.field_id;
      overlay.dataset.type = field.field_type || 'unknown';

      const color = FIELD_COLORS[field.field_type] || FIELD_COLORS.unknown;
      overlay.style.borderColor = color;

      const left   = (bb.x || 0) * scaleX;
      const top    = (bb.y || 0) * scaleY;
      const width  = (bb.width  || 80) * scaleX;
      const height = (bb.height || 20) * scaleY;

      overlay.style.cssText += `
        left:${left}px; top:${top}px;
        width:${width}px; height:${height}px;
        position:absolute;
      `;

      // Label
      const label = document.createElement('span');
      label.className = `field-label ${(field.field_type || 'unknown').split('_')[0]}`;
      label.style.background = color;
      label.textContent = field.field_id;
      overlay.appendChild(label);

      overlay.addEventListener('click', () => this.highlightField(field.field_id));

      const previewContainer = document.getElementById('svgPreview');
      if (previewContainer) {
        previewContainer.style.position = 'relative';
        previewContainer.appendChild(overlay);
      }

      this.overlays[field.field_id] = overlay;
      this._attachDrag(overlay, field.field_id, scaleX, scaleY);
    });
  }

  _attachDrag(overlay, fieldId, scaleX, scaleY) {
    if (!window.interact) return;

    interact(overlay)
      .draggable({
        listeners: {
          move: (event) => {
            const el = event.target;
            const x = (parseFloat(el.dataset.x) || 0) + event.dx;
            const y = (parseFloat(el.dataset.y) || 0) + event.dy;
            el.style.transform = `translate(${x}px, ${y}px)`;
            el.dataset.x = x;
            el.dataset.y = y;

            const newX = (this.fields[fieldId]?.x || 0) + event.dx / scaleX;
            const newY = (this.fields[fieldId]?.y || 0) + event.dy / scaleY;
            this._syncPosition(fieldId, newX, newY);
          },
          end: (event) => {
            const newX = this.fields[fieldId]?.x || 0;
            const newY = this.fields[fieldId]?.y || 0;
            this.moveField(fieldId, newX, newY);
          },
        },
      });
  }

  /* ---------------------------------------------------------------- */
  /*  Public field manipulation                                         */
  /* ---------------------------------------------------------------- */

  highlightField(fieldId) {
    // Deselect previous
    if (this.selectedId && this.overlays[this.selectedId]) {
      this.overlays[this.selectedId].classList.remove('selected');
    }
    this.selectedId = fieldId;

    const overlay = this.overlays[fieldId];
    if (overlay) overlay.classList.add('selected');

    const field = this.fields[fieldId];
    if (!field) return;

    // Show property panel
    const details = document.getElementById('fieldDetails');
    if (details) details.style.display = 'block';

    // Populate inputs
    this._setVal('fieldType',   field.field_type   || 'unknown');
    this._setVal('fontFamily',  field.font_family  || '');
    this._setVal('fontSize',    field.font_size     || '');
    this._setVal('posX',        Math.round(field.x || 0));
    this._setVal('posY',        Math.round(field.y || 0));

    if (this.colorPicker && field.text_color) {
      this.colorPicker.setColor(field.text_color);
    }

    // Confidence indicator
    const conf = field.confidence ?? 0;
    const indicator = document.getElementById('confidenceIndicator');
    if (indicator) {
      indicator.className = `confidence-badge ${confClass(conf)}`;
      indicator.textContent = confLabel(conf);
    }

    // Evidence tooltip
    const evidenceEl = document.getElementById('fieldEvidence');
    if (evidenceEl && field.evidence) {
      evidenceEl.textContent = field.evidence.join(' • ');
    }
  }

  moveField(fieldId, newX, newY) {
    if (!this.fields[fieldId]) return;
    this.fields[fieldId].x = newX;
    this.fields[fieldId].y = newY;
    if (this.fields[fieldId].bounding_box) {
      this.fields[fieldId].bounding_box.x = newX;
      this.fields[fieldId].bounding_box.y = newY;
    }
    // Update SVG element directly
    const svgEl = this.svgRoot?.querySelector(`[id="${fieldId}"]`);
    if (svgEl) {
      svgEl.setAttribute('x', newX);
      svgEl.setAttribute('y', newY);
    }
    // Update property panel
    if (fieldId === this.selectedId) {
      this._setVal('posX', Math.round(newX));
      this._setVal('posY', Math.round(newY));
    }
  }

  _syncPositionToServer(fieldId, x, y) {
    this.fields[fieldId] = { ...(this.fields[fieldId] || {}), x, y };
  }

  resizeField(fieldId, newWidth, newHeight) {
    if (!this.fields[fieldId]) return;
    if (this.fields[fieldId].bounding_box) {
      this.fields[fieldId].bounding_box.width  = newWidth;
      this.fields[fieldId].bounding_box.height = newHeight;
    }
    const overlay = this.overlays[fieldId];
    if (overlay) {
      overlay.style.width  = `${newWidth}px`;
      overlay.style.height = `${newHeight}px`;
    }
  }

  changeFieldType(fieldId, newType) {
    if (!this.fields[fieldId]) return;
    this.fields[fieldId].field_type = newType;

    const overlay = this.overlays[fieldId];
    if (overlay) {
      overlay.dataset.type = newType;
      const color = FIELD_COLORS[newType] || FIELD_COLORS.unknown;
      overlay.style.borderColor = color;
      const label = overlay.querySelector('.field-label');
      if (label) label.style.background = color;
    }
    this._renderFieldList();
  }

  changeFont(fieldId, fontFamily) {
    if (!this.fields[fieldId]) return;
    this.fields[fieldId].font_family = fontFamily;
    const svgEl = this.svgRoot?.querySelector(`[id="${fieldId}"]`);
    if (svgEl) svgEl.setAttribute('font-family', fontFamily);
  }

  _changeFontSize(fieldId, size) {
    if (!this.fields[fieldId] || isNaN(size)) return;
    this.fields[fieldId].font_size = size;
    const svgEl = this.svgRoot?.querySelector(`[id="${fieldId}"]`);
    if (svgEl) svgEl.setAttribute('font-size', `${size}px`);
  }

  changeColor(fieldId, hexColor) {
    if (!this.fields[fieldId]) return;
    this.fields[fieldId].text_color = hexColor;
    const svgEl = this.svgRoot?.querySelector(`[id="${fieldId}"]`);
    if (svgEl) svgEl.setAttribute('fill', hexColor);
  }

  /* ---------------------------------------------------------------- */
  /*  Test preview                                                      */
  /* ---------------------------------------------------------------- */

  testWithSampleData() {
    // Temporarily replace SVG text content with sample data
    const savedTexts = {};
    Object.values(this.fields).forEach(field => {
      const svgEl = this.svgRoot?.querySelector(`[id="${field.field_id}"]`);
      if (!svgEl) return;
      savedTexts[field.field_id] = svgEl.textContent;
      const sample = SAMPLE_DATA[field.field_type] || 'Sample';
      svgEl.textContent = sample;
    });

    // Ask server to generate PDF preview
    fetch(`${this.apiBase}/test-preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sample_data: SAMPLE_DATA }),
    })
      .then(r => {
        if (!r.ok) throw new Error(`Preview failed: ${r.status}`);
        return r.blob();
      })
      .then(blob => {
        const url = URL.createObjectURL(blob);
        this._showPreviewModal(url);
      })
      .catch(err => {
        console.error('testWithSampleData error:', err);
        alert('Preview generation failed. See console for details.');
      })
      .finally(() => {
        // Restore original text
        Object.entries(savedTexts).forEach(([fid, txt]) => {
          const el = this.svgRoot?.querySelector(`[id="${fid}"]`);
          if (el) el.textContent = txt;
        });
      });
  }

  _showPreviewModal(pdfUrl) {
    let modal = document.getElementById('previewModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'previewModal';
      modal.innerHTML = `
        <div class="preview-modal-backdrop"></div>
        <div class="preview-modal-content">
          <button class="preview-modal-close" onclick="document.getElementById('previewModal').style.display='none'">✕</button>
          <iframe id="previewFrame" style="width:100%;height:80vh;border:none;"></iframe>
        </div>`;
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
    document.getElementById('previewFrame').src = pdfUrl;
  }

  /* ---------------------------------------------------------------- */
  /*  Save mapping                                                      */
  /* ---------------------------------------------------------------- */

  saveMapping() {
    const payload = {
      fields: Object.values(this.fields).map(f => ({
        field_id:    f.field_id,
        field_type:  f.field_type,
        x:           f.x,
        y:           f.y,
        font_family: f.font_family,
        font_size:   f.font_size,
        text_color:  f.text_color,
        bounding_box: f.bounding_box,
      })),
    };

    fetch(`${this.apiBase}/mapping`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(data => {
        const btn = document.querySelector('.btn-save');
        if (btn) {
          const orig = btn.textContent;
          btn.textContent = '✓ Saved';
          btn.style.background = '#388E3C';
          setTimeout(() => {
            btn.textContent = orig;
            btn.style.background = '';
          }, 2000);
        }
      })
      .catch(err => {
        console.error('saveMapping error:', err);
        alert('Save failed. Please try again.');
      });
  }

  /* ---------------------------------------------------------------- */
  /*  Utilities                                                         */
  /* ---------------------------------------------------------------- */

  _setVal(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.tagName === 'SELECT') {
      const opt = el.querySelector(`option[value="${value}"]`);
      if (opt) el.value = value;
    } else {
      el.value = value ?? '';
    }
  }
}

/* ------------------------------------------------------------------ */
/*  Global convenience shims used by onclick in the template            */
/* ------------------------------------------------------------------ */

function testPreview() {
  if (window._mapper) window._mapper.testWithSampleData();
}

function saveMapping() {
  if (window._mapper) window._mapper.saveMapping();
}
