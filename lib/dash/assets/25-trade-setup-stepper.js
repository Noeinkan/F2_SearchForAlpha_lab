/**
 * Visible − / + steppers for Trade Setup number inputs.
 * Native browser spin buttons are nearly invisible on dark themes; these
 * buttons sit beside the field and write through React's value setter so
 * Dash dcc.Input callbacks still fire.
 */
(function () {
  'use strict';

  function stepInput(input, dir) {
    if (!input || input.disabled || input.readOnly) return;

    var step = parseFloat(input.getAttribute('step') || '1');
    if (!isFinite(step) || step <= 0) step = 1;

    var minAttr = input.getAttribute('min');
    var maxAttr = input.getAttribute('max');
    var min = minAttr === null || minAttr === '' ? -Infinity : parseFloat(minAttr);
    var max = maxAttr === null || maxAttr === '' ? Infinity : parseFloat(maxAttr);

    var current = parseFloat(input.value);
    if (!isFinite(current)) current = isFinite(min) && min > -Infinity ? min : 0;

    var next = current + dir * step;
    // Avoid float dust (e.g. 0.1 + 0.2)
    var decimals = (String(step).split('.')[1] || '').length;
    if (decimals) next = Math.round(next * Math.pow(10, decimals)) / Math.pow(10, decimals);
    if (isFinite(min)) next = Math.max(min, next);
    if (isFinite(max)) next = Math.min(max, next);

    var setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value'
    ).set;
    setter.call(input, String(next));
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  document.addEventListener('click', function (event) {
    var btn = event.target.closest('.sfa-num-stepper__btn');
    if (!btn) return;
    var wrap = btn.closest('.sfa-num-stepper');
    if (!wrap) return;
    var input = wrap.querySelector('input[type="number"]');
    var dir = parseInt(btn.getAttribute('data-dir') || '0', 10);
    if (!input || !dir) return;
    event.preventDefault();
    stepInput(input, dir);
  });
})();
