/**
 * Quick-swap keys: ","  previous symbol, "."  next symbol.
 *
 * Not [ and ]: on an Italian (and most non-US) layout those need AltGr, which
 * Windows reports as Ctrl+Alt. Comma and full stop are unshifted everywhere.
 *
 * The keys only click the strip's own buttons, so the server-side swap
 * (lib/dash/callbacks/quick_swap.py) does all the work. They stay quiet while
 * typing, while any modal is open, and whenever the Backtest panel is not on
 * screen, so they never swap the symbol under the Optimizer or Fundamentals.
 */
(function () {
  'use strict';

  function typing(target) {
    if (!target) return false;
    var tag = (target.tagName || '').toUpperCase();
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable === true;
  }

  document.addEventListener('keydown', function (event) {
    if (event.key !== ',' && event.key !== '.') return;
    if (event.ctrlKey || event.metaKey || event.altKey || event.repeat) return;
    if (typing(event.target)) return;
    if (document.querySelector('.modal.show')) return;

    var block = document.getElementById('quick-swap-block');
    if (!block || block.offsetParent === null) return;

    var button = document.getElementById(event.key === ',' ? 'quick-swap-prev' : 'quick-swap-next');
    if (!button) return;
    event.preventDefault();
    button.click();
  });
})();
