/* Optional Flow strategy preview. All amounts are expiry P/L before fees. */
(function () {
    'use strict';

    var strategies = new Map();
    var NS = 'http://www.w3.org/2000/svg';
    function money(value) {
        return '$' + Math.abs(value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    function shortMoney(value) {
        return (value < 0 ? '−' : value > 0 ? '+' : '') +
            '$' + Math.abs(value).toLocaleString('en-US', {maximumFractionDigits: 0});
    }
    function premium(leg) { return leg.side === 'buy' ? leg.ask : leg.bid; }
    function when(stamp) {
        var date = new Date(stamp);
        return Number.isNaN(date.getTime()) ? stamp : date.toLocaleString('en-GB', {
            day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'});
    }
    function payoff(legs, price) {
        return legs.reduce(function (total, leg) {
            var intrinsic = Math.max(leg.cp === 'C' ? price - leg.strike : leg.strike - price, 0);
            return total + (leg.side === 'buy' ? 1 : -1) * leg.qty * leg.multiplier * (intrinsic - premium(leg));
        }, 0);
    }
    function analyze(legs) {
        if (!legs.length) { return null; }
        var strikes = Array.from(new Set(legs.map(function (leg) { return leg.strike; }))).sort(function (a, b) { return a - b; });
        var points = [0].concat(strikes.filter(function (strike) { return strike > 0; }));
        var values = points.map(function (price) { return payoff(legs, price); });
        var roots = [];
        function root(value) {
            if (value >= 0 && !roots.some(function (other) { return Math.abs(other - value) < 0.00001; })) { roots.push(value); }
        }
        for (var i = 0; i < points.length - 1; i++) {
            if (Math.abs(values[i]) < 0.000001) { root(points[i]); }
            if (values[i] * values[i + 1] < 0) {
                root(points[i] - values[i] * (points[i + 1] - points[i]) / (values[i + 1] - values[i]));
            }
        }
        var last = points[points.length - 1];
        var lastValue = values[values.length - 1];
        var rightSlope = legs.reduce(function (sum, leg) {
            return sum + (leg.cp === 'C' ? (leg.side === 'buy' ? 1 : -1) * leg.qty * leg.multiplier : 0);
        }, 0);
        if (Math.abs(lastValue) < 0.000001) { root(last); }
        if (rightSlope && -lastValue / rightSlope > 0) { root(last - lastValue / rightSlope); }
        roots.sort(function (a, b) { return a - b; });
        return {
            roots: roots,
            netCredit: legs.reduce(function (sum, leg) {
                return sum + (leg.side === 'sell' ? 1 : -1) * leg.qty * leg.multiplier * premium(leg);
            }, 0),
            maxProfit: rightSlope > 0 ? Infinity : Math.max.apply(null, values),
            maxLoss: rightSlope < 0 ? -Infinity : Math.min.apply(null, values),
            strikes: strikes,
        };
    }
    function svgEl(svg, tag, attrs, label) {
        var el = document.createElementNS(NS, tag);
        Object.keys(attrs).forEach(function (key) { el.setAttribute(key, attrs[key]); });
        if (label !== undefined) { el.textContent = label; }
        svg.appendChild(el);
        return el;
    }
    function drawChart(host, legs, summary, spot) {
        var width = 560, height = 210, left = 74, right = 18, top = 31, bottom = 44;
        var lowStrike = summary.strikes[0], highStrike = summary.strikes[summary.strikes.length - 1];
        var maxPremium = Math.max.apply(null, legs.map(premium));
        var pad = Math.max((highStrike - lowStrike) * 0.5, maxPremium * 3, (spot || highStrike) * 0.1, 1);
        var minX = Math.max(0, Math.min(lowStrike, spot > 0 ? spot : lowStrike) - pad);
        var maxX = Math.max(highStrike, spot > 0 ? spot : highStrike) + pad;
        var xs = [minX].concat(summary.strikes.filter(function (value) { return value > minX && value < maxX; }), [maxX]);
        var ys = xs.map(function (price) { return payoff(legs, price); });
        var lowY = Math.min(0, Math.min.apply(null, ys)), highY = Math.max(0, Math.max.apply(null, ys));
        var range = Math.max(highY - lowY, 1);
        lowY -= range * 0.12; highY += range * 0.12;
        var x = function (value) { return left + (value - minX) / (maxX - minX) * (width - left - right); };
        var y = function (value) { return top + (highY - value) / (highY - lowY) * (height - top - bottom); };
        var svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-label', 'Combined profit and loss at expiry, before fees');
        svgEl(svg, 'line', {x1: left, y1: y(0), x2: width - right, y2: y(0), 'class': 'sfa-flow-payoff-zero'});
        svgEl(svg, 'text', {x: 7, y: 16, 'class': 'sfa-flow-payoff-axis-title'}, 'P/L ($)');
        summary.strikes.forEach(function (strike) {
            svgEl(svg, 'line', {x1: x(strike), y1: top, x2: x(strike), y2: height - bottom, 'class': 'sfa-flow-payoff-strike'});
        });
        if (spot > minX && spot < maxX) {
            svgEl(svg, 'line', {x1: x(spot), y1: top, x2: x(spot), y2: height - bottom, 'class': 'sfa-flow-payoff-spot'});
            svgEl(svg, 'text', {x: x(spot), y: 15, 'text-anchor': 'middle', 'class': 'sfa-flow-payoff-spot-label'}, 'Now ' + money(spot));
        }
        var segmentXs = xs.concat(summary.roots.filter(function (value) { return value > minX && value < maxX; }))
            .sort(function (a, b) { return a - b; });
        for (var i = 0; i < segmentXs.length - 1; i++) {
            var a = segmentXs[i], b = segmentXs[i + 1];
            if (b - a < 0.000001) { continue; }
            var cls = payoff(legs, (a + b) / 2) >= 0 ? 'sfa-flow-payoff-gain' : 'sfa-flow-payoff-loss';
            svgEl(svg, 'path', {d: 'M' + x(a) + ',' + y(payoff(legs, a)) + ' L' + x(b) + ',' + y(payoff(legs, b)), 'class': cls});
        }
        summary.roots.filter(function (value) { return value >= minX && value <= maxX; }).forEach(function (value) {
            svgEl(svg, 'circle', {cx: x(value), cy: y(0), r: 4, 'class': 'sfa-flow-payoff-be-dot'});
            svgEl(svg, 'text', {x: x(value), y: height - 24, 'text-anchor': 'middle', 'class': 'sfa-flow-payoff-be-label'},
                'BE ' + money(value));
        });
        svgEl(svg, 'text', {x: left - 8, y: y(0) + 4, 'text-anchor': 'end', 'class': 'sfa-flow-payoff-axis'}, '$0');
        if (Math.max.apply(null, ys) > 0) {
            svgEl(svg, 'text', {x: left - 8, y: y(Math.max.apply(null, ys)) + 4, 'text-anchor': 'end', 'class': 'sfa-flow-payoff-axis'}, shortMoney(Math.max.apply(null, ys)));
        }
        if (Math.min.apply(null, ys) < 0) {
            svgEl(svg, 'text', {x: left - 8, y: y(Math.min.apply(null, ys)) + 4, 'text-anchor': 'end', 'class': 'sfa-flow-payoff-axis'}, shortMoney(Math.min.apply(null, ys)));
        }
        svgEl(svg, 'text', {x: left, y: height - 24, 'text-anchor': 'start', 'class': 'sfa-flow-payoff-axis'}, money(minX));
        svgEl(svg, 'text', {x: width - right, y: height - 24, 'text-anchor': 'end', 'class': 'sfa-flow-payoff-axis'}, money(maxX));
        svgEl(svg, 'text', {x: width / 2, y: height - 5, 'text-anchor': 'middle', 'class': 'sfa-flow-payoff-axis-title'}, 'Underlying price at expiry →');
        host.replaceChildren(svg);
    }
    function render(chain) {
        var builder = chain.querySelector('.sfa-flow-strategy');
        if (!builder) { return; }
        var ticker = chain.dataset.ticker || '';
        var legs = strategies.get(ticker) || [];
        var list = builder.querySelector('.sfa-flow-strategy-legs');
        var output = builder.querySelector('.sfa-flow-strategy-results');
        list.replaceChildren(); output.replaceChildren();
        if (!legs.length) {
            list.textContent = 'No options added yet. Click a bid or ask in the chain, then choose “Add to strategy”.';
            return;
        }
        legs.forEach(function (leg, index) {
            var row = document.createElement('div');
            row.className = 'sfa-flow-strategy-leg';
            row.innerHTML = '<select aria-label="Buy or sell"><option value="buy">Buy</option><option value="sell">Sell</option></select>' +
                '<span class="sfa-flow-strategy-leg-name"></span>' +
                '<label>Contracts <input type="number" min="1" max="100" step="1" aria-label="Contracts"></label>' +
                '<span class="sfa-flow-strategy-leg-price"></span>' +
                '<button type="button" aria-label="Remove option">×</button>';
            row.dataset.index = String(index);
            row.querySelector('select').value = leg.side;
            row.querySelector('input').value = String(leg.qty);
            row.querySelector('.sfa-flow-strategy-leg-name').textContent =
                (leg.cp === 'C' ? 'Call ' : 'Put ') + money(leg.strike);
            row.querySelector('.sfa-flow-strategy-leg-price').textContent =
                money(premium(leg)) + ' ' + (leg.side === 'buy' ? 'ask' : 'bid') + ' × ' + leg.multiplier;
            list.append(row);
        });
        var result = analyze(legs);
        var expiry = legs[0].expiry;
        output.innerHTML = '<div class="sfa-flow-strategy-heading"></div>' +
            '<div class="sfa-flow-strategy-metrics">' +
            '<div><span>AT THE START</span><strong class="sfa-flow-strategy-entry"></strong></div>' +
            '<div><span>BREAK-EVEN PRICES</span><strong class="sfa-flow-strategy-be"></strong></div>' +
            '<div><span>BEST AT EXPIRY</span><strong class="sfa-flow-strategy-best"></strong></div>' +
            '<div><span>MOST YOU COULD LOSE</span><strong class="sfa-flow-strategy-worst"></strong></div>' +
            '</div><div class="sfa-flow-strategy-chart"></div>' +
            '<div class="sfa-flow-strategy-foot"></div>' +
            '<button type="button" class="sfa-flow-strategy-paper"></button>';
        var observedAt = legs[0].observed;
        output.querySelector('.sfa-flow-strategy-paper').textContent = observedAt
            ? 'Replay from this date in paper trading →' : 'Send to paper trading →';
        var date = new Date(expiry + 'T00:00:00Z');
        output.querySelector('.sfa-flow-strategy-heading').textContent =
            'Combined payoff at expiry · ' + (Number.isNaN(date.getTime()) ? expiry : date.toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC'})) +
            (observedAt ? ' · historical quotes observed ' + when(observedAt) : '');
        output.querySelector('.sfa-flow-strategy-entry').textContent =
            result.netCredit > 0 ? 'Receive ' + money(result.netCredit) : result.netCredit < 0 ? 'Pay ' + money(result.netCredit) : '$0.00';
        output.querySelector('.sfa-flow-strategy-be').textContent =
            result.roots.length ? result.roots.map(money).join(' · ') : 'None';
        output.querySelector('.sfa-flow-strategy-best').textContent =
            result.maxProfit === Infinity ? 'No fixed limit' : (result.maxProfit >= 0 ? money(result.maxProfit) : 'Loss ' + money(result.maxProfit));
        output.querySelector('.sfa-flow-strategy-worst').textContent =
            result.maxLoss === -Infinity ? 'No fixed limit' : money(Math.min(result.maxLoss, 0));
        var ratio = Number.isFinite(result.maxProfit) && Number.isFinite(result.maxLoss) && result.maxLoss < 0 && result.maxProfit > 0
            ? ' · Best gain ÷ most you could lose: ' + (result.maxProfit / -result.maxLoss).toFixed(2) : '';
        output.querySelector('.sfa-flow-strategy-foot').textContent =
            'All figures combine ' + legs.length + ' option leg' + (legs.length === 1 ? '' : 's') +
            ' at expiry, before fees. Buy uses ask; sell uses bid. Quotes are indicative.' + ratio;
        if (legs.some(function (leg) { return leg.bid > leg.ask; })) {
            var warning = document.createElement('div');
            warning.className = 'sfa-flow-strategy-warning';
            warning.textContent = 'One or more bid/ask quotes are crossed. Treat this payoff as illustrative; those prices may not be executable.';
            output.append(warning);
        }
        drawChart(output.querySelector('.sfa-flow-strategy-chart'), legs, result,
            observedAt ? legs[0].spot : Number(chain.dataset.spot));
    }
    function add(price) {
        var chain = price.closest('.sfa-flow-chain');
        if (!chain) { return; }
        var ticker = chain.dataset.ticker || '';
        var builder = chain.querySelector('.sfa-flow-strategy');
        var message = builder && builder.querySelector('.sfa-flow-strategy-message');
        if (!builder || !message) { return; }
        var legs = strategies.get(ticker) || [];
        var scroller = price.closest('.sfa-flow-chain-scroll');
        var expiry = scroller?.dataset.expiry || '';
        var historical = scroller?.dataset.source === 'historical';
        var observed = historical ? (scroller.dataset.observed || '') : '';
        var cp = price.dataset.cp, strike = Number(price.dataset.strike);
        var ask = Number(price.dataset.ask), bid = Number(price.dataset.bid);
        var multiplier = Number(price.dataset.multiplier);
        var error = '';
        if (!expiry || !['C', 'P'].includes(cp) || !(strike > 0 && ask > 0 && multiplier > 0)) {
            error = 'This quote needs a valid ask, strike, and expiry.';
        } else if (legs.length && (legs[0].observed || '') !== observed) {
            error = 'Keep every option on the same observation: the strategy uses ' +
                (legs[0].observed ? 'historical quotes from ' + when(legs[0].observed) : 'current quotes') +
                '. Remove the current legs to start from ' + (observed ? when(observed) : 'current quotes') + '.';
        } else if (legs.length && legs[0].expiry !== expiry) {
            error = 'Choose options with the same expiry. Remove the current legs to start another expiry.';
        } else if (legs.some(function (leg) { return leg.cp === cp && leg.strike === strike; })) {
            error = 'That option is already added. Change its contract count below.';
        } else if (legs.length >= 4) {
            error = 'This preview holds up to four options. Remove one to add another.';
        }
        builder.open = true;
        if (error) { message.textContent = error; builder.scrollIntoView({block: 'nearest', behavior: 'smooth'}); return; }
        legs.push({cp: cp, strike: strike, ask: ask, bid: bid, multiplier: multiplier,
            expiry: expiry, qty: 1, side: 'buy', observed: observed,
            tradeDate: historical ? (scroller.dataset.tradeDate || '') : '',
            spot: historical ? Number(scroller.dataset.spot) : NaN});
        strategies.set(ticker, legs);
        message.textContent = (cp === 'C' ? 'Call ' : 'Put ') + money(strike) + ' added. Choose Buy or Sell below.';
        render(chain);
        builder.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    }
    document.addEventListener('change', function (event) {
        var row = event.target.closest && event.target.closest('.sfa-flow-strategy-leg');
        if (!row) { return; }
        var chain = row.closest('.sfa-flow-chain');
        var legs = strategies.get(chain.dataset.ticker || '') || [];
        var leg = legs[Number(row.dataset.index)];
        if (!leg) { return; }
        if (event.target.matches('select')) {
            if (event.target.value === 'sell' && !(leg.bid > 0)) {
                row.closest('.sfa-flow-strategy').querySelector('.sfa-flow-strategy-message').textContent = 'A bid is needed to preview a sale.';
                event.target.value = leg.side;
                return;
            }
            leg.side = event.target.value;
        } else if (event.target.matches('input')) {
            var count = Number(event.target.value);
            leg.qty = Number.isInteger(count) && count >= 1 && count <= 100 ? count : 1;
        }
        render(chain);
    });
    document.addEventListener('click', function (event) {
        var paper = event.target.closest && event.target.closest('.sfa-flow-strategy-paper');
        if (paper) {
            var paperChain = paper.closest('.sfa-flow-chain');
            var paperLegs = strategies.get(paperChain.dataset.ticker || '') || [];
            var message = paperChain.querySelector('.sfa-flow-strategy-message');
            if (!window.dash_clientside || !window.dash_clientside.set_props) {
                message.textContent = 'Paper trading is unavailable. Refresh the Flow page and try again.';
                return;
            }
            var fromHistory = !!paperLegs[0].observed;
            window.dash_clientside.set_props('flow-paper-strategy-selection', {data: {
                ticker: paperChain.dataset.ticker, expiry: paperLegs[0].expiry,
                legs: paperLegs.map(function (leg) {
                    return {key: leg.expiry + '|' + leg.cp + '|' + leg.strike,
                        side: leg.side, qty: leg.qty};
                }), nonce: Date.now(),
                source: fromHistory ? 'historical' : 'current',
                trade_date: fromHistory ? paperLegs[0].tradeDate : null,
                observed_at: fromHistory ? paperLegs[0].observed : null,
            }});
            var panel = document.querySelector('.sfa-flow-paper');
            if (panel) { panel.open = true; panel.scrollIntoView({block: 'start', behavior: 'smooth'}); }
            message.textContent = fromHistory
                ? 'Loading daily quotes from ' + when(paperLegs[0].observed) + ' through expiry for Historical replay…'
                : 'Strategy sent to paper trading. Review the recorded prices before opening it.';
            return;
        }
        var button = event.target.closest && event.target.closest('.sfa-flow-strategy-leg > button');
        if (!button) { return; }
        var row = button.closest('.sfa-flow-strategy-leg');
        var chain = row.closest('.sfa-flow-chain');
        var legs = strategies.get(chain.dataset.ticker || '') || [];
        legs.splice(Number(row.dataset.index), 1);
        chain.querySelector('.sfa-flow-strategy-message').textContent = 'Option removed.';
        render(chain);
    });
    window.sfaFlowStrategy = {add: add, analyze: analyze, payoff: payoff};
    function start() {
        document.querySelectorAll('.sfa-flow-chain').forEach(render);
        new MutationObserver(function (changes) {
            changes.forEach(function (change) {
                change.addedNodes.forEach(function (node) {
                    if (node.nodeType !== 1) { return; }
                    var builder = node.matches && node.matches('.sfa-flow-strategy') ? node : node.querySelector && node.querySelector('.sfa-flow-strategy');
                    if (builder) { render(builder.closest('.sfa-flow-chain')); }
                });
            });
        }).observe(document.body, {childList: true, subtree: true});
    }
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', start); }
    else { start(); }
})();
