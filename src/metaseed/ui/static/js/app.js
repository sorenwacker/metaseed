// Metaseed JavaScript

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

// Unified validation based on data-type and constraint attributes
function validateInput(input) {
    var value = input.value;
    var dataType = input.getAttribute('data-type') || 'string';
    var isValid = true;
    var errorMsg = '';

    // Empty values are valid (required check is separate)
    if (!value) {
        input.classList.remove('invalid');
        input.removeAttribute('title');
        return true;
    }

    // Type-based validation
    switch (dataType) {
        case 'integer':
            if (!/^-?\d+$/.test(value)) {
                isValid = false;
                errorMsg = 'Must be a whole number';
            }
            break;
        case 'float':
            if (!/^-?\d*\.?\d+$/.test(value)) {
                isValid = false;
                errorMsg = 'Must be a number';
            }
            break;
        case 'date':
            if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
                isValid = false;
                errorMsg = 'Date format: YYYY-MM-DD';
            }
            break;
        case 'uri':
            try {
                new URL(value);
            } catch (_) {
                isValid = false;
                errorMsg = 'Must be a valid URL';
            }
            break;
    }

    // Constraint-based validation (only if type validation passed)
    if (isValid) {
        // Min/max for numbers
        var min = input.getAttribute('data-min');
        var max = input.getAttribute('data-max');
        if (min !== null && (dataType === 'integer' || dataType === 'float')) {
            var num = parseFloat(value);
            if (num < parseFloat(min)) {
                isValid = false;
                errorMsg = 'Minimum value: ' + min;
            }
        }
        if (max !== null && (dataType === 'integer' || dataType === 'float')) {
            var num = parseFloat(value);
            if (num > parseFloat(max)) {
                isValid = false;
                errorMsg = 'Maximum value: ' + max;
            }
        }

        // Min/max length for strings
        var minLen = input.getAttribute('data-minlength');
        var maxLen = input.getAttribute('data-maxlength');
        if (minLen !== null && value.length < parseInt(minLen)) {
            isValid = false;
            errorMsg = 'Minimum length: ' + minLen;
        }
        if (maxLen !== null && value.length > parseInt(maxLen)) {
            isValid = false;
            errorMsg = 'Maximum length: ' + maxLen;
        }

        // Pattern validation (HTML5 pattern attribute)
        var pattern = input.getAttribute('pattern');
        if (pattern && !new RegExp('^' + pattern + '$').test(value)) {
            isValid = false;
            errorMsg = input.getAttribute('title') || 'Invalid format';
        }
    }

    // Update visual state
    if (isValid) {
        input.classList.remove('invalid');
        input.removeAttribute('title');
    } else {
        input.classList.add('invalid');
        if (errorMsg) {
            input.setAttribute('title', errorMsg);
        }
    }

    return isValid;
}

// Validate all form inputs on change
document.addEventListener('input', function(e) {
    if (e.target.classList.contains('form-input')) {
        validateInput(e.target);
    }
});

// Validate all inputs after HTMX swap (for newly added rows)
document.addEventListener('htmx:afterSwap', function(e) {
    var inputs = e.target.querySelectorAll('.form-input');
    inputs.forEach(function(input) {
        if (input.value) {
            validateInput(input);
        }
    });
});

// Handle page refresh trigger (e.g., after import)
// HTMX triggers events via htmx:trigger on the requesting element
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

// ============================================
// Excel-style Bulk Editing
// ============================================

// Track the currently active cell
var activeCell = null;
var originalValue = null;

// Click-to-edit cells
document.addEventListener('click', function(e) {
    var cell = e.target.closest('.editable-cell');
    if (cell && !e.target.classList.contains('cell-input')) {
        activateCell(cell);
    }
});

function activateCell(cell) {
    // Deactivate previous cell if any
    if (activeCell && activeCell !== cell) {
        deactivateCell(activeCell);
    }

    var input = cell.querySelector('.cell-input');
    var display = cell.querySelector('.cell-display');

    if (input && display) {
        originalValue = input.value;
        cell.classList.add('editing');
        display.style.display = 'none';
        input.style.display = 'block';
        input.focus();
        input.select();
        activeCell = cell;
    }
}

