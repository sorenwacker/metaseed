/**
 * Inline ontology term autocomplete.
 *
 * Reusable dropdown suggestion widget for ontology term inputs, shipped by
 * metaseed for apps that mount its static directory. metaseed's own UI uses
 * the modal-based lookup in lookup.js and does not load this file;
 * metaseed-hub attaches it to its `[data-ontology-autocomplete]` inputs.
 *
 * Usage: OntologyAutocomplete.create(config);
 * create() scans the document for matching inputs on DOMContentLoaded and
 * re-attaches after every htmx:afterSwap. The returned object exposes
 * {init, attachAutocomplete} for manual wiring.
 *
 * Config contract - required:
 *   suggestUrl(query, input): string
 *       Returns the suggestions endpoint URL for a query. The input element
 *       is passed so per-input data attributes (e.g. data-ontologies, a
 *       comma-separated ontology filter) can shape the URL. The endpoint
 *       must return JSON {suggestions: [{id, label, ontology}]}.
 *
 * Config contract - optional:
 *   selector: string
 *       CSS selector for inputs to enhance. Default
 *       '[data-ontology-autocomplete]'.
 *   minQueryLength: number  Minimum characters before querying. Default 2.
 *   debounceMs: number      Input debounce in milliseconds. Default 300.
 *   onSelect(input, suggestion): void
 *       Applies a chosen suggestion {id, label, ontology} to the input.
 *       Default sets input.value to 'label (id)' and dispatches a bubbling
 *       'change' event.
 *
 * DOM/CSS contract: the widget wraps each input in
 * '.ontology-autocomplete-wrapper' and renders suggestions into an
 * '.ontology-autocomplete-dropdown' with '.ontology-option',
 * '.ontology-option-label', '.ontology-option-id', '.ontology-option-source',
 * and '.ontology-no-results' elements; the consumer styles these classes.
 */

const OntologyAutocomplete = (function() {
    'use strict';

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function create(config) {
        const selector = config.selector || '[data-ontology-autocomplete]';
        const minQueryLength = config.minQueryLength || 2;
        const debounceMs = config.debounceMs || 300;
        let activeRequest = null;
        let debounceTimer = null;

        function init() {
            document.querySelectorAll(selector).forEach(attachAutocomplete);

            // Re-attach after HTMX swaps
            document.body.addEventListener('htmx:afterSwap', function(e) {
                e.detail.elt.querySelectorAll(selector).forEach(attachAutocomplete);
            });
        }

        function attachAutocomplete(input) {
            if (input.dataset.autocompleteAttached) return;
            input.dataset.autocompleteAttached = 'true';

            const wrapper = document.createElement('div');
            wrapper.className = 'ontology-autocomplete-wrapper';
            wrapper.style.position = 'relative';
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);

            const dropdown = document.createElement('div');
            dropdown.className = 'ontology-autocomplete-dropdown hidden';
            wrapper.appendChild(dropdown);

            input.addEventListener('input', function() {
                handleInput(input, dropdown);
            });

            input.addEventListener('keydown', function(e) {
                handleKeydown(e, input, dropdown);
            });

            input.addEventListener('blur', function() {
                setTimeout(function() { hideDropdown(dropdown); }, 200);
            });

            dropdown.addEventListener('mousedown', function(e) {
                const option = e.target.closest('.ontology-option');
                if (option) {
                    selectOption(input, dropdown, option);
                }
            });
        }

        function handleInput(input, dropdown) {
            const query = input.value.trim();

            if (debounceTimer) clearTimeout(debounceTimer);
            if (activeRequest) activeRequest.abort();

            if (query.length < minQueryLength) {
                hideDropdown(dropdown);
                return;
            }

            debounceTimer = setTimeout(function() {
                fetchSuggestions(query, input, dropdown);
            }, debounceMs);
        }

        function fetchSuggestions(query, input, dropdown) {
            const controller = new AbortController();
            activeRequest = controller;

            fetch(config.suggestUrl(query, input), { signal: controller.signal })
                .then(function(response) {
                    if (!response.ok) throw new Error('Suggestion request failed');
                    return response.json();
                })
                .then(function(data) {
                    renderDropdown(data, dropdown);
                })
                .catch(function(err) {
                    if (err.name !== 'AbortError') {
                        console.error('Ontology autocomplete error:', err);
                        hideDropdown(dropdown);
                    }
                })
                .finally(function() {
                    activeRequest = null;
                });
        }

        function renderDropdown(data, dropdown) {
            const suggestions = data.suggestions || [];

            if (suggestions.length === 0) {
                dropdown.innerHTML = '<div class="ontology-no-results">No matching terms found</div>';
                showDropdown(dropdown);
                return;
            }

            dropdown.innerHTML = suggestions.map(function(s, idx) {
                const label = escapeHtml(s.label || 'Unknown');
                const id = escapeHtml(s.id || '');
                const ontology = escapeHtml(s.ontology || '');
                return '<div class="ontology-option" data-value="' + id + '" data-index="' + idx + '">' +
                       '<span class="ontology-option-label">' + label + '</span>' +
                       '<span class="ontology-option-id">' + id + '</span>' +
                       '<span class="ontology-option-source">' + ontology + '</span>' +
                       '</div>';
            }).join('');
            showDropdown(dropdown);
        }

        function handleKeydown(e, input, dropdown) {
            const options = dropdown.querySelectorAll('.ontology-option');
            const current = dropdown.querySelector('.ontology-option.highlighted');
            const currentIdx = current ? parseInt(current.dataset.index) : -1;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                highlightOption(options, Math.min(currentIdx + 1, options.length - 1));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                highlightOption(options, Math.max(currentIdx - 1, 0));
            } else if (e.key === 'Enter' && current) {
                e.preventDefault();
                selectOption(input, dropdown, current);
            } else if (e.key === 'Escape') {
                hideDropdown(dropdown);
            }
        }

        function highlightOption(options, idx) {
            options.forEach(function(opt) { opt.classList.remove('highlighted'); });
            if (options[idx]) {
                options[idx].classList.add('highlighted');
                options[idx].scrollIntoView({ block: 'nearest' });
            }
        }

        function selectOption(input, dropdown, option) {
            const suggestion = {
                id: option.dataset.value,
                label: option.querySelector('.ontology-option-label')?.textContent || '',
                ontology: option.querySelector('.ontology-option-source')?.textContent || ''
            };

            if (config.onSelect) {
                config.onSelect(input, suggestion);
            } else {
                // Store as "label (ID)" for readability, keeping the ID
                // extractable.
                input.value = suggestion.label
                    ? suggestion.label + ' (' + suggestion.id + ')'
                    : suggestion.id;
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
            hideDropdown(dropdown);
        }

        function showDropdown(dropdown) {
            dropdown.classList.remove('hidden');
        }

        function hideDropdown(dropdown) {
            dropdown.classList.add('hidden');
        }

        document.addEventListener('DOMContentLoaded', init);
        if (document.readyState !== 'loading') {
            setTimeout(init, 50);
        }

        return { init: init, attachAutocomplete: attachAutocomplete };
    }

    return { create };
})();
