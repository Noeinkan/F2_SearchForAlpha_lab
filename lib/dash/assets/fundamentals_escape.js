(function () {
    if (window.__sfaFundamentalsEscBound) {
        return;
    }
    window.__sfaFundamentalsEscBound = true;

    window.__sfaLastFundamentalsCell = null;

    function isVisible(element) {
        return element && window.getComputedStyle(element).display !== 'none';
    }

    function getFundamentalsTableCell(target) {
        if (!target || !target.closest) {
            return null;
        }
        var cell = target.closest('td.dash-cell');
        if (!cell) {
            return null;
        }
        var tableRoot = target.closest(
            '#fundamentals-financial-table, #fundamentals-big-five-table, #fundamentals-valuation-table-a, #fundamentals-valuation-table-b'
        );
        if (!tableRoot) {
            return null;
        }
        var row = cell.getAttribute('data-dash-row');
        var column = cell.getAttribute('data-dash-column');
        if (row === null || column === null) {
            return null;
        }
        return { tableId: tableRoot.id, row: row, column: column };
    }

    function sameFundamentalsCell(left, right) {
        return Boolean(
            left
            && right
            && left.tableId === right.tableId
            && left.row === right.row
            && left.column === right.column
        );
    }

    function dismissFundamentalsExplain() {
        window.__sfaLastFundamentalsCell = null;

        var signal = document.getElementById('fundamentals-esc-signal');
        if (!signal) {
            return;
        }

        var nextValue = String(Date.now());
        var prototype = window.HTMLInputElement && window.HTMLInputElement.prototype;
        var descriptor = prototype ? Object.getOwnPropertyDescriptor(prototype, 'value') : null;
        if (descriptor && descriptor.set) {
            descriptor.set.call(signal, nextValue);
        } else {
            signal.value = nextValue;
        }
        signal.dispatchEvent(new Event('input', { bubbles: true }));
    }

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') {
            return;
        }
        dismissFundamentalsExplain();
    });

    document.addEventListener('mousedown', function (event) {
        var overlay = document.getElementById('fundamentals-overlay');
        if (!isVisible(overlay) || !overlay.contains(event.target)) {
            return;
        }

        var panel = document.getElementById('fundamentals-valuation-explain');
        var cell = getFundamentalsTableCell(event.target);

        if (cell) {
            if (isVisible(panel) && sameFundamentalsCell(window.__sfaLastFundamentalsCell, cell)) {
                dismissFundamentalsExplain();
                return;
            }
            window.__sfaLastFundamentalsCell = cell;
            return;
        }

        if (!isVisible(panel)) {
            return;
        }

        if (event.target.closest('#fundamentals-valuation-explain')) {
            return;
        }

        dismissFundamentalsExplain();
    });
})();