function deactivateCell(cell, revert) {
    var input = cell.querySelector('.cell-input');
    var display = cell.querySelector('.cell-display');

    if (input && display) {
        if (revert && originalValue !== null) {
            input.value = originalValue;
        }
        display.textContent = input.value;
        cell.classList.remove('editing');
        display.style.display = 'block';
        input.style.display = 'none';

        // Trigger change event if value changed
        if (!revert && input.value !== originalValue) {
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    if (activeCell === cell) {
        activeCell = null;
        originalValue = null;
    }
}

// Handle blur to deactivate cell
document.addEventListener('focusout', function(e) {
    if (e.target.classList.contains('cell-input')) {
        var cell = e.target.closest('.editable-cell');
        // Use setTimeout to allow click events to fire first
        setTimeout(function() {
            if (cell && activeCell === cell) {
                deactivateCell(cell, false);
            }
        }, 100);
    }
});

// Keyboard navigation
document.addEventListener('keydown', function(e) {
    if (!activeCell) return;

    var input = activeCell.querySelector('.cell-input');
    if (!input || document.activeElement !== input) return;

    var row = activeCell.closest('tr');
    var colIndex = Array.from(row.querySelectorAll('.editable-cell')).indexOf(activeCell);
    var rows = Array.from(document.querySelectorAll('#table-body tr'));
    var rowIndex = rows.indexOf(row);

    var targetCell = null;
    var handled = false;

    switch (e.key) {
        case 'Tab':
            e.preventDefault();
            handled = true;
            if (e.shiftKey) {
                // Move left
                targetCell = getCell(rows, rowIndex, colIndex - 1);
                if (!targetCell && rowIndex > 0) {
                    var prevRow = rows[rowIndex - 1];
                    var cells = prevRow.querySelectorAll('.editable-cell');
                    targetCell = cells[cells.length - 1];
                }
            } else {
                // Move right
                targetCell = getCell(rows, rowIndex, colIndex + 1);
                if (!targetCell && rowIndex < rows.length - 1) {
                    targetCell = getCell(rows, rowIndex + 1, 0);
                }
            }
            break;

        case 'Enter':
            e.preventDefault();
            handled = true;
            if (e.shiftKey) {
                // Move up
                targetCell = getCell(rows, rowIndex - 1, colIndex);
            } else {
                // Move down
                targetCell = getCell(rows, rowIndex + 1, colIndex);
            }
            break;

        case 'ArrowUp':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                handled = true;
                targetCell = getCell(rows, rowIndex - 1, colIndex);
            }
            break;

        case 'ArrowDown':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                handled = true;
                targetCell = getCell(rows, rowIndex + 1, colIndex);
            }
            break;

        case 'ArrowLeft':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                handled = true;
                targetCell = getCell(rows, rowIndex, colIndex - 1);
            }
            break;

        case 'ArrowRight':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                handled = true;
                targetCell = getCell(rows, rowIndex, colIndex + 1);
            }
            break;

        case 'Escape':
            e.preventDefault();
            handled = true;
            deactivateCell(activeCell, true);
            break;
    }

    if (targetCell && handled) {
        deactivateCell(activeCell, false);
        activateCell(targetCell);
    }
});

function getCell(rows, rowIndex, colIndex) {
    if (rowIndex < 0 || rowIndex >= rows.length) return null;
    var cells = rows[rowIndex].querySelectorAll('.editable-cell');
    if (colIndex < 0 || colIndex >= cells.length) return null;
    return cells[colIndex];
}

// Row selection handling
document.addEventListener('change', function(e) {
    if (e.target.id === 'select-all') {
        var checked = e.target.checked;
        document.querySelectorAll('.row-select').forEach(function(checkbox) {
            checkbox.checked = checked;
            checkbox.closest('tr').classList.toggle('selected', checked);
        });
        updateBulkToolbar();
    } else if (e.target.classList.contains('row-select')) {
        e.target.closest('tr').classList.toggle('selected', e.target.checked);
        updateSelectAllState();
        updateBulkToolbar();
    }
});

function updateSelectAllState() {
    var selectAll = document.getElementById('select-all');
    if (!selectAll) return;

    var checkboxes = document.querySelectorAll('.row-select');
    var checked = document.querySelectorAll('.row-select:checked');

    if (checked.length === 0) {
        selectAll.checked = false;
        selectAll.indeterminate = false;
    } else if (checked.length === checkboxes.length) {
        selectAll.checked = true;
        selectAll.indeterminate = false;
    } else {
        selectAll.checked = false;
        selectAll.indeterminate = true;
    }
}

