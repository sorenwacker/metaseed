/**
 * Spec Builder - metaseed app wiring.
 *
 * Instantiates the shared ERD core (spec-builder-core.js) with metaseed's
 * endpoints and the template-inlined globals, and publishes the returned API
 * as globals for the inline handlers in templates/spec_builder/. The graph
 * logic itself lives in spec-builder-core.js; only metaseed-specific wiring
 * (URL prefix, entity source, sidebar layout) belongs here.
 *
 * Template contract: base.html inlines `const entities` (live entity map),
 * `let rootEntity`, and loads erd-common.js and spec-builder-core.js before
 * this file.
 */

const specBuilder = SpecBuilderGraph.create({
    getEntities: function() { return entities; },
    rootEntity: function() { return rootEntity; },
    // Navigates to /spec-builder when called with '' (not /new, which resets
    // state).
    url: function(path) { return '/spec-builder' + path; },
    afterSidebarTabSwitch: function(tabName) {
        // Widen sidebar for the notes tab, then refit the graph.
        const sidebar = document.querySelector('.erd-sidebar');
        if (sidebar) {
            sidebar.classList.toggle('notes-active', tabName === 'notes');
        }
        setTimeout(() => {
            const network = specBuilder.getNetwork();
            if (network) {
                network.fit();
            }
        }, 250);
    }
});

// Expose the core API as globals for inline template handlers and tests.
// autoLayout/zoomIn/zoomOut/fitGraph come from erd-common.js.
Object.assign(window, specBuilder);

// =============================================================================
// Sidebar Toggle (metaseed layout)
// =============================================================================

function toggleSidebar() {
    const sidebar = document.querySelector('.erd-sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle-btn');
    sidebar.classList.toggle('collapsed');
    if (sidebar.classList.contains('collapsed')) {
        toggleBtn.textContent = 'Show Sidebar';
        toggleBtn.title = 'Show sidebar (Ctrl+B)';
    } else {
        toggleBtn.textContent = 'Hide Sidebar';
        toggleBtn.title = 'Hide sidebar (Ctrl+B)';
    }
    // Resize the graph to fit new space after animation
    setTimeout(() => {
        const network = specBuilder.getNetwork();
        if (network) {
            network.fit();
        }
    }, 300);
}

// Ctrl+B toggles the sidebar (Escape handling is wired by the core).
document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
    }
});
