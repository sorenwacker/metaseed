// Metaseed Excel-style Bulk Editing

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
        fetch(BASE_URL + '/table/' + parentType + '/' + fieldName + '/paste', {
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
});
