// Metaseed Cross-Entity Lookup (Autocomplete + Modal)

// Track active autocomplete dropdown
var activeAutocomplete = null;
var debounceTimer = null;

// Initialize lookup inputs in a container
function initLookupInputs(container) {
    var inputs = container.querySelectorAll('.lookup-input');
    inputs.forEach(function(input) {
        if (!input.dataset.lookupInitialized) {
            input.dataset.lookupInitialized = 'true';
            input.addEventListener('input', handleLookupInput);
            input.addEventListener('focus', handleLookupFocus);
            input.addEventListener('blur', handleLookupBlur);
            input.addEventListener('keydown', handleLookupKeydown);
        }
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initLookupInputs(document);
});

// Initialize after HTMX swap
document.addEventListener('htmx:afterSwap', function(e) {
    initLookupInputs(e.target);
});

// Handle input typing for autocomplete
function handleLookupInput(e) {
    var input = e.target;
    var lookupType = input.dataset.lookupType;
    var entityType = input.dataset.lookup;
    var query = input.value;

    // Ontology fields use modal only - no inline autocomplete
    if (lookupType === 'ontology') {
        return;
    }

    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function() {
        if (query.length > 0) {
            fetchLookupSuggestions(input, entityType, query);
        } else {
            hideAutocomplete();
        }
    }, 300);
}

// Handle focus to show existing suggestions
function handleLookupFocus(e) {
    var input = e.target;
    var lookupType = input.dataset.lookupType;
    var entityType = input.dataset.lookup;
    var query = input.value;

    // Ontology fields use modal only - no inline autocomplete
    if (lookupType === 'ontology') {
        return;
    }

    if (query.length > 0) {
        fetchLookupSuggestions(input, entityType, query);
    }
}

// Handle blur to hide autocomplete (with delay for clicks)
function handleLookupBlur(e) {
    setTimeout(function() {
        if (!document.activeElement || !document.activeElement.closest('.autocomplete-dropdown')) {
            hideAutocomplete();
        }
    }, 200);
}

// Handle keyboard navigation in autocomplete
function handleLookupKeydown(e) {
    var input = e.target;
    var lookupType = input.dataset.lookupType;
    var entityType = input.dataset.lookup;

    // Tab key: open the lookup modal for better UX
    if (e.key === 'Tab' && !activeAutocomplete) {
        e.preventDefault();
        // Find or create a testid for this input
        var inputId = input.getAttribute('data-testid');
        if (!inputId) {
            inputId = 'lookup-input-' + Date.now();
            input.setAttribute('data-testid', inputId);
        }
        if (lookupType === 'ontology') {
            var ontologies = input.dataset.ontologies || null;
            openOntologyModal(inputId, ontologies, input.dataset.within || null);
        } else {
            openLookupModal(entityType, inputId);
        }
        return;
    }

    if (!activeAutocomplete) return;

    var items = activeAutocomplete.querySelectorAll('.autocomplete-item');
    var activeItem = activeAutocomplete.querySelector('.autocomplete-item.active');
    var activeIndex = Array.from(items).indexOf(activeItem);

    switch (e.key) {
        case 'Tab':
            // Tab with autocomplete visible: select current item and close
            e.preventDefault();
            if (activeItem) {
                selectLookupValue(input, activeItem.dataset.value);
            }
            hideAutocomplete();
            break;
        case 'ArrowDown':
            e.preventDefault();
            if (activeIndex < items.length - 1) {
                if (activeItem) activeItem.classList.remove('active');
                items[activeIndex + 1].classList.add('active');
                scrollIntoViewIfNeeded(items[activeIndex + 1]);
            }
            break;
        case 'ArrowUp':
            e.preventDefault();
            if (activeIndex > 0) {
                if (activeItem) activeItem.classList.remove('active');
                items[activeIndex - 1].classList.add('active');
                scrollIntoViewIfNeeded(items[activeIndex - 1]);
            }
            break;
        case 'Enter':
            e.preventDefault();
            if (activeItem) {
                selectLookupValue(input, activeItem.dataset.value);
            }
            break;
        case 'Escape':
            e.preventDefault();
            hideAutocomplete();
            break;
    }
}

