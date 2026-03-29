// MIAPPE-API JavaScript

// Handle collapsible sections
document.addEventListener('click', function(e) {
    var header = e.target.closest('.collapsible-header');
    if (header) {
        var collapsible = header.closest('.collapsible');
        collapsible.classList.toggle('open');
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
document.body.addEventListener('refreshPage', function() {
    window.location.reload();
});

// Reset file input after upload (to allow re-uploading same file)
document.addEventListener('htmx:afterRequest', function(e) {
    if (e.target.type === 'file') {
        e.target.value = '';
    }
});
