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
    var entityType = input.dataset.lookup;
    var query = input.value;

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
    var entityType = input.dataset.lookup;
    var query = input.value;

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
        openLookupModal(entityType, inputId);
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

// Fetch suggestions from API
function fetchLookupSuggestions(input, entityType, query) {
    fetch('/api/lookup/' + encodeURIComponent(entityType) + '?q=' + encodeURIComponent(query))
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
function selectLookupValue(input, value) {
    input.value = value;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    hideAutocomplete();

    // Update display if in editable cell
    var cell = input.closest('.editable-cell');
    if (cell) {
        var display = cell.querySelector('.cell-display');
        if (display) {
            display.textContent = value;
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
var lookupModalSelectedValues = new Set();

// Open lookup modal
function openLookupModal(entityType, inputId) {
    var input = document.querySelector('[data-testid="' + inputId + '"]');
    if (!input) return;

    lookupModalInput = input;
    lookupModalEntityType = entityType;
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

    fetch('/api/lookup/' + encodeURIComponent(entityType) + '?q=' + encodeURIComponent(query))
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
});

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        var modal = document.getElementById('lookup-modal');
        if (modal && !modal.classList.contains('hidden')) {
            closeLookupModal();
        }
    }
});