// Helper to scroll item into view in dropdown
function scrollIntoViewIfNeeded(element) {
    var parent = element.parentElement;
    var elementRect = element.getBoundingClientRect();
    var parentRect = parent.getBoundingClientRect();

    if (elementRect.bottom > parentRect.bottom) {
        element.scrollIntoView({ block: 'end', behavior: 'smooth' });
    } else if (elementRect.top < parentRect.top) {
        element.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
}

// Where to ask for suggestions. The standalone application answers at
// /api/lookup/; an application that embeds these tables serves its own — the
// hub's is scoped to a dataset — and says so with data-lookup-url on the input.
function lookupBase(input) {
    return input.dataset.lookupUrl || '/api/lookup/';
}

// Fetch suggestions from API
function fetchLookupSuggestions(input, entityType, query) {
    fetch(lookupBase(input) + encodeURIComponent(entityType) + '?q=' + encodeURIComponent(query))
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            showAutocomplete(input, data.results);
        })
        .catch(function(error) {
            console.error('Lookup error:', error);
        });
}

// Show simple autocomplete dropdown (no inline search - use Tab for modal)
function showAutocomplete(input, results, entityType) {
    hideAutocomplete();

    if (!results || results.length === 0) return;

    var dropdown = document.createElement('div');
    dropdown.className = 'autocomplete-dropdown';
    dropdown.setAttribute('data-testid', 'autocomplete-dropdown');

    results.forEach(function(result, index) {
        var item = document.createElement('div');
        item.className = 'autocomplete-item';
        if (index === 0) item.classList.add('active');
        item.dataset.value = result.value;
        item.innerHTML = '<span class="autocomplete-value">' + escapeHtml(result.value) + '</span>' +
                        (result.label !== result.value ? '<span class="autocomplete-label">' + escapeHtml(result.label) + '</span>' : '');

        item.addEventListener('mousedown', function(e) {
            e.preventDefault();
            selectLookupValue(input, result.value);
        });

        dropdown.appendChild(item);
    });

    // Position dropdown below input
    var wrapper = input.closest('.cell-input-wrapper');
    if (wrapper) {
        wrapper.appendChild(dropdown);
    } else {
        input.parentElement.appendChild(dropdown);
    }

    activeAutocomplete = dropdown;
}

// Hide autocomplete dropdown
function hideAutocomplete() {
    if (activeAutocomplete) {
        activeAutocomplete.remove();
        activeAutocomplete = null;
    }
}

// Select a value from autocomplete
function selectLookupValue(input, value, label) {
    input.value = value;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    hideAutocomplete();

    // Update display if in editable cell
    var cell = input.closest('.editable-cell');
    if (cell) {
        var display = cell.querySelector('.cell-display');
        if (display) {
            // Show "label (ID)" for ontology terms, otherwise just value
            if (label && label !== value) {
                display.textContent = label + ' (' + value + ')';
            } else {
                display.textContent = value;
            }
        }
    }
}

// Escape HTML for safe display
function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// Lookup Modal
// ============================================

var lookupModalInput = null;
var lookupModalEntityType = null;
var lookupModalBase = '/api/lookup/';
var lookupModalSelectedValues = new Set();

