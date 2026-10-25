/*
 * Watchlist editor: drag rows to reorder (lib/dash/layout/header_watchlist.py).
 *
 * The rows are re-rendered by Dash after every edit, so the listeners are
 * delegated from the document instead of bound to rows. On drop the new order
 * is read back from each row's data-symbol and handed to Dash through
 * `watchlist-editor-order`; the server callback turns it into the draft and
 * re-renders. Nothing here touches the saved list: that happens only on Save.
 */
(function () {
    'use strict';

    var dragged = null;

    function rowOf(target) {
        return target && target.closest ? target.closest('.sfa-wle-row') : null;
    }

    function clearMarks() {
        document.querySelectorAll('.sfa-wle-row.drop-before, .sfa-wle-row.drop-after')
            .forEach(function (el) { el.classList.remove('drop-before', 'drop-after'); });
    }

    function placeAfter(row, clientY) {
        var box = row.getBoundingClientRect();
        return clientY > box.top + box.height / 2;
    }

    document.addEventListener('dragstart', function (event) {
        var row = rowOf(event.target);
        if (!row) { return; }
        dragged = row;
        row.classList.add('dragging');
        event.dataTransfer.effectAllowed = 'move';
        // Firefox starts no drag without data.
        event.dataTransfer.setData('text/plain', row.getAttribute('data-symbol') || '');
    });

    document.addEventListener('dragover', function (event) {
        var row = rowOf(event.target);
        if (!dragged || !row || row === dragged) { return; }
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        clearMarks();
        row.classList.add(placeAfter(row, event.clientY) ? 'drop-after' : 'drop-before');
    });

    document.addEventListener('drop', function (event) {
        var row = rowOf(event.target);
        if (!dragged || !row || row === dragged) { return; }
        event.preventDefault();
        // Compute the order only; the DOM is React's, and moving rows here
        // would leave it out of step with what Dash renders next.
        var moving = dragged.getAttribute('data-symbol');
        var anchor = row.getAttribute('data-symbol');
        var symbols = Array.prototype.map.call(
            row.parentNode.querySelectorAll('.sfa-wle-row'),
            function (el) { return el.getAttribute('data-symbol'); }
        ).filter(function (s) { return s !== moving; });
        var at = symbols.indexOf(anchor) + (placeAfter(row, event.clientY) ? 1 : 0);
        symbols.splice(at, 0, moving);
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('watchlist-editor-order', {
                data: { symbols: symbols, nonce: Date.now() }
            });
        }
    });

    document.addEventListener('dragend', function () {
        if (dragged) { dragged.classList.remove('dragging'); }
        dragged = null;
        clearMarks();
    });
}());
