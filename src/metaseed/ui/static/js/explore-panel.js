// The explorer's entity panel and sidebar sections: everything a profile says
// about an entity, its fields, its rules, and itself. Served by metaseed and
// used by every host that renders the explorer (metaseed's own page and the
// hub's), so the two cannot drift apart.
//
// Contract: the graph payload from /explore/graph carries, per node,
// data.{name, description, ontology_term, seek, fields[], rules[]} and, at the
// top level, rules{profile: [...]} and profiles_meta{profile: {...}}. The page
// provides #editor-panel, #editor-title, #editor-content, and optionally
// #rules-section/#rules-list/#rules-count and #profile-section/#profile-meta.

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// The attributes a field has set beyond name/type/required/items: shown as
// name: value rows, so a plain field is one line and a bound one several.
function renderFieldDetails(details) {
    const rows = Object.entries(details || {}).map(([key, value]) => {
        const shown = (value !== null && typeof value === 'object' && !Array.isArray(value))
            ? Object.entries(value).map(([k, v]) => `${escapeHtml(k)}=${escapeHtml(v)}`).join(', ')
            : escapeHtml(Array.isArray(value) ? value.join(', ') : value);
        return `<div class="field-detail"><span class="field-detail-key">${escapeHtml(key)}</span> ${shown}</div>`;
    });
    return rows.length ? `<div class="field-details">${rows.join('')}</div>` : '';
}

// A validation rule: its name, what it checks, and the parameters it sets.
function renderRule(rule) {
    // Class names are the panel's own (explore-rule-*): the hub's spec builder
    // styles a `.rule-item` of its own as a one-line flex row, and sharing the
    // name squeezed these cards into columns a few words wide.
    const skip = new Set(['name', 'description', 'type', 'applies_to', 'message']);
    const params = Object.entries(rule).filter(([k]) => !skip.has(k))
        .map(([k, v]) => `<span class="explore-rule-param">${escapeHtml(k)}=${escapeHtml(Array.isArray(v) ? v.join(', ') : v)}</span>`).join(' ');
    const applies = Array.isArray(rule.applies_to) ? rule.applies_to.join(', ') : (rule.applies_to || 'all');
    return `<div class="explore-rule" data-testid="rule-${escapeHtml(rule.name)}">
        <div class="explore-rule-header"><strong>${escapeHtml(rule.name)}</strong> <code>${escapeHtml(rule.type || '')}</code></div>
        ${rule.description ? `<div class="explore-rule-description">${escapeHtml(rule.description)}</div>` : ''}
        <div class="explore-rule-meta"><span class="explore-rule-param">applies to ${escapeHtml(applies)}</span>${params ? ' ' + params : ''}</div>
        ${rule.message ? `<div class="explore-rule-message">"${escapeHtml(rule.message)}"</div>` : ''}
    </div>`;
}

// The sidebar's list of every rule of the base profile.
function renderRules(rulesByProfile, baseProfile) {
    const section = document.getElementById('rules-section');
    const list = document.getElementById('rules-list');
    const count = document.getElementById('rules-count');
    if (!section || !list) return;
    const rules = (baseProfile && rulesByProfile[baseProfile]) || Object.values(rulesByProfile || {})[0] || [];
    if (!rules.length) { section.style.display = 'none'; list.innerHTML = ''; return; }
    if (count) count.textContent = `(${rules.length})`;
    list.innerHTML = rules.map(renderRule).join('');
    section.style.display = '';
}

// The sidebar's block about the profile itself: what the builder's profile
// form holds. Laid out as a heading, a subtitle and a paragraph -- a key/value
// grid squeezed the description into a column a few words wide.
function renderProfileMeta(metaByProfile, baseProfile) {
    const section = document.getElementById('profile-section');
    const target = document.getElementById('profile-meta');
    if (!section || !target) return;
    const meta = (baseProfile && metaByProfile[baseProfile]) || Object.values(metaByProfile || {})[0];
    if (!meta) { section.style.display = 'none'; target.innerHTML = ''; return; }
    const facts = [
        meta.root_entity ? `root entity <code>${escapeHtml(meta.root_entity)}</code>` : '',
        meta.ontology ? `ontology <code>${escapeHtml(meta.ontology)}</code>` : '',
    ].filter(Boolean).join(' · ');
    target.innerHTML = `
        <div class="profile-title">${escapeHtml(meta.display_name || meta.name)}</div>
        <div class="profile-subtitle"><code>${escapeHtml(meta.name)}</code> ${escapeHtml(meta.version)}</div>
        ${meta.description ? `<p class="profile-description">${escapeHtml(meta.description)}</p>` : ''}
        ${facts ? `<div class="profile-facts">${facts}</div>` : ''}`;
    section.style.display = '';
}

