(function () {
    if (window.__sfaFundamentalsEscBound) {
        return;
    }
    window.__sfaFundamentalsEscBound = true;

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') {
            return;
        }

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
    });
})();
