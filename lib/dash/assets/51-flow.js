/* Flow Scanner UX helpers (no Dash callbacks involved).
 *
 * 1. The toolbar's ⋯ menu is a <details>: close it on an outside click or once
 *    an item is picked.
 * 2. Each time an option-chain table is (re)rendered, scroll it so the spot
 *    divider sits mid-view — otherwise it opens on the deepest ITM strike.
 */
(function () {
    'use strict';

    document.addEventListener('click', function (ev) {
        var menus = document.querySelectorAll('details.sfa-flow-menu[open]');
        for (var i = 0; i < menus.length; i++) {
            var menu = menus[i];
            var inside = menu.contains(ev.target);
            var onItem = ev.target.closest && ev.target.closest('.sfa-flow-menu-item');
            if (!inside || onItem) { menu.open = false; }
        }
    });

    function centreOnSpot(scroller) {
        if (!scroller || scroller.clientHeight === 0) { return false; }
        var target = scroller.querySelector('.sfa-flow-chain-spot-divider')
            || scroller.querySelector('.sfa-flow-chain-atm');
        if (!target) { return true; }
        var offset = target.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
        scroller.scrollTop += offset - scroller.clientHeight / 2;
        return true;
    }

    // React may keep the same <table> node when only its rows change (another
    // expiry, another view), so "already centred" is keyed on the content.
    function signature(table) {
        var rows = table.tBodies.length ? table.tBodies[0].rows : [];
        if (!rows.length) { return ''; }
        return rows.length + '|' + rows[0].textContent + '|' + rows[rows.length - 1].textContent;
    }

    function sweep() {
        var tables = document.querySelectorAll('.sfa-flow-chain-scroll table');
        for (var i = 0; i < tables.length; i++) {
            var table = tables[i];
            var sig = signature(table);
            if (table.dataset.sfaCentred === sig) { continue; }
            // Hidden (collapsed card): try again when it becomes visible.
            if (centreOnSpot(table.parentElement)) { table.dataset.sfaCentred = sig; }
        }
    }

    var queued = false;
    function schedule() {
        if (queued) { return; }
        queued = true;
        window.requestAnimationFrame(function () { queued = false; sweep(); });
    }

    function start() {
        new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
        // A collapsed ticker card opening reveals a chain that measured 0 tall.
        document.addEventListener('toggle', schedule, true);
        schedule();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
