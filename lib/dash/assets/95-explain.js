/*
 * Explain — ask Gemini what something on the dashboard means
 * (server side: lib/dash/explain_route.py). Two ways in:
 *
 * 1. Smart help per panel. Every panel header (sidebar sections and the
 *    accordion cards: Chart Settings, Execution Type, Trade Setup, Signals…)
 *    gets a ✦ button. First click arms that panel: dashed outline, help cursor,
 *    a hint, and whatever is under the pointer lights up. Second click, on
 *    anything inside the panel, asks Gemini about it — and does nothing else:
 *    the click is swallowed, so no box gets ticked and no button pressed.
 *    Esc, the ✦ again, or a click outside the panel cancels.
 * 2. Select text (a number, a word) and press the small "Explain" button.
 *
 * Asks /api/session once. Nothing is wired unless the answer says
 * explain: true — an admin with GEMINI_API_KEY set — so the demo and
 * non-admin users see none of it. The same answer fills the header's account
 * slot on the hosted site (email, Users for an admin, Sign out).
 *
 * Panel buttons are added from here, not from the Python layout, so they exist
 * only for admins; a MutationObserver adds them to panels that mount later.
 * Answers are inserted with textContent, never as HTML.
 */
(function () {
    'use strict';

    var MAX_SELECTION = 300;
    var MAX_CONTEXT = 600;
    var PANELS = 'details.bbg-section, .accordion-item';
    var HEADERS = 'summary.bbg-section-header, .accordion-header';
    var TARGETS = 'label, button, a, input, select, textarea, td, th, h1, h2, h3, h4, h5, h6, ' +
        '.dash-dropdown, .Select, .rc-slider, .accordion-title-row, .card, [title], [aria-label]';

    var button = null;      // the floating "Explain" for text selections
    var popover = null;
    var hint = null;
    var pending = null;     // {text, context, rect}
    var picking = null;     // {panel, title, icon, hovered}

    function clip(text, limit) {
        var value = (text || '').replace(/\s+/g, ' ').trim();
        return value.length <= limit ? value : value.slice(0, limit - 1) + '…';
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function nearestElement(node) {
        while (node && node.nodeType !== 1) node = node.parentNode;
        return node;
    }

    function swallow(e) {
        e.preventDefault();
        e.stopPropagation();
        if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    }

    // ------------------------------------------------------------ account --
    function fillAccount(info) {
        if (!info || info.mode !== 'hosted' || !info.email) return;
        var tries = 0;
        (function attempt() {
            var slot = document.getElementById('sfa-account-slot');
            if (!slot) {
                if (tries++ < 40) setTimeout(attempt, 250);  // the layout mounts after this script
                return;
            }
            slot.textContent = '';
            slot.appendChild(el('span', 'sfa-account-email', info.email));
            if (info.admin) {
                var users = el('a', 'bbg-icon-button sfa-account-link', 'Users');
                users.href = '/admin/users';
                users.title = 'Manage the whitelist';
                slot.appendChild(users);
            }
            var out = el('a', 'bbg-icon-button sfa-account-link', 'Sign out');
            out.href = '/logout';
            slot.appendChild(out);
        })();
    }

    // ------------------------------------------------------------ context --
    function tableContext(cell) {
        var parts = [];
        var column = cell.getAttribute('data-dash-column');  // dash DataTable
        var table = cell.closest('table');
        if (table && cell.cellIndex >= 0) {
            var head = table.querySelector('thead tr:last-child') || table.querySelector('tr');
            var th = head && head.cells[cell.cellIndex];
            if (th && th !== cell) parts.push('column "' + clip(th.textContent, 60) + '"');
        }
        if (column) parts.push('column id "' + column + '"');
        var row = cell.parentElement;
        if (row && row.cells && row.cells.length && row.cells[0] !== cell) {
            parts.push('row "' + clip(row.cells[0].textContent, 60) + '"');
        }
        return parts.join(', ');
    }

    // Walk up from `start` collecting labels/tooltips, then the first ancestor
    // whose text says more than `own` (a label + value pair, a card, a row).
    function surroundings(start, own, stopAt) {
        var bits = [];
        var cell = start.closest('td, th');
        if (cell) bits.push(tableContext(cell));
        var node = start;
        var gotText = false;
        for (var depth = 0; node && depth < 7 && node !== stopAt; depth++, node = node.parentElement) {
            var tip = node.getAttribute && (node.getAttribute('title') || node.getAttribute('aria-label'));
            if (tip && tip !== own) bits.push('tooltip "' + clip(tip, 160) + '"');
            if (!gotText) {
                var text = clip(node.textContent, 400);
                if (text.length > own.length + 3 && !node.matches('body, #react-entry-point, ._dash-app-content')) {
                    bits.push('surrounding text "' + text + '"');
                    gotText = true;
                }
            }
        }
        return bits;
    }

    function selectionContext(range, selected) {
        var start = nearestElement(range.commonAncestorContainer);
        if (!start) return '';
        var bits = surroundings(start, selected, null);
        var panel = start.closest(PANELS);
        if (panel) bits.unshift('panel "' + panelTitle(panel) + '"');
        return clip(bits.filter(Boolean).join('; '), MAX_CONTEXT);
    }

    function currentTicker() {
        var match = location.pathname.match(/^\/(?:ticker|fundamentals|flow|optimize)\/([^/?#]+)/);
        if (match) return decodeURIComponent(match[1]).toUpperCase();
        var label = document.querySelector('#ticker-dropdown .Select-value-label');
        return label ? clip(label.textContent, 20) : '';
    }

    // ------------------------------------------------------------ popover --
    function place(node, rect) {
        var width = node.offsetWidth || 280;
        var left = Math.min(Math.max(8, rect.left), window.innerWidth - width - 8);
        var top = rect.bottom + 6;
        if (top + node.offsetHeight > window.innerHeight - 8) top = Math.max(8, rect.top - node.offsetHeight - 6);
        node.style.left = left + 'px';
        node.style.top = top + 'px';
    }

    function ensurePopover() {
        if (popover) return popover;
        popover = el('div', 'sfa-explain-pop');
        popover.setAttribute('role', 'dialog');
        popover.setAttribute('aria-label', 'Explanation');
        document.body.appendChild(popover);
        return popover;
    }

    function hidePopover() {
        if (popover) popover.style.display = 'none';
    }

    function render(title, body, state) {
        var node = ensurePopover();
        node.textContent = '';
        node.className = 'sfa-explain-pop' + (state ? ' is-' + state : '');
        var head = el('div', 'sfa-explain-head');
        head.appendChild(el('span', 'sfa-explain-title', title));
        var close = el('button', 'sfa-explain-close', '×');
        close.type = 'button';
        close.setAttribute('aria-label', 'Close');
        close.addEventListener('click', hidePopover);
        head.appendChild(close);
        node.appendChild(head);
        node.appendChild(el('div', 'sfa-explain-body', body));
        if (state !== 'loading') node.appendChild(el('div', 'sfa-explain-foot', 'Gemini · may be wrong · not financial advice'));
        node.style.display = 'block';
    }

    function ask(item) {
        var title = clip(item.text, 60);
        render(title, 'Asking Gemini…', 'loading');
        place(popover, item.rect);
        fetch('/api/explain', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-SFA-Explain': '1' },
            body: JSON.stringify({
                selection: item.text,
                context: item.context,
                ticker: currentTicker(),
                page: location.pathname
            })
        }).then(function (response) {
            return response.json().catch(function () { return { ok: false, text: 'HTTP ' + response.status }; });
        }).then(function (data) {
            render(title, (data && data.text) || 'No answer.', data && data.ok ? 'done' : 'error');
            place(popover, item.rect);
        }).catch(function () {
            render(title, 'Network error — is the server still running?', 'error');
        });
    }

    // ---------------------------------------------------- text selection --
    function hideButton() {
        if (button) button.style.display = 'none';
        pending = null;
    }

    function ensureButton() {
        if (button) return button;
        button = el('button', 'sfa-explain-btn', 'Explain');
        button.type = 'button';
        button.title = 'Ask Gemini what this means';
        button.addEventListener('mousedown', function (e) { e.preventDefault(); });  // keep the selection
        button.addEventListener('click', function () {
            if (pending) ask(pending);
            hideButton();
        });
        document.body.appendChild(button);
        return button;
    }

    function onSelection() {
        if (picking) return;
        var selection = window.getSelection();
        if (!selection || selection.isCollapsed || !selection.rangeCount) { hideButton(); return; }
        var text = clip(selection.toString(), MAX_SELECTION + 1);
        if (!text || text.length > MAX_SELECTION) { hideButton(); return; }
        var range = selection.getRangeAt(0);
        var origin = nearestElement(range.commonAncestorContainer);
        if (!origin || origin.closest('input, textarea, [contenteditable="true"], .sfa-explain-pop')) { hideButton(); return; }
        var rect = range.getBoundingClientRect();
        if (!rect || (!rect.width && !rect.height)) { hideButton(); return; }
        pending = { text: text, context: selectionContext(range, text), rect: rect };
        var node = ensureButton();
        node.style.display = 'block';
        place(node, rect);
    }

    // -------------------------------------------------------- panel help --
    function headerOf(panel) {
        for (var i = 0; i < panel.children.length; i++) {
            if (panel.children[i].matches(HEADERS)) return panel.children[i];
        }
        return null;
    }

    // The element holding the panel's name: the first one with its own text.
    function titleNode(header) {
        var all = header.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            var node = all[i];
            if (node.classList.contains('sfa-panel-help')) continue;
            for (var j = 0; j < node.childNodes.length; j++) {
                var child = node.childNodes[j];
                if (child.nodeType === 3 && child.nodeValue.trim() && child.nodeValue.trim() !== '?') return node;
            }
        }
        return null;
    }

    function panelTitle(panel) {
        var header = headerOf(panel);
        var node = header && titleNode(header);
        var text = '';
        if (node) {
            for (var i = 0; i < node.childNodes.length; i++) {
                if (node.childNodes[i].nodeType === 3) text += node.childNodes[i].nodeValue;
            }
        } else if (header) {
            text = header.textContent;
        }
        return clip(text.replace(/[✦?]/g, ''), 40) || 'panel';
    }

    function addPanelButtons() {
        var panels = document.querySelectorAll(PANELS);
        for (var i = 0; i < panels.length; i++) {
            var panel = panels[i];
            if (panel.closest('.modal')) continue;  // the feedback form's accordion is not a panel
            var header = headerOf(panel);
            if (!header || header.querySelector('.sfa-panel-help')) continue;
            var host = titleNode(header);
            if (!host) continue;
            var icon = el('span', 'sfa-panel-help', '✦');
            icon.setAttribute('role', 'button');
            icon.setAttribute('tabindex', '0');
            icon.setAttribute('aria-label', 'Smart help for this panel');
            icon.title = 'Smart help: click here, then click anything in this panel to have it explained';
            host.appendChild(icon);
        }
    }

    function showHint(panel, title) {
        if (!hint) {
            hint = el('div', 'sfa-help-hint');
            document.body.appendChild(hint);
        }
        hint.textContent = '';
        hint.appendChild(el('strong', null, '✦ ' + title));
        hint.appendChild(document.createTextNode(' — click anything in this panel to explain it · Esc to cancel'));
        hint.style.display = 'block';
        var rect = panel.getBoundingClientRect();
        var top = rect.top - hint.offsetHeight - 6;
        hint.style.top = Math.max(6, top < 6 ? rect.top + 6 : top) + 'px';
        hint.style.left = Math.min(Math.max(8, rect.left), window.innerWidth - hint.offsetWidth - 8) + 'px';
    }

    function setHovered(node) {
        if (!picking || picking.hovered === node) return;
        if (picking.hovered) picking.hovered.classList.remove('sfa-help-hover');
        picking.hovered = node;
        if (node) node.classList.add('sfa-help-hover');
    }

    function stopPicking() {
        if (!picking) return;
        setHovered(null);
        picking.panel.classList.remove('sfa-help-picking');
        picking.icon.classList.remove('is-active');
        picking = null;
        if (hint) hint.style.display = 'none';
    }

    function openPanel(panel) {
        if (panel.tagName === 'DETAILS') { panel.open = true; return; }
        var toggle = panel.querySelector('.accordion-button.collapsed');
        if (toggle) toggle.click();
    }

    function startPicking(icon) {
        var panel = icon.closest(PANELS);
        if (!panel) return;
        var again = picking && picking.panel === panel;
        stopPicking();
        if (again) return;  // the ✦ a second time switches it off
        hideButton();
        hidePopover();
        openPanel(panel);
        var title = panelTitle(panel);
        picking = { panel: panel, title: title, icon: icon, hovered: null };
        panel.classList.add('sfa-help-picking');
        icon.classList.add('is-active');
        showHint(panel, title);
    }

    function pickTarget(node) {
        if (!picking || !node || !picking.panel.contains(node)) return null;
        var header = headerOf(picking.panel);
        if (header && header.contains(node)) return header;  // the header explains the panel itself
        var target = node.closest(TARGETS);
        if (!target || !picking.panel.contains(target) || target === picking.panel) target = node;
        // An input inside a label: describe the label, which carries the name.
        if (target.matches('input') && target.closest('label') && picking.panel.contains(target.closest('label'))) {
            target = target.closest('label');
        }
        return target;
    }

    function labelFor(input) {
        if (input.labels && input.labels.length) return clip(input.labels[0].textContent, 80);
        var named = input.getAttribute('aria-label') || input.getAttribute('placeholder') || input.getAttribute('title');
        if (named) return clip(named, 80);
        var row = input.parentElement;
        for (var depth = 0; row && depth < 4; depth++, row = row.parentElement) {
            var text = clip(row.textContent, 80);
            if (text) return text;
        }
        return input.name || input.id || 'input';
    }

    function describe(target) {
        var panel = picking.panel;
        var header = headerOf(panel);
        if (header && target === header) {
            return {
                text: picking.title,
                context: clip('the whole panel "' + picking.title + '" (the user asked what this panel is for); panel content: ' + panel.textContent, MAX_CONTEXT)
            };
        }
        var text = '';
        var bits = ['panel "' + picking.title + '"'];
        var box = target.matches('label') ? target.querySelector('input') : null;
        if (target.matches('input, select, textarea')) {
            var kind = target.type || target.tagName.toLowerCase();
            text = labelFor(target);
            bits.push(kind === 'checkbox' || kind === 'radio'
                ? kind + ', currently ' + (target.checked ? 'on' : 'off')
                : kind + ' field, current value "' + clip(target.value, 60) + '"');
        } else {
            text = clip(target.innerText || target.textContent, MAX_SELECTION);
            if (!text || text.length < 2) {
                text = clip(target.getAttribute('title') || target.getAttribute('aria-label') || text, MAX_SELECTION);
            }
            if (box) bits.push(box.type + ', currently ' + (box.checked ? 'on' : 'off'));
        }
        // Dash pattern ids end up in the input's name, e.g. {"indicator":"rsi","type":"plot-toggle"}.
        var named = box || (target.matches('input') ? target : target.querySelector('input'));
        if (named && named.name) bits.push('control id ' + clip(named.name, 80));
        var host = target.closest('[id]');
        if (host && panel.contains(host) && host.id && host.id.indexOf('{') !== 0) bits.push('element id "' + clip(host.id, 60) + '"');
        bits = bits.concat(surroundings(target, text, panel));
        return { text: text || picking.title, context: clip(bits.filter(Boolean).join('; '), MAX_CONTEXT) };
    }

    function wirePanelHelp() {
        addPanelButtons();
        var queued = false;
        new MutationObserver(function () {
            if (queued) return;
            queued = true;
            setTimeout(function () { queued = false; addPanelButtons(); }, 300);
        }).observe(document.body, { childList: true, subtree: true });

        // Capture phase on window: runs before React's own listeners, so a
        // swallowed click never reaches the checkbox or the button under it.
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'dblclick'].forEach(function (type) {
            window.addEventListener(type, function (e) {
                var icon = e.target.closest && e.target.closest('.sfa-panel-help');
                if (icon) { swallow(e); return; }
                if (picking && picking.panel.contains(e.target)) swallow(e);
            }, true);
        });

        window.addEventListener('click', function (e) {
            var icon = e.target.closest && e.target.closest('.sfa-panel-help');
            if (icon) { swallow(e); startPicking(icon); return; }
            if (!picking) return;
            if (!picking.panel.contains(e.target)) { stopPicking(); return; }  // outside: cancel, let it through
            swallow(e);
            var target = pickTarget(e.target);
            if (!target) return;
            var item = describe(target);
            item.rect = target.getBoundingClientRect();
            target.classList.add('sfa-help-picked');
            setTimeout(function () { target.classList.remove('sfa-help-picked'); }, 700);
            stopPicking();
            ask(item);
        }, true);

        window.addEventListener('mouseover', function (e) {
            if (picking) setHovered(pickTarget(e.target));
        }, true);

        window.addEventListener('keydown', function (e) {
            var icon = e.target.closest && e.target.closest('.sfa-panel-help');
            if (icon && (e.key === 'Enter' || e.key === ' ')) { swallow(e); startPicking(icon); }
        }, true);

        window.addEventListener('resize', stopPicking);
    }

    // -------------------------------------------------------------- wire --
    function wireSelection() {
        var timer = null;
        document.addEventListener('mouseup', function (e) {
            if (button && button.contains(e.target)) return;
            clearTimeout(timer);
            timer = setTimeout(onSelection, 10);  // let the browser settle the selection
        });
        document.addEventListener('keyup', function (e) {
            if (e.key === 'Escape') { stopPicking(); hidePopover(); hideButton(); return; }
            if (e.shiftKey) { clearTimeout(timer); timer = setTimeout(onSelection, 10); }
        });
        document.addEventListener('mousedown', function (e) {
            if (popover && popover.style.display === 'block' && !popover.contains(e.target) && !(button && button.contains(e.target))) hidePopover();
            if (button && !button.contains(e.target)) hideButton();
        });
        window.addEventListener('scroll', hideButton, true);
    }

    function start() {
        fetch('/api/session', { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (info) {
                if (!info) return;
                fillAccount(info);
                if (info.explain) {
                    wireSelection();
                    wirePanelHelp();
                }
            })
            .catch(function () { /* no session endpoint: nothing to do */ });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