function updateBulkToolbar() {
    var toolbar = document.getElementById('bulk-edit-toolbar');
    if (!toolbar) return;

    var selected = document.querySelectorAll('.row-select:checked');
    var countSpan = document.getElementById('selected-count');
    var indicesInput = document.getElementById('bulk-edit-indices');

    if (selected.length > 0) {
        toolbar.classList.remove('hidden');
        if (countSpan) countSpan.textContent = selected.length;

        // Update indices
        var indices = Array.from(selected).map(function(cb) {
            return cb.getAttribute('data-idx');
        });
        if (indicesInput) indicesInput.value = indices.join(',');
    } else {
        toolbar.classList.add('hidden');
    }
}

// Bulk edit cancel button
document.addEventListener('click', function(e) {
    if (e.target.id === 'bulk-cancel-btn') {
        // Uncheck all
        document.querySelectorAll('.row-select:checked').forEach(function(cb) {
            cb.checked = false;
            cb.closest('tr').classList.remove('selected');
        });
        var selectAll = document.getElementById('select-all');
        if (selectAll) {
            selectAll.checked = false;
            selectAll.indeterminate = false;
        }
        updateBulkToolbar();
    }
});

// Paste handling
document.addEventListener('paste', function(e) {
    if (!activeCell) return;

    var input = activeCell.querySelector('.cell-input');
    if (!input || document.activeElement !== input) return;

    var clipboardData = e.clipboardData || window.clipboardData;
    var pastedText = clipboardData.getData('text');

    // Check if it looks like tab-separated data (Excel format)
    if (pastedText.includes('\t') || (pastedText.includes('\n') && pastedText.trim().split('\n').length > 1)) {
        e.preventDefault();
        handlePaste(pastedText);
    }
    // Otherwise let the default paste behavior happen
});

function handlePaste(text) {
    var table = document.getElementById('data-table');
    if (!table) return;

    var parentType = table.getAttribute('data-parent-type');
    var fieldName = table.getAttribute('data-field-name');

    var rows = text.trim().split('\n');
    var changes = [];

    var startRow = activeCell.closest('tr');
    var startRowIndex = parseInt(startRow.getAttribute('data-idx'));
    var cells = Array.from(startRow.querySelectorAll('.editable-cell'));
    var startColIndex = cells.indexOf(activeCell);
    var columns = cells.map(function(c) { return c.getAttribute('data-col'); });

    var allRows = Array.from(document.querySelectorAll('#table-body tr'));
    var rowOffset = allRows.indexOf(startRow);

    rows.forEach(function(rowText, ri) {
        var values = rowText.split('\t');
        var targetRowIndex = rowOffset + ri;

        if (targetRowIndex >= allRows.length) return;

        var targetRow = allRows[targetRowIndex];
        var idx = parseInt(targetRow.getAttribute('data-idx'));

        values.forEach(function(value, ci) {
            var targetColIndex = startColIndex + ci;
            if (targetColIndex >= columns.length) return;

            var colName = columns[targetColIndex];
            var cell = targetRow.querySelector('.editable-cell[data-col="' + colName + '"]');

            if (cell) {
                var cellInput = cell.querySelector('.cell-input');
                var cellDisplay = cell.querySelector('.cell-display');
                if (cellInput) {
                    cellInput.value = value;
                    if (cellDisplay) cellDisplay.textContent = value;
                }
                changes.push({idx: idx, field: colName, value: value});
            }
        });
    });

    // Send paste data to server
    if (changes.length > 0) {
        fetch('/table/' + parentType + '/' + fieldName + '/paste', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: 'changes=' + encodeURIComponent(JSON.stringify(changes))
        }).then(function(response) {
            if (response.ok) {
                // Show success notification
                htmx.trigger(document.body, 'showNotification', {
                    type: 'success',
                    message: 'Pasted ' + changes.length + ' cells'
                });
            }
        });
    }

    deactivateCell(activeCell, false);
}

// Initialize cells after HTMX swap
document.addEventListener('htmx:afterSwap', function(e) {
    // Re-initialize selection state
    updateSelectAllState();
    updateBulkToolbar();

    // Initialize lookup inputs
    initLookupInputs(e.target);
});

// ============================================
// Cross-Entity Lookup (Autocomplete + Modal)
// ============================================

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