// Open lookup modal
function openLookupModal(entityType, inputId) {
    var input = document.querySelector('[data-testid="' + inputId + '"]');
    if (!input) return;

    lookupModalInput = input;
    lookupModalEntityType = entityType;
    lookupModalBase = lookupBase(input);
    lookupModalSelectedValues.clear();

    var modal = document.getElementById('lookup-modal');
    var entityTypeSpan = document.getElementById('lookup-modal-entity-type');
    var searchInput = document.getElementById('lookup-modal-search');
    var resultsDiv = document.getElementById('lookup-modal-results');

    entityTypeSpan.textContent = entityType;
    searchInput.value = '';
    resultsDiv.innerHTML = '<div class="lookup-modal-loading">Loading...</div>';

    // Parse existing values (filter out empty strings and empty list notation)
    var existingValue = input.value.trim();
    if (existingValue) {
        existingValue.split(',').forEach(function(v) {
            var trimmed = v.trim();
            if (trimmed && trimmed !== '[]') lookupModalSelectedValues.add(trimmed);
        });
    }

    modal.classList.remove('hidden');
    searchInput.focus();

    // Render selected items
    renderSelectedItems();

    // Load all entities of this type
    loadModalResults(entityType, '');

    // Set up search
    searchInput.oninput = function() {
        loadModalResults(entityType, searchInput.value);
    };
}

// Close lookup modal
function closeLookupModal() {
    var modal = document.getElementById('lookup-modal');
    modal.classList.add('hidden');
    lookupModalInput = null;
    lookupModalEntityType = null;
}

// Render selected items with remove buttons
function renderSelectedItems() {
    var selectedDiv = document.getElementById('lookup-modal-selected');
    if (!selectedDiv) return;

    if (lookupModalSelectedValues.size === 0) {
        selectedDiv.innerHTML = '';
        return;
    }

    var html = '';
    lookupModalSelectedValues.forEach(function(value) {
        html += '<span class="lookup-modal-chip">' +
            escapeHtml(value) +
            '<button type="button" class="lookup-modal-chip-remove" data-value="' + escapeHtml(value) + '" title="Remove">-</button>' +
            '</span>';
    });
    selectedDiv.innerHTML = html;

    // Add remove handlers
    selectedDiv.querySelectorAll('.lookup-modal-chip-remove').forEach(function(btn) {
        btn.addEventListener('click', function() {
            removeSelectedValue(this.dataset.value);
        });
    });
}

// Update the input field with current selections
function updateLookupInput() {
    if (!lookupModalInput) return;

    var values = Array.from(lookupModalSelectedValues);
    var valueStr = values.join(', ');

    lookupModalInput.value = valueStr;
    lookupModalInput.dispatchEvent(new Event('change', { bubbles: true }));

    // Update display if in editable cell
    var cell = lookupModalInput.closest('.editable-cell');
    if (cell) {
        var display = cell.querySelector('.cell-display');
        if (display) {
            display.textContent = valueStr;
        }
    }
}

// Add a value to selection
function addSelectedValue(value) {
    if (lookupModalSelectedValues.has(value)) return;
    lookupModalSelectedValues.add(value);
    renderSelectedItems();
    updateLookupInput();
    // Re-render results to update + button state
    var searchInput = document.getElementById('lookup-modal-search');
    loadModalResults(lookupModalEntityType, searchInput ? searchInput.value : '');
}

// Remove a value from selection
function removeSelectedValue(value) {
    lookupModalSelectedValues.delete(value);
    renderSelectedItems();
    updateLookupInput();
    // Re-render results to update + button state
    var searchInput = document.getElementById('lookup-modal-search');
    loadModalResults(lookupModalEntityType, searchInput ? searchInput.value : '');
}