// The entity's SEEK mapping, when the profile declares one: which ISA role it
// plays, the installed template it binds, the extended metadata it carries.
function renderSeek(seek) {
    if (!seek || !Object.keys(seek).length) return '';
    const rows = Object.entries(seek).map(([k, v]) => {
        const shown = (v && typeof v === 'object') ? Object.entries(v).map(([a, b]) => `${escapeHtml(a)} → ${escapeHtml(b)}`).join(', ') : escapeHtml(v);
        return `<div class="field-detail"><span class="field-detail-key">${escapeHtml(k)}</span> ${shown}</div>`;
    });
    return `<div class="form-section" data-testid="entity-seek"><label class="form-label">SEEK mapping</label><div class="field-details">${rows.join('')}</div></div>`;
}

function renderFieldRow(field) {
    const target = field.items ? ` → <code>${escapeHtml(field.items)}</code>` : '';
    const profiles = (field.profiles || []).map(p => `<span class="profile-tag sm">${escapeHtml(p.split('/')[0])}</span>`).join('');
    const vocabulary = field.vocabulary && field.vocabulary.length
        ? `<details class="field-vocabulary"><summary>controlled vocabulary (${field.vocabulary.length} terms)</summary><ul>${field.vocabulary.map(term => `<li>${escapeHtml(term)}</li>`).join('')}</ul></details>`
        : '';
    const changed = field.attributes_changed && field.attributes_changed.length
        ? `<div class="field-diff-changes">Changed: ${escapeHtml(field.attributes_changed.join(', '))}</div>` : '';
    return `<div class="field-diff-item ${escapeHtml(field.diff_type || '')}" data-testid="field-${escapeHtml(field.name)}">
        <div class="field-diff-header">
            <span>${field.required ? '*' : ''}${escapeHtml(field.name)}</span>
            <code>${escapeHtml(field.type)}</code>${target}
        </div>
        <div class="field-diff-profiles">${profiles}</div>
        ${renderFieldDetails(field.details)}
        ${vocabulary}
        ${changed}
    </div>`;
}

// Fill the panel for one graph node. `node` is the vis.js node whose `data`
// the graph payload produced.
function renderEntityPanel(node) {
    document.getElementById('editor-title').textContent = node.data.name;
    const fields = node.data.fields || [];
    let html = '';
    if (node.data.description || node.data.ontology_term) {
        html += `<div class="form-section entity-about" data-testid="entity-about">
            ${node.data.description ? `<p>${escapeHtml(node.data.description)}</p>` : ''}
            ${node.data.ontology_term ? `<code class="term">${escapeHtml(node.data.ontology_term)}</code>` : ''}
        </div>`;
    }
    html += `<div class="form-section">
            <label class="form-label">Status</label>
            <span class="diff-badge ${escapeHtml(node.data.diff_type || '')}">${escapeHtml(node.data.diff_type || '')}</span>
        </div>
        <div class="form-section">
            <label class="form-label">Present in</label>
            <div class="profile-tags">${Object.entries(node.data.profiles || {}).filter(([, present]) => present).map(([p]) => `<span class="profile-tag">${escapeHtml(p)}</span>`).join('')}</div>
        </div>`;
    html += renderSeek(node.data.seek);
    if (fields.length) {
        html += `<div class="form-section"><label class="form-label">Fields (${fields.length})</label><div class="field-diff-list">${fields.map(renderFieldRow).join('')}</div></div>`;
    }
    const rules = node.data.rules || [];
    if (rules.length) {
        html += `<div class="form-section" data-testid="entity-rules"><label class="form-label">Validation rules (${rules.length})</label>${rules.map(renderRule).join('')}</div>`;
    }
    document.getElementById('editor-content').innerHTML = html;
    document.getElementById('editor-panel').classList.add('open');
}

function selectEntity(nodeId) {
    const node = ERD.getNodes().get(nodeId);
    if (node) renderEntityPanel(node);
}

function closeEditorPanel() {
    document.getElementById('editor-panel').classList.remove('open');
}
