// Metaseed Core UI Functionality

// Handle collapsible sections
document.addEventListener('click', function(e) {
    var header = e.target.closest('.collapsible-header');
    if (header) {
        var collapsible = header.closest('.collapsible');
        collapsible.classList.toggle('open');
    }
});

// Handle inline table toggle (clicking on title area)
document.addEventListener('click', function(e) {
    var title = e.target.closest('.inline-table-title');
    if (title) {
        var section = title.closest('.inline-table-section');
        section.classList.toggle('collapsed');
    }
});

// Handle profile select change
document.addEventListener('change', function(e) {
    if (e.target.id === 'profile-select') {
        var profile = e.target.value;
        window.location.href = '/profile/' + profile;
    }
});

// Auto-dismiss notifications after 5 seconds
document.addEventListener('htmx:afterSwap', function(e) {
    if (e.target.id === 'notification-container') {
        var notifications = e.target.querySelectorAll('.notification');
        notifications.forEach(function(notification) {
            setTimeout(function() {
                notification.style.opacity = '0';
                setTimeout(function() {
                    notification.remove();
                }, 200);
            }, 5000);
        });
    }
});

// Handle delete confirmation
function confirmDelete(nodeId, nodeLabel) {
    return confirm('Delete "' + nodeLabel + '"?');
}

// Handle page refresh trigger (e.g., after import)
document.body.addEventListener('htmx:afterRequest', function(e) {
    var triggerHeader = e.detail.xhr && e.detail.xhr.getResponseHeader('HX-Trigger');
    if (triggerHeader && triggerHeader.includes('refreshPage')) {
        window.location.reload();
    }
});

// Reset file input after upload (to allow re-uploading same file)
document.addEventListener('htmx:afterRequest', function(e) {
    if (e.target.type === 'file') {
        e.target.value = '';
    }
});

// MCP runs in-process - no WebSocket needed for sync
// State changes are immediate since UI and MCP share the same state

// Graph polling functions (used by graph.js)
var graphPollingInterval = null;

function startGraphPolling() {
    // Poll for MCP changes from external processes (Claude Code via stdio)
    // The /api/graph endpoint reloads from disk to pick up changes
    if (graphPollingInterval) return;

    graphPollingInterval = setInterval(function() {
        var graphContainer = document.getElementById('graph-container');
        if (graphContainer && !graphContainer.classList.contains('hidden')) {
            loadGraph();
        }
    }, 2000);
}

function stopGraphPolling() {
    if (graphPollingInterval) {
        clearInterval(graphPollingInterval);
        graphPollingInterval = null;
    }
}

// Validate entire dataset
function validateDataset() {
    var btn = document.getElementById('validate-btn');
    var panel = document.getElementById('validation-panel');
    var results = document.getElementById('validation-results');

    btn.disabled = true;
    btn.textContent = 'Validating...';

    fetch(BASE_URL + '/api/validate')
        .then(function(response) { return response.json(); })
        .then(function(data) {
            btn.disabled = false;
            btn.textContent = 'Validate';

            if (data.error) {
                showNotification('Validation error: ' + data.error, 'error');
                return;
            }

            // Build results HTML
            var html = '<div class="validation-summary">';
            html += '<span class="validation-total">Total: ' + data.total + '</span>';
            html += '<span class="validation-valid">Valid: ' + data.valid + '</span>';
            html += '<span class="validation-invalid">Invalid: ' + data.invalid + '</span>';
            html += '</div>';

            if (data.invalid > 0) {
                html += '<div class="validation-errors" data-testid="validation-errors">';
                data.results.forEach(function(r) {
                    if (!r.valid) {
                        html += '<div class="validation-item invalid">';
                        html += '<strong>' + r.entity_type + ': ' + r.label + '</strong>';
                        html += '<ul>';
                        r.errors.forEach(function(e) {
                            html += '<li data-testid="validation-error-' + e.field + '"><code>' + e.field + '</code>: ' + e.message + '</li>';
                        });
                        html += '</ul></div>';
                    }
                });
                html += '</div>';
            } else {
                html += '<div class="validation-success" data-testid="validation-success">All entities are valid!</div>';
            }

            results.innerHTML = html;
            panel.classList.remove('hidden');
        })
        .catch(function(err) {
            btn.disabled = false;
            btn.textContent = 'Validate';
            showNotification('Validation failed: ' + err.message, 'error');
        });
}

function closeValidationPanel() {
    document.getElementById('validation-panel').classList.add('hidden');
}