// Load results into modal
function loadModalResults(entityType, query) {
    var resultsDiv = document.getElementById('lookup-modal-results');

    fetch(lookupModalBase + encodeURIComponent(entityType) + '?q=' + encodeURIComponent(query))
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (!data.results || data.results.length === 0) {
                resultsDiv.innerHTML = '';
                return;
            }

            resultsDiv.innerHTML = '';
            data.results.forEach(function(result) {
                var item = document.createElement('div');
                item.className = 'lookup-modal-item';
                item.dataset.value = result.value;

                var isSelected = lookupModalSelectedValues.has(result.value);

                item.innerHTML =
                    '<span class="lookup-modal-item-value">' + escapeHtml(result.value) + '</span>' +
                    (result.label !== result.value ? '<span class="lookup-modal-item-label">' + escapeHtml(result.label) + '</span>' : '') +
                    '<button type="button" class="lookup-modal-item-add' + (isSelected ? ' hidden' : '') + '" title="Add">+</button>';

                var addBtn = item.querySelector('.lookup-modal-item-add');
                addBtn.addEventListener('click', function(e) {
                    e.stopPropagation();
                    addSelectedValue(result.value);
                });

                resultsDiv.appendChild(item);
            });
        })
        .catch(function(error) {
            console.error('Modal lookup error:', error);
            resultsDiv.innerHTML = '<div class="lookup-modal-error">Error loading results</div>';
        });
}

// Handle lookup button clicks
document.addEventListener('click', function(e) {
    var btn = e.target.closest('.lookup-btn');
    if (btn) {
        e.preventDefault();
        e.stopPropagation();
        var entityType = btn.dataset.lookup;
        var inputId = btn.dataset.input;
        openLookupModal(entityType, inputId);
    }

    // Handle ontology lookup button clicks
    var ontologyBtn = e.target.closest('.ontology-lookup-btn');
    if (ontologyBtn) {
        e.preventDefault();
        e.stopPropagation();
        var inputId = ontologyBtn.dataset.input;
        var ontologies = ontologyBtn.dataset.ontologies || null;
        openOntologyModal(inputId, ontologies, ontologyBtn.dataset.within || null);
    }
});

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        var modal = document.getElementById('lookup-modal');
        if (modal && !modal.classList.contains('hidden')) {
            closeLookupModal();
        }
        var ontologyModal = document.getElementById('ontology-modal');
        if (ontologyModal && !ontologyModal.classList.contains('hidden')) {
            closeOntologyModal();
        }
    }
});

// ============================================
// Ontology Modal
// ============================================

var ontologyModalInput = null;
var ontologyModalOntologies = null;
// The branch a column is scoped to, when its field declares one (#229): a
// technology-type column takes one subtree, not a whole ontology.
var ontologyModalWithin = null;
var ontologyModalSelectedValues = new Map(); // Map of value -> label

// Open ontology modal
function openOntologyModal(inputId, ontologies, within) {
    var input = document.querySelector('[data-testid="' + inputId + '"]');
    if (!input) return;

    ontologyModalInput = input;
    ontologyModalOntologies = ontologies;
    ontologyModalWithin = within || input.dataset.within || null;
    ontologyModalSelectedValues = new Map();

    var modal = document.getElementById('ontology-modal');
    if (!modal) {
        // Create modal if it doesn't exist
        modal = createOntologyModal();
        document.body.appendChild(modal);
    }

    var ontologyLabel = document.getElementById('ontology-modal-ontology');
    var searchInput = document.getElementById('ontology-modal-search');
    var resultsDiv = document.getElementById('ontology-modal-results');

    ontologyLabel.textContent = ontologies ? ontologies.toUpperCase() : 'All Ontologies';
    searchInput.value = '';
    resultsDiv.innerHTML = '<div class="lookup-modal-empty">Start typing to search ontology terms</div>';

    // Parse existing values (stored as IDs only, labels unknown)
    // In single-select mode, only load first value
    var isMulti = input.dataset.multi === 'true';
    var existingValue = input.value.trim();
    if (existingValue) {
        var values = existingValue.split(',');
        var maxValues = isMulti ? values.length : 1;
        for (var i = 0; i < Math.min(values.length, maxValues); i++) {
            var trimmed = values[i].trim();
            if (trimmed && trimmed !== '[]') {
                ontologyModalSelectedValues.set(trimmed, null); // label unknown for existing values
            }
        }
    }

    modal.classList.remove('hidden');
    searchInput.focus();

    // Render selected items
    renderOntologySelectedItems();

    // Set up search with debounce
    var searchDebounce = null;
    searchInput.oninput = function() {
        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(function() {
            if (searchInput.value.length >= 2) {
                loadOntologyModalResults(searchInput.value);
            } else {
                resultsDiv.innerHTML = '<div class="lookup-modal-empty">Type at least 2 characters to search</div>';
            }
        }, 300);
    };
}

