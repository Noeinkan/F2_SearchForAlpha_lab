(function () {
    if (window.__sfaFundamentalsEscBound) {
        return;
    }
    window.__sfaFundamentalsEscBound = true;

    window.__sfaLastFundamentalsCell = null;

    var scrollTimer = null;
    var explainObserver = null;
    var tableObserver = null;

    var TABLE_SELECTOR = [
        '#fundamentals-financial-table',
        '#fundamentals-big-five-table',
        '#fundamentals-valuation-table-a',
        '#fundamentals-valuation-table-b',
        '#fundamentals-dcf-table',
    ].join(', ');

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
        var tableRoot = target.closest(TABLE_SELECTOR);
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

    function scrollSelectedCellIntoView() {
        var overlay = document.getElementById('fundamentals-overlay');
        if (!isVisible(overlay)) {
            return;
        }
        var selected = overlay.querySelector(
            TABLE_SELECTOR.split(', ').map(function (sel) {
                return sel + ' td.dash-cell.cell--selected';
            }).join(', ')
        );
        if (selected) {
            selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    }

    function scrollExplainIntoView() {
        var panel = document.getElementById('fundamentals-valuation-explain');
        if (!isVisible(panel) || !panel.children || !panel.children.length) {
            return;
        }
        panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    function scheduleFundamentalsScroll() {
        if (scrollTimer) {
            window.clearTimeout(scrollTimer);
        }
        scrollTimer = window.setTimeout(function () {
            scrollTimer = null;
            scrollSelectedCellIntoView();
            scrollExplainIntoView();
        }, 100);
    }

    function bindExplainObserver() {
        var panel = document.getElementById('fundamentals-valuation-explain');
        if (!panel || explainObserver) {
            return;
        }
        explainObserver = new MutationObserver(function () {
            scheduleFundamentalsScroll();
        });
        explainObserver.observe(panel, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['style', 'class'],
        });
        scheduleFundamentalsScroll();
    }

    function bindTableSelectionObserver() {
        var overlay = document.getElementById('fundamentals-overlay');
        if (!overlay || tableObserver) {
            return;
        }
        tableObserver = new MutationObserver(function () {
            scheduleFundamentalsScroll();
        });
        tableObserver.observe(overlay, {
            subtree: true,
            attributes: true,
            attributeFilter: ['class'],
        });
    }

    function watchForExplainPanel() {
        bindExplainObserver();
        bindTableSelectionObserver();
        if (explainObserver && tableObserver) {
            return;
        }
        var root = document.getElementById('fundamentals-content')
            || document.getElementById('fundamentals-overlay')
            || document.body;
        var bootObserver = new MutationObserver(function () {
            bindExplainObserver();
            bindTableSelectionObserver();
            if (explainObserver && tableObserver) {
                bootObserver.disconnect();
            }
        });
        bootObserver.observe(root, { childList: true, subtree: true });
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

    document.addEventListener('click', function (event) {
        if (!event.target || !event.target.closest) {
            return;
        }
        if (event.target.closest('.sfa-dep-chip')) {
            scheduleFundamentalsScroll();
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watchForExplainPanel);
    } else {
        watchForExplainPanel();
    }
})();
