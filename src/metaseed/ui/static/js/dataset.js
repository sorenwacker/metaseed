// Metaseed Dataset Management

var currentDataset = null;

function toggleDatasetDropdown() {
    var menu = document.getElementById('dataset-menu');
    if (menu.classList.contains('hidden')) {
        menu.classList.remove('hidden');
        loadDatasets();
        setTimeout(function() {
            document.addEventListener('click', closeDatasetOnClickOutside);
        }, 0);
    } else {
        menu.classList.add('hidden');
        document.removeEventListener('click', closeDatasetOnClickOutside);
    }
}

function closeDatasetOnClickOutside(e) {
    var dropdown = document.querySelector('.dataset-dropdown');
    if (dropdown && !dropdown.contains(e.target)) {
        var menu = document.getElementById('dataset-menu');
        menu.classList.add('hidden');
        document.removeEventListener('click', closeDatasetOnClickOutside);
    }
}

function loadDatasets() {
    fetch(BASE_URL + '/api/datasets')
        .then(function(response) { return response.json(); })
        .then(function(data) {
            currentDataset = data.current;
            updateDatasetIndicator();
            renderDatasetList(data.datasets);
        })
        .catch(function(err) {
            console.error('Failed to load datasets:', err);
        });
}

function renderDatasetList(datasets) {
    var listDiv = document.getElementById('dataset-list');
    if (!listDiv) return;

    if (datasets.length === 0) {
        listDiv.innerHTML = '<div class="dataset-list-empty">No saved datasets</div>';
        return;
    }

    var html = '';
    datasets.forEach(function(ds) {
        var isActive = ds.name === currentDataset;
        html += '<div class="dataset-item' + (isActive ? ' active' : '') + '">';
        html += '<div class="dataset-item-main" onclick="loadDataset(\'' + escapeHtml(ds.name) + '\')">';
        html += '<span class="dataset-item-name">' + escapeHtml(ds.name) + '</span>';
        html += '<span class="dataset-item-meta">' + ds.profile + ' ' + ds.version;
        html += ' - ' + ds.entity_count + ' entities</span>';
        html += '</div>';
        html += '<button class="btn-dataset-delete" onclick="deleteDataset(\'' + escapeHtml(ds.name) + '\', event)" title="Delete">&times;</button>';
        html += '</div>';
    });
    listDiv.innerHTML = html;
}

function updateDatasetIndicator() {
    var nameSpan = document.getElementById('dataset-name');
    if (nameSpan) {
        nameSpan.textContent = currentDataset || 'Datasets';
    }
}

function saveDataset() {
    var input = document.getElementById('dataset-save-name');
    var name = input.value.trim();

    if (!name) {
        showNotification('Please enter a dataset name', 'error');
        return;
    }

    fetch(BASE_URL + '/api/datasets/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
    })
        .then(function(response) {
            if (!response.ok) {
                return response.json().then(function(data) {
                    throw new Error(data.error || 'Failed to save dataset');
                });
            }
            return response.json();
        })
        .then(function(data) {
            currentDataset = data.name;
            updateDatasetIndicator();
            showNotification('Dataset "' + data.name + '" saved', 'success');
            input.value = '';
            loadDatasets();
        })
        .catch(function(err) {
            showNotification(err.message, 'error');
        });
}

function loadDataset(name) {
    fetch(BASE_URL + '/api/datasets/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
    })
        .then(function(response) {
            if (!response.ok) {
                return response.json().then(function(data) {
                    throw new Error(data.error || 'Failed to load dataset');
                });
            }
            return response.json();
        })
        .then(function(data) {
            currentDataset = data.name;
            showNotification('Loaded "' + data.name + '" (' + data.entity_count + ' entities)', 'success');
            window.location.reload();
        })
        .catch(function(err) {
            showNotification(err.message, 'error');
        });
}

function deleteDataset(name, event) {
    event.stopPropagation();

    if (!confirm('Delete dataset "' + name + '"?')) {
        return;
    }

    fetch(BASE_URL + '/api/datasets/' + encodeURIComponent(name), {
        method: 'DELETE'
    })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.error) {
                showNotification(data.error, 'error');
                return;
            }
            showNotification('Dataset deleted', 'success');
            if (currentDataset === name) {
                currentDataset = null;
                updateDatasetIndicator();
            }
            loadDatasets();
        })
        .catch(function(err) {
            showNotification('Failed to delete dataset', 'error');
        });
}

// Validate dataset name before creating new dataset
function validateDatasetName() {
    var input = document.getElementById('new-dataset-name');
    if (!input) return true;

    var name = input.value.trim();
    if (!name) {
        input.classList.add('invalid');
        input.focus();
        showNotification('Please enter a dataset name', 'error');
        return false;
    }

    if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]*$/.test(name)) {
        input.classList.add('invalid');
        input.focus();
        showNotification('Dataset name must start with a letter or number and contain only letters, numbers, hyphens, and underscores', 'error');
        return false;
    }

    input.classList.remove('invalid');
    return true;
}

// Filter datasets by name or profile
function filterDatasets(query) {
    var cards = document.querySelectorAll('.dataset-card');
    var q = query.toLowerCase().trim();

    cards.forEach(function(card) {
        var name = card.dataset.name || '';
        var profile = card.dataset.profile || '';
        var matches = !q || name.includes(q) || profile.includes(q);
        card.style.display = matches ? '' : 'none';
    });

    // Show "no results" message if all hidden
    var grid = document.querySelector('.datasets-grid');
    var visibleCount = document.querySelectorAll('.dataset-card[style=""], .dataset-card:not([style])').length;
    var noResults = document.getElementById('filter-no-results');

    if (q && visibleCount === 0) {
        if (!noResults) {
            noResults = document.createElement('div');
            noResults.id = 'filter-no-results';
            noResults.className = 'datasets-filter-empty';
            noResults.textContent = 'No datasets match your filter';
            grid.parentNode.insertBefore(noResults, grid.nextSibling);
        }
        noResults.style.display = '';
    } else if (noResults) {
        noResults.style.display = 'none';
    }
}

// Load datasets on page load
document.addEventListener('DOMContentLoaded', function() {
    loadDatasets();
});

// Escape HTML for safe display (shared utility)
function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