// Create ontology modal HTML
function createOntologyModal() {
    var modal = document.createElement('div');
    modal.id = 'ontology-modal';
    modal.className = 'lookup-modal hidden';
    modal.setAttribute('data-testid', 'ontology-modal');

    modal.innerHTML = '<div class="lookup-modal-backdrop" onclick="closeOntologyModal()"></div>' +
        '<div class="lookup-modal-content ontology-modal-content">' +
        '<div class="lookup-modal-header">' +
        '<h3>Search Ontology: <span id="ontology-modal-ontology">All</span></h3>' +
        '<button type="button" class="lookup-modal-close" onclick="closeOntologyModal()">&times;</button>' +
        '</div>' +
        '<div class="lookup-modal-body">' +
        '<input type="text" id="ontology-modal-search" class="lookup-modal-search" ' +
        'placeholder="Search terms (e.g., temperature, drought)..." autocomplete="off">' +
        '<div id="ontology-modal-selected" class="lookup-modal-selected"></div>' +
        '<div id="ontology-modal-results" class="lookup-modal-results ontology-results"></div>' +
        '</div>' +
        '<div class="lookup-modal-footer">' +
        '<button type="button" class="btn btn-secondary" onclick="closeOntologyModal()">Done</button>' +
        '</div>' +
        '</div>';

    return modal;
}

// Close ontology modal
function closeOntologyModal() {
    var modal = document.getElementById('ontology-modal');
    if (modal) {
        modal.classList.add('hidden');
    }
    ontologyModalInput = null;
    ontologyModalOntologies = null;
    ontologyModalWithin = null;
}

// Render selected ontology items
function renderOntologySelectedItems() {
    var selectedDiv = document.getElementById('ontology-modal-selected');
    if (!selectedDiv) return;

    if (ontologyModalSelectedValues.size === 0) {
        selectedDiv.innerHTML = '';
        return;
    }

    var html = '';
    ontologyModalSelectedValues.forEach(function(label, value) {
        // Display "label (ID)" if label is known, otherwise just ID
        var displayText = (label && label !== value) ? label + ' (' + value + ')' : value;
        html += '<span class="lookup-modal-chip ontology-chip">' +
            escapeHtml(displayText) +
            '<button type="button" class="lookup-modal-chip-remove" data-value="' + escapeHtml(value) + '" title="Remove">-</button>' +
            '</span>';
    });
    selectedDiv.innerHTML = html;

    // Add remove handlers
    selectedDiv.querySelectorAll('.lookup-modal-chip-remove').forEach(function(btn) {
        btn.addEventListener('click', function() {
            removeOntologySelectedValue(this.dataset.value);
        });
    });
}

// Update input with ontology selections
function updateOntologyInput() {
    if (!ontologyModalInput) return;

    // Store only IDs in the input value (for data integrity)
    var ids = Array.from(ontologyModalSelectedValues.keys());
    var valueStr = ids.join(', ');

    ontologyModalInput.value = valueStr;
    ontologyModalInput.dispatchEvent(new Event('change', { bubbles: true }));

    // Update display if in editable cell - show "label (ID)" format
    var cell = ontologyModalInput.closest('.editable-cell');
    if (cell) {
        var display = cell.querySelector('.cell-display');
        if (display) {
            var displayParts = [];
            ontologyModalSelectedValues.forEach(function(label, id) {
                if (label && label !== id) {
                    displayParts.push(label + ' (' + id + ')');
                } else {
                    displayParts.push(id);
                }
            });
            display.textContent = displayParts.join(', ');
        }
    }
}

