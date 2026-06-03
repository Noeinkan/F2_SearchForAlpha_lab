(function () {
    if (window.__sfaFundamentalsEscBound) {
        return;
    }
    window.__sfaFundamentalsEscBound = true;

    function isVisible(element) {
        return element && window.getComputedStyle(element).display !== 'none';
    }

    function isInsideFundamentalsTable(target) {
        if (!target || !target.closest) {
            return false;
        }
        return Boolean(target.closest(
            '#fundamentals-financial-table, #fundamentals-big-five-table, #fundamentals-valuation-table'
        ));
    }

    function dismissFundamentalsExplain() {
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
        if (!isVisible(panel)) {
            return;
        }

        var target = event.target;
        if (target.closest('#fundamentals-valuation-explain')) {
            return;
        }
        if (isInsideFundamentalsTable(target)) {
            return;
        }

        dismissFundamentalsExplain();
    });
})();
