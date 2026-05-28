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
    // Polling disabled - UI and MCP share state, no need for constant refresh
    // Graph updates when user interacts or via htmx swaps
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

    fetch('/api/validate')
        .then(function(response) { return response.json(); })
        .then(function(data) {
            btn.disabled = false;
            btn.textContent = 'Validate';

            if (data.error) {
                showNotification('error', 'Validation error: ' + data.error);
                return;
            }

            // Build results HTML
            var html = '<div class="validation-summary">';
            html += '<span class="validation-total">Total: ' + data.total + '</span>';
            html += '<span class="validation-valid">Valid: ' + data.valid + '</span>';
            html += '<span class="validation-invalid">Invalid: ' + data.invalid + '</span>';
            html += '</div>';

            if (data.invalid > 0) {
                html += '<div class="validation-errors">';
                data.results.forEach(function(r) {
                    if (!r.valid) {
                        html += '<div class="validation-item invalid">';
                        html += '<strong>' + r.entity_type + ': ' + r.label + '</strong>';
                        html += '<ul>';
                        r.errors.forEach(function(e) {
                            html += '<li><code>' + e.field + '</code>: ' + e.message + '</li>';
                        });
                        html += '</ul></div>';
                    }
                });
                html += '</div>';
            } else {
                html += '<div class="validation-success">All entities are valid!</div>';
            }

            results.innerHTML = html;
            panel.classList.remove('hidden');
        })
        .catch(function(err) {
            btn.disabled = false;
            btn.textContent = 'Validate';
            showNotification('error', 'Validation failed: ' + err.message);
        });
}

function closeValidationPanel() {
    document.getElementById('validation-panel').classList.add('hidden');
}
