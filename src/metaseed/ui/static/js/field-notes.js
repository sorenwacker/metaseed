/**
 * Field notes: the box a form label or table heading with a data-note opens.
 *
 * Drawn here, not as a native title: the browser delays a title tooltip and
 * shows none in an unfocused window, so the notes looked absent. One fixed box
 * serves every element and sits on the body so a scrolling panel cannot clip
 * it. The note is plain text from heading_note: a description paragraph, then
 * "Label: value" lines, laid out as rows. The box stays open while the pointer
 * is on it, so a long note can be scrolled. metaseed-hub loads this file too.
 */
(function () {
    let box = null;
    let anchor = null;
    let hideTimer = null;

    function renderNote(note) {
        const fragment = document.createDocumentFragment();
        const [description, ...rest] = note.split('\n\n');
        const lead = document.createElement('p');
        lead.className = 'note-tooltip-description';
        lead.textContent = description;
        fragment.appendChild(lead);
        const rows = rest.join('\n').split('\n').filter(Boolean);
        if (!rows.length) return fragment;
        const list = document.createElement('dl');
        for (const row of rows) {
            const split = row.indexOf(': ');
            const term = document.createElement('dt');
            const detail = document.createElement('dd');
            if (split < 0) {
                term.textContent = 'Field';
                detail.textContent = row;
            } else {
                term.textContent = row.slice(0, split);
                const value = row.slice(split + 2);
                if (term.textContent === 'Allowed values') {
                    for (const choice of value.split(', ')) {
                        const chip = document.createElement('span');
                        chip.className = 'note-tooltip-chip';
                        chip.textContent = choice;
                        detail.appendChild(chip);
                    }
                } else if (term.textContent === 'Rules') {
                    const items = document.createElement('ul');
                    for (const rule of value.split('; ')) {
                        const item = document.createElement('li');
                        item.textContent = rule;
                        items.appendChild(item);
                    }
                    detail.appendChild(items);
                } else {
                    detail.textContent = value;
                }
            }
            list.append(term, detail);
        }
        fragment.appendChild(list);
        return fragment;
    }

    function hide() {
        clearTimeout(hideTimer);
        if (box) box.hidden = true;
        anchor = null;
    }

    function hideSoon() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(hide, 150);
    }

    function show(target) {
        clearTimeout(hideTimer);
        if (!box) {
            box = document.createElement('div');
            box.className = 'note-tooltip';
            box.setAttribute('role', 'tooltip');
            box.addEventListener('mouseenter', () => clearTimeout(hideTimer));
            box.addEventListener('mouseleave', hideSoon);
            document.body.appendChild(box);
        }
        if (anchor === target && !box.hidden) return;
        anchor = target;
        box.replaceChildren(renderNote(target.dataset.note));
        box.hidden = false;
        box.scrollTop = 0;
        const rect = target.getBoundingClientRect();
        box.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - box.offsetWidth - 8))}px`;
        const below = rect.bottom + 4;
        box.style.top = below + box.offsetHeight > window.innerHeight
            ? `${Math.max(8, rect.top - box.offsetHeight - 4)}px`
            : `${below}px`;
    }

    document.addEventListener('mouseover', event => {
        const target = event.target.closest && event.target.closest('[data-note]');
        if (target) show(target);
    });
    document.addEventListener('mouseout', event => {
        const from = event.target.closest && event.target.closest('[data-note]');
        if (from && !from.contains(event.relatedTarget)) hideSoon();
    });
    document.addEventListener('scroll', event => {
        if (box && !box.contains(event.target)) hide();
    }, true);
    document.addEventListener('mousedown', event => {
        if (box && !box.contains(event.target)) hide();
    });
    document.addEventListener('htmx:beforeSwap', hide);
})();