var _dcatCard = null;

function showDcatCard() {
    var btn = document.getElementById('dcat-btn');
    var panel = document.getElementById('dcat-panel');
    var content = document.getElementById('dcat-card-content');

    btn.disabled = true;

    fetch(BASE_URL + '/api/dcat')
        .then(function(response) { return response.json(); })
        .then(function(data) {
            btn.disabled = false;

            if (data.error) {
                showNotification('DCAT error: ' + data.error, 'error');
                return;
            }

            _dcatCard = data;

            var esc = function(s) {
                var d = document.createElement('div');
                d.textContent = s == null ? '' : s;
                return d.innerHTML;
            };

            var attr = function(s) { return esc(s).replace(/"/g, '&quot;'); };

            var name = data.title || data.identifier || 'this dataset';
            var html = '<p class="dcat-card-hint">Catalog/discovery metadata for <strong>'
                + esc(name) + '</strong> — what a data portal or a FAIR tool (F-UJI) would ingest.</p>';

            // Editor for explicit catalog metadata (needed for profiles whose
            // root entity is not a dataset container, e.g. Darwin Core).
            var m = data.metadata || {};
            html += '<details class="dcat-card-meta"><summary>Edit catalog metadata</summary>'
                + '<form class="dcat-meta-form" onsubmit="saveDcatMetadata(event)">'
                + '<label>Title<input name="title" value="' + attr(m.title) + '"></label>'
                + '<label>Description<textarea name="description" rows="2">' + esc(m.description) + '</textarea></label>'
                + '<label>Publisher<input name="publisher" value="' + attr(m.publisher) + '"></label>'
                + '<label>License<input name="license" value="' + attr(m.license) + '"></label>'
                + '<label>Keywords <span class="dcat-meta-hint">(comma-separated)</span>'
                + '<input name="keywords" value="' + attr(m.keywords) + '"></label>'
                + '<button type="submit" class="btn btn-secondary btn-sm">Save metadata</button>'
                + '</form></details>';

            html += '<div class="dcat-card-actions">'
                + '<button class="btn btn-secondary btn-sm" onclick="dcatCopy(\'turtle\')">Copy Turtle</button>'
                + '<button class="btn btn-secondary btn-sm" onclick="dcatDownload(\'turtle\')">Download .ttl</button>'
                + '<button class="btn btn-secondary btn-sm" onclick="dcatCopy(\'jsonld\')">Copy JSON-LD</button>'
                + '<button class="btn btn-secondary btn-sm" onclick="dcatDownload(\'jsonld\')">Download .jsonld</button>'
                + '</div>';
            html += '<h4>Turtle</h4><pre class="dcat-card-pre">' + esc(data.turtle) + '</pre>';
            html += '<h4>JSON-LD</h4><pre class="dcat-card-pre">' + esc(data.jsonld) + '</pre>';

            content.innerHTML = html;
            panel.classList.remove('hidden');
        })
        .catch(function(err) {
            btn.disabled = false;
            showNotification('DCAT failed: ' + err.message, 'error');
        });
}

function dcatCopy(fmt) {
    if (!_dcatCard) { return; }
    var text = fmt === 'turtle' ? _dcatCard.turtle : _dcatCard.jsonld;
    navigator.clipboard.writeText(text).then(function() {
        showNotification('Copied ' + (fmt === 'turtle' ? 'Turtle' : 'JSON-LD'), 'success');
    });
}

function dcatDownload(fmt) {
    if (!_dcatCard) { return; }
    var text = fmt === 'turtle' ? _dcatCard.turtle : _dcatCard.jsonld;
    var ext = fmt === 'turtle' ? 'ttl' : 'jsonld';
    var blob = new Blob([text], { type: 'text/plain' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = (_dcatCard.identifier || 'dataset') + '.' + ext;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function saveDcatMetadata(event) {
    event.preventDefault();
    var body = new URLSearchParams(new FormData(event.target));
    fetch(BASE_URL + '/api/dcat/metadata', { method: 'POST', body: body })
        .then(function(response) {
            if (!response.ok) { throw new Error('HTTP ' + response.status); }
            showNotification('Catalog metadata saved', 'success');
            showDcatCard();  // refresh the card with the new values
        })
        .catch(function(err) {
            showNotification('Save failed: ' + err.message, 'error');
        });
}

function closeDcatPanel() {
    document.getElementById('dcat-panel').classList.add('hidden');
}
