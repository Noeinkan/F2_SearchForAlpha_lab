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

    // Dash rebuilds chain rows on expiry/view changes, so use delegated clicks.
    var quotePopup = null;
    var selectedPrice = null;
    function closeQuotePopup(restoreFocus) {
        var anchor = selectedPrice;
        if (quotePopup) { quotePopup.remove(); quotePopup = null; }
        if (selectedPrice) {
            selectedPrice.classList.remove('sfa-flow-chain-price-selected');
            selectedPrice.setAttribute('aria-expanded', 'false');
            selectedPrice = null;
        }
        if (restoreFocus && anchor && anchor.isConnected) { anchor.focus(); }
    }
    function detail(label, value) {
        var row = document.createElement('div');
        row.className = 'sfa-flow-quote-detail';
        var term = document.createElement('span');
        term.textContent = label;
        var number = document.createElement('strong');
        number.textContent = value;
        row.append(term, number);
        return row;
    }
    function payoffCard(cp, strike, premium, multiplier, spot) {
        var card = document.createElement('section');
        card.className = 'sfa-flow-quote-payoff';
        card.innerHTML = '<div class="sfa-flow-chain-preview-eyebrow">ONE LONG CONTRACT · EXPIRY PAYOFF</div>' +
            '<div class="sfa-flow-quote-payoff-metrics">' +
            '<div><span>CONTRACT COST</span><strong class="sfa-flow-quote-payoff-cost"></strong></div>' +
            '<div><span>BREAK-EVEN</span><strong class="sfa-flow-quote-payoff-be"></strong></div>' +
            '</div><div class="sfa-flow-chain-preview-chart" aria-hidden="true"></div>' +
            '<div class="sfa-flow-quote-payoff-note"></div>' +
            '<button type="button" class="sfa-flow-strategy-add">Add to strategy</button>';
        var money = function (value) {
            return '$' + value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        };
        card.querySelector('.sfa-flow-quote-payoff-cost').textContent = money(premium * multiplier);
        card.querySelector('.sfa-flow-quote-payoff-be').textContent =
            money(strike + (cp === 'C' ? premium : -premium));
        card.querySelector('.sfa-flow-quote-payoff-note').textContent =
            money(premium) + ' ask × ' + multiplier.toLocaleString('en-US') + ' shares · before fees';
        drawPayoff(card, cp, strike, premium, multiplier, spot);
        return card;
    }
    // A historical chain carries its own underlying close; the panel's spot is today's.
    function spotFor(el) {
        var scroller = el.closest && el.closest('.sfa-flow-chain-scroll');
        if (scroller && scroller.dataset.source === 'historical') { return Number(scroller.dataset.spot); }
        var chain = el.closest && el.closest('.sfa-flow-chain');
        return Number(chain && chain.dataset.spot);
    }
    function showQuotePopup(price) {
        var data = price.dataset;
        var bid = Number(data.bid);
        var ask = Number(data.ask);
        var strike = Number(data.strike);
        var cp = data.cp;
        if (!(strike > 0) || (cp !== 'C' && cp !== 'P')) { return; }
        var money = function (value) {
            return value > 0 ? '$' + value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : 'Unavailable';
        };
        var popup = document.createElement('section');
        popup.className = 'sfa-flow-quote-popup';
        popup.setAttribute('role', 'dialog');
        popup.setAttribute('aria-label', 'Option quote details');
        var head = document.createElement('div');
        head.className = 'sfa-flow-quote-popup-head';
        var title = document.createElement('strong');
        var chain = price.closest('.sfa-flow-chain');
        var reports = price.closest('.sfa-flow-reports');
        title.textContent = (chain && chain.dataset.ticker ? chain.dataset.ticker + ' · ' : '') +
            (cp === 'C' ? 'Call' : 'Put') + ' · ' + money(strike) + ' strike';
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'sfa-flow-quote-popup-close';
        close.textContent = '×';
        close.setAttribute('aria-label', 'Close quote details');
        close.addEventListener('click', function () { closeQuotePopup(true); });
        head.append(title, close);
        popup.append(head);
        var multiplier = Number(data.multiplier);
        if (ask > 0 && multiplier > 0) {
            var payoff = payoffCard(cp, strike, ask, multiplier, spotFor(price));
            payoff.querySelector('.sfa-flow-strategy-add').addEventListener('click', function () {
                if (window.sfaFlowStrategy) { window.sfaFlowStrategy.add(price); }
                closeQuotePopup();
            });
            popup.append(payoff);
        }
        var scroller = price.closest('.sfa-flow-chain-scroll');
        if (scroller && scroller.dataset.expiry) { popup.append(detail('Expiry', scroller.dataset.expiry)); }
        popup.append(detail('Bid', money(bid)));
        popup.append(detail('Ask', money(ask)));
        popup.append(detail('Last trade', money(Number(data.last))));
        popup.append(detail('Volume', Number(data.volume || 0).toLocaleString('en-US')));
        popup.append(detail('Open interest', Number(data.oi || 0).toLocaleString('en-US')));
        var iv = Number(data.iv);
        popup.append(detail('Implied volatility', iv > 0 ? (iv <= 2 ? iv * 100 : iv).toFixed(1) + '%' : 'Unavailable'));
        if (scroller && scroller.dataset.source === 'historical') {
            popup.append(detail('Source', scroller.dataset.sourceLabel || 'ThetaData EOD'));
            popup.append(detail('Observed', data.observed ? new Date(data.observed).toLocaleString() : 'Unavailable'));
        } else {
            popup.append(detail('Source', 'Yahoo Finance'));
            var epoch = Number(reports && reports.dataset.scanEpoch);
            popup.append(detail('Report scanned', epoch > 0 ? new Date(epoch * 1000).toLocaleString() : 'Unavailable'));
            popup.append(detail('Individual quote time', 'Not supplied'));
        }
        var quality = document.createElement('div');
        quality.className = 'sfa-flow-quote-quality';
        if (bid > 0 && ask > 0 && bid > ask) {
            quality.classList.add('sfa-flow-quote-quality-bad');
            quality.textContent = 'Crossed quote: bid exceeds ask. Do not treat these prices as executable.';
        } else if (!(bid > 0 && ask > 0)) {
            quality.classList.add('sfa-flow-quote-quality-bad');
            quality.textContent = 'Incomplete quote: bid or ask is missing.';
        } else {
            quality.textContent = 'Bid/ask order is normal. Quote freshness and execution are unverified.';
        }
        if (epoch > 0) {
            var parts = new Intl.DateTimeFormat('en-US', {
                timeZone: 'America/New_York', weekday: 'short', hour: '2-digit',
                minute: '2-digit', hourCycle: 'h23'
            }).formatToParts(new Date(epoch * 1000));
            var clock = {};
            parts.forEach(function (part) { clock[part.type] = part.value; });
            var minutes = Number(clock.hour) * 60 + Number(clock.minute);
            if (clock.weekday === 'Sat' || clock.weekday === 'Sun' || minutes < 570 || minutes >= 960) {
                quality.textContent += ' Scan was outside regular US equity-option hours; quotes may be from a prior session.';
                quality.classList.add('sfa-flow-quote-quality-bad');
            }
        }
        popup.append(quality);
        if (data.flagged === 'true') {
            var flag = document.createElement('div');
            flag.className = 'sfa-flow-quote-flag';
            flag.textContent = data.reason ? 'Scanner flag: ' + data.reason : 'Flagged by scanner as unusual activity.';
            popup.append(flag);
        }
        document.body.append(popup);
        var rect = price.getBoundingClientRect();
        var width = popup.getBoundingClientRect().width;
        var left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
        var below = rect.bottom + 8;
        var height = popup.getBoundingClientRect().height;
        popup.style.left = left + 'px';
        popup.style.top = (below + height <= window.innerHeight - 8 ? below : Math.max(8, rect.top - height - 8)) + 'px';
        quotePopup = popup;
        selectedPrice = price;
        price.classList.add('sfa-flow-chain-price-selected');
        price.setAttribute('aria-expanded', 'true');
        close.focus();
    }
    function drawPayoff(card, cp, strike, premium, multiplier, spot) {
        var host = card.querySelector('.sfa-flow-chain-preview-chart');
        if (!host) { return; }
        var svgNS = 'http://www.w3.org/2000/svg';
        var width = 480, height = 170, left = 73, right = 18, top = 34, bottom = 42;
        var span = Math.max(premium * 3, strike * 0.1);
        var minX = Math.max(0, strike - span), maxX = strike + span;
        var breakEven = strike + (cp === 'C' ? premium : -premium);
        var cost = premium * multiplier;
        var upside = Math.max(cost, (span - premium) * multiplier);
        var minY = -cost * 1.35, maxY = upside * 1.15;
        var x = function (value) { return left + (value - minX) / (maxX - minX) * (width - left - right); };
        var y = function (value) { return top + (maxY - value) / (maxY - minY) * (height - top - bottom); };
        var payoff = function (value) {
            return (Math.max(cp === 'C' ? value - strike : strike - value, 0) - premium) * multiplier;
        };
        var axisMoney = function (value) {
            return '$' + value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        };
        var pnlMoney = function (value) {
            return (value > 0 ? '+' : value < 0 ? '−' : '') +
                '$' + Math.abs(value).toLocaleString('en-US', {maximumFractionDigits: 0});
        };
        var svg = document.createElementNS(svgNS, 'svg');
        svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-label', (cp === 'C' ? 'Call' : 'Put') + ' expiry profit and loss, before fees');
        function add(tag, attrs, label) {
            var el = document.createElementNS(svgNS, tag);
            Object.keys(attrs).forEach(function (key) { el.setAttribute(key, attrs[key]); });
            if (label !== undefined) { el.textContent = label; }
            svg.appendChild(el);
            return el;
        }
        function path(points, cls) {
            add('path', {d: points.map(function (p, i) {
                return (i ? 'L' : 'M') + x(p).toFixed(1) + ',' + y(payoff(p)).toFixed(1);
            }).join(' '), 'class': cls});
        }
        add('line', {x1: left, y1: y(0), x2: width - right, y2: y(0), 'class': 'sfa-flow-payoff-zero'});
        add('text', {x: 6, y: 14, 'class': 'sfa-flow-payoff-axis-title'}, 'P/L ($)');
        add('line', {x1: x(strike), y1: top, x2: x(strike), y2: height - bottom, 'class': 'sfa-flow-payoff-strike'});
        if (cp === 'C') {
            path([minX, strike, breakEven], 'sfa-flow-payoff-loss');
            path([breakEven, maxX], 'sfa-flow-payoff-gain');
        } else if (breakEven < minX) {
            path([minX, strike, maxX], 'sfa-flow-payoff-loss');
        } else {
            path([minX, breakEven], 'sfa-flow-payoff-gain');
            path([breakEven, strike, maxX], 'sfa-flow-payoff-loss');
        }
        if (breakEven >= minX) {
            add('circle', {cx: x(breakEven), cy: y(0), r: 4, 'class': 'sfa-flow-payoff-be-dot'});
            add('text', {x: x(breakEven), y: 14, 'text-anchor': 'middle', 'class': 'sfa-flow-payoff-be-label'}, 'BE ' + axisMoney(breakEven));
        }
        if (spot > 0 && spot >= minX && spot <= maxX) {
            add('line', {x1: x(spot), y1: top, x2: x(spot), y2: height - bottom, 'class': 'sfa-flow-payoff-spot'});
            add('text', {x: x(spot), y: 29, 'text-anchor': 'middle', 'class': 'sfa-flow-payoff-spot-label'}, 'Now ' + axisMoney(spot));
        }
        var favorable = payoff(cp === 'C' ? maxX : minX);
        if (favorable > 0) {
            add('text', {x: left - 8, y: y(favorable) + 3, 'text-anchor': 'end', 'class': 'sfa-flow-payoff-axis'}, pnlMoney(favorable));
        }
        add('text', {x: left - 8, y: y(0) + 3, 'text-anchor': 'end', 'class': 'sfa-flow-payoff-axis'}, '$0');
        add('text', {x: left - 8, y: y(-cost) + 3, 'text-anchor': 'end', 'class': 'sfa-flow-payoff-axis'}, pnlMoney(-cost));
        add('text', {x: left, y: height - 23, 'text-anchor': 'start', 'class': 'sfa-flow-payoff-axis'}, axisMoney(minX));
        add('text', {x: x(strike), y: height - 23, 'text-anchor': 'middle', 'class': 'sfa-flow-payoff-axis'}, 'Strike ' + axisMoney(strike));
        add('text', {x: width - right, y: height - 23, 'text-anchor': 'end', 'class': 'sfa-flow-payoff-axis'}, axisMoney(maxX));
        add('text', {x: width / 2, y: height - 5, 'text-anchor': 'middle', 'class': 'sfa-flow-payoff-axis-title'}, 'Underlying price at expiry →');
        host.replaceChildren(svg);
    }
    document.addEventListener('click', function (ev) {
        var quote = ev.target.closest && ev.target.closest('.sfa-flow-chain-price');
        if (!quote) {
            if (quotePopup && !quotePopup.contains(ev.target)) { closeQuotePopup(); }
            return;
        }
        var same = quote === selectedPrice;
        closeQuotePopup();
        if (same) { return; }
        showQuotePopup(quote);
    });
    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' && quotePopup) { closeQuotePopup(true); }
    });
    document.addEventListener('focusin', function (ev) {
        if (quotePopup && ev.target !== selectedPrice && !quotePopup.contains(ev.target)) {
            closeQuotePopup();
        }
    });
    window.addEventListener('scroll', function () { if (quotePopup) { closeQuotePopup(); } }, true);
    window.addEventListener('resize', function () { if (quotePopup) { closeQuotePopup(); } });

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
        if (selectedPrice && !selectedPrice.isConnected) { closeQuotePopup(); }
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
