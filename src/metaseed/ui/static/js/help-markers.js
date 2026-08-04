/**
 * Turn every `title` in the builder into a visible, focusable help marker.
 *
 * A native tooltip is invisible until hovered for about a second, never appears
 * on touch, and does not render at all on some machines -- so the guidance a
 * specification carries would not reach the person filling it in. The marker is
 * a small "?" beside the label, which also advertises that help exists.
 *
 * The bubble is attached to <body> rather than the marker: every panel in the
 * builder clips its overflow, which cut a tooltip off at the edge of the section
 * it belonged to.
 *
 * Runs over the whole page and again after each htmx swap, so a partial loaded
 * later (the entity editor, a field form) is covered without knowing about this.
 */
(function () {
    'use strict';

    var BUBBLE_ID = 'help-bubble';
    var EDGE = 8;

    function bubble() {
        var el = document.getElementById(BUBBLE_ID);
        if (!el) {
            el = document.createElement('div');
            el.id = BUBBLE_ID;
            el.className = 'help-bubble';
            document.body.appendChild(el);
        }
        return el;
    }

    function show(marker) {
        var el = bubble();
        el.textContent = marker.getAttribute('data-help');
        el.classList.add('visible');

        var m = marker.getBoundingClientRect();
        // Measured after the text is set, so the width used to centre it and to
        // keep it on screen is the width it will actually have.
        var b = el.getBoundingClientRect();
        var left = Math.min(
            Math.max(EDGE, m.left + m.width / 2 - b.width / 2),
            window.innerWidth - b.width - EDGE
        );
        var above = m.top - b.height - EDGE;
        el.style.left = left + 'px';
        el.style.top = (above >= EDGE ? above : m.bottom + EDGE) + 'px';
    }

    function hide() {
        var el = document.getElementById(BUBBLE_ID);
        if (el) el.classList.remove('visible');
    }

    function addMarkers(root) {
        if (!root || !root.querySelectorAll) return;
        root.querySelectorAll('[title]').forEach(function (el) {
            var text = el.getAttribute('title');
            if (!text || el.querySelector('.help-marker')) return;
            // A control with its own behaviour on hover (a button, a link) keeps
            // its native title: appending a focusable child inside it would sit
            // in the way of the thing it labels.
            if (el.matches('button, a, input, select, textarea, option')) return;

            // Removed so a browser that does render native tooltips does not
            // show a second copy alongside this one.
            el.removeAttribute('title');

            var marker = document.createElement('span');
            marker.className = 'help-marker';
            marker.setAttribute('data-help', text);
            marker.setAttribute('tabindex', '0');
            marker.setAttribute('role', 'note');
            marker.setAttribute('aria-label', text);
            marker.textContent = '?';
            marker.addEventListener('mouseenter', function () { show(marker); });
            marker.addEventListener('focus', function () { show(marker); });
            marker.addEventListener('mouseleave', hide);
            marker.addEventListener('blur', hide);
            el.appendChild(marker);
        });
    }

    function start() {
        addMarkers(document.body);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }

    document.body.addEventListener('htmx:afterSwap', function (e) {
        addMarkers(e.target);
        hide();
    });

    window.addHelpMarkers = addMarkers;
})();