// Add ontology value to selection
function addOntologySelectedValue(value, label) {
    if (ontologyModalSelectedValues.has(value)) return;

    // Check if multi-select is allowed (default: single select)
    var isMulti = ontologyModalInput && ontologyModalInput.dataset.multi === 'true';
    if (!isMulti) {
        // Single select: clear existing values and auto-close modal
        ontologyModalSelectedValues = new Map();
        ontologyModalSelectedValues.set(value, label);
        updateOntologyInput();
        closeOntologyModal();
        return;
    }

    ontologyModalSelectedValues.set(value, label);
    renderOntologySelectedItems();
    updateOntologyInput();
    // Re-render results
    var searchInput = document.getElementById('ontology-modal-search');
    if (searchInput && searchInput.value.length >= 2) {
        loadOntologyModalResults(searchInput.value);
    }
}

// Remove ontology value from selection
function removeOntologySelectedValue(value) {
    ontologyModalSelectedValues.delete(value); // Map.delete works the same as Set.delete
    renderOntologySelectedItems();
    updateOntologyInput();
    // Re-render results
    var searchInput = document.getElementById('ontology-modal-search');
    if (searchInput && searchInput.value.length >= 2) {
        loadOntologyModalResults(searchInput.value);
    }
}

// Load ontology results into modal
function loadOntologyModalResults(query) {
    var resultsDiv = document.getElementById('ontology-modal-results');

    var url = '/api/ontology/search?q=' + encodeURIComponent(query);
    if (ontologyModalOntologies) {
        url += '&ontology=' + encodeURIComponent(ontologyModalOntologies);
    }
    if (ontologyModalWithin) {
        url += '&within=' + encodeURIComponent(ontologyModalWithin);
    }

    resultsDiv.innerHTML = '<div class="lookup-modal-loading">Searching OLS4...</div>';

    fetch(url)
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            if (!data.results || data.results.length === 0) {
                resultsDiv.innerHTML = '<div class="lookup-modal-empty">No terms found</div>';
                return;
            }

            resultsDiv.innerHTML = '';
            data.results.forEach(function(result) {
                var item = document.createElement('div');
                item.className = 'lookup-modal-item ontology-modal-item';
                item.dataset.value = result.value;

                var isSelected = ontologyModalSelectedValues.has(result.value);

                var html = '<div class="ontology-modal-item-info">' +
                    '<div class="ontology-modal-item-header">' +
                    '<span class="ontology-term-id">' + escapeHtml(result.value) + '</span>' +
                    '<span class="ontology-term-label">' + escapeHtml(result.label) + '</span>' +
                    '</div>';

                if (result.ontology || result.description) {
                    html += '<div class="ontology-modal-item-meta">';
                    if (result.ontology) {
                        html += '<span class="ontology-source-badge">' + escapeHtml(result.ontology) + '</span>';
                    }
                    if (result.description) {
                        var desc = result.description.length > 120
                            ? result.description.substring(0, 120) + '...'
                            : result.description;
                        html += '<span class="ontology-description">' + escapeHtml(desc) + '</span>';
                    }
                    html += '</div>';
                }

                html += '</div>' +
                    '<button type="button" class="lookup-modal-item-add' + (isSelected ? ' hidden' : '') + '" title="Add">+</button>';

                item.innerHTML = html;

                var addBtn = item.querySelector('.lookup-modal-item-add');
                addBtn.addEventListener('click', function(e) {
                    e.stopPropagation();
                    addOntologySelectedValue(result.value, result.label);
                });

                resultsDiv.appendChild(item);
            });
        })
        .catch(function(error) {
            console.error('Ontology modal error:', error);
            resultsDiv.innerHTML = '<div class="lookup-modal-error">Error searching ontology</div>';
        });
}
