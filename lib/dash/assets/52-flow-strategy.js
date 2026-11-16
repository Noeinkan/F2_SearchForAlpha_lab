/* "Add to strategy" in the Flow quote popup: hand the quote to the strategy panel.
 *
 * The panel (lib/dash/flow_strategy_view.py) owns the legs, their validation, the payoff,
 * the Greeks and the send-to-paper step — all priced in Python by lib/options/pricing.py.
 * This file only carries the clicked quote across and brings the panel into view.
 */
(function () {
    'use strict';

    function reveal(selector) {
        var panel = document.querySelector(selector);
        if (panel) { panel.open = true; panel.scrollIntoView({block: 'start', behavior: 'smooth'}); }
    }

    function add(price) {
        var chain = price.closest('.sfa-flow-chain');
        if (!chain || !window.dash_clientside || !window.dash_clientside.set_props) { return; }
        var scroller = price.closest('.sfa-flow-chain-scroll');
        var historical = !!scroller && scroller.dataset.source === 'historical';
        var expiry = (scroller && scroller.dataset.expiry) || '';
        var data = price.dataset;
        window.dash_clientside.set_props('flow-strategy-add', {data: {
            ticker: chain.dataset.ticker || '', expiry: expiry,
            key: expiry + '|' + data.cp + '|' + Number(data.strike),
            cp: data.cp, strike: Number(data.strike), bid: Number(data.bid), ask: Number(data.ask),
            iv: data.iv || null, multiplier: Number(data.multiplier),
            spot: Number(historical ? scroller.dataset.spot : chain.dataset.spot) || null,
            observed: historical ? (scroller.dataset.observed || '') : '',
            trade_date: historical ? (scroller.dataset.tradeDate || '') : '',
            nonce: Date.now(),
        }});
        reveal('#flow-strategy-panel');
    }

    document.addEventListener('click', function (event) {
        if (event.target.closest && event.target.closest('#flow-strategy-paper')) {
            window.setTimeout(function () { reveal('.sfa-flow-paper'); }, 150);
        }
    });

    window.sfaFlowStrategy = {add: add};
})();
