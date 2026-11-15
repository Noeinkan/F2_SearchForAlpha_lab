/*
 * Explain, chart points — what a ✦ smart-help click on a chart asks Gemini.
 *
 * Charts draw on a canvas (the price chart, Lightweight Charts) or in SVG
 * (Plotly, e.g. the Fundamentals Growth cards), so the clicked element says
 * nothing useful. The chart's own hover state does: the bar under the
 * crosshair (window.sfaChart.hoverPoint(), 10-sfa-chart.js) or the point
 * Plotly is showing a tooltip for (graphDiv._hoverdata). This file turns that
 * into the {text, context} pair 95-explain.js sends to /api/explain.
 *
 * describe(chart, panelTitle) returns null when it has nothing better than
 * the generic description, and 95-explain.js falls back to that.
 * Only ever called by 95-explain.js, which wires nothing for non-admins.
 */
(function () {
    'use strict';

    var MAX_TEXT = 300;
    var MAX_CONTEXT = 600;
    var PLAIN = 'explain in plain words what this point shows and how to read it';

    function clip(text, limit) {
        var value = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
        return value.length <= limit ? value : value.slice(0, limit - 1) + '…';
    }

    function signed(pct) {
        return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
    }

    // ------------------------------------------------- price chart (LWC) --
    function markerText(m) {
        var side = m.side === 'buy' ? 'Buy' : 'Sell';
        return m.accepted
            ? side + ' signal that triggered (arrow with ' + side.charAt(0) + ')'
            : side + ' signal rejected by the consecutive-signal rules (grey arrow)';
    }

    function pricePoint(panelTitle) {
        var api = window.sfaChart;
        var p = api && typeof api.hoverPoint === 'function' ? api.hoverPoint() : null;
        if (!p) return null;
        var where = p.ticker + ' ' + (p.interval || '').toUpperCase() + ' bar of ' + p.date;
        var ohlc = 'open ' + p.open + ', high ' + p.high + ', low ' + p.low + ', close ' + p.close
            + ' (' + signed(p.changePct) + ' open to close)';
        var pane = p.pane || 'price';
        var here = p.indicators.filter(function (r) { return r.pane === pane; });
        var overlays = p.indicators.filter(function (r) { return r.pane === 'price'; });
        var text;
        if (p.markers.length && pane === 'price') {
            text = p.markers.map(markerText).join(' + ') + ' on ' + p.date;
        } else if (pane === 'volume') {
            text = 'Volume ' + (p.volume || '?') + ' on ' + p.date;
        } else if (pane !== 'price' && here.length) {
            text = here.map(function (r) { return r.title + ' = ' + r.text; }).join(', ') + ' on ' + p.date;
        } else {
            text = (p.chartType === 'line' || p.chartType === 'area' || p.chartType === 'baseline'
                ? 'Price' : 'Candle') + ' of ' + p.date + ': close ' + p.close + ' (' + signed(p.changePct) + ')';
        }
        var bits = [
            'panel "' + panelTitle + '"',
            'the user clicked one point of the price chart: ' + where,
            'clicked pane: ' + pane,
            ohlc,
        ];
        if (p.volume) bits.push('volume ' + p.volume);
        if (overlays.length && pane === 'price') {
            bits.push('overlays at this bar: ' + overlays.map(function (r) { return r.title + ' ' + r.text; }).join(', '));
        }
        if (here.length && pane !== 'price') {
            bits.push('values in this pane: ' + here.map(function (r) { return r.title + ' ' + r.text; }).join(', '));
        }
        if (p.markers.length) bits.push('markers on this bar: ' + p.markers.map(markerText).join('; '));
        bits.push(PLAIN);
        return { text: clip(text, MAX_TEXT), context: clip(bits.join('; '), MAX_CONTEXT) };
    }

    // ------------------------------------------------------------ Plotly --
    // The chart's name: its layout title, else the first "*title*" element
    // of the card around it (e.g. .sfa-fundamentals-chart-title).
    function plotlyTitle(gd) {
        var layoutTitle = gd.layout && gd.layout.title;
        var text = layoutTitle && (layoutTitle.text || (typeof layoutTitle === 'string' ? layoutTitle : ''));
        if (text) return clip(text, 60);
        var node = gd.parentElement;
        for (var depth = 0; node && depth < 4; depth++, node = node.parentElement) {
            var found = node.querySelector('[class*="title"]');
            if (found && !gd.contains(found)) return clip(found.textContent, 60);
        }
        return '';
    }

    function axisSuffix(gd) {
        var y = gd.layout && gd.layout.yaxis;
        return (y && y.ticksuffix) || '';
    }

    function formatValue(value, suffix) {
        if (typeof value !== 'number') return String(value);
        var digits = Math.abs(value) >= 100 ? 0 : 2;
        return value.toLocaleString('en-US', { maximumFractionDigits: digits }) + suffix;
    }

    function seriesSummary(trace, suffix) {
        var xs = trace.x || [], ys = trace.y || [];
        var first = -1, last = -1;
        for (var i = 0; i < ys.length; i++) {
            if (ys[i] == null || isNaN(ys[i])) continue;
            if (first < 0) first = i;
            last = i;
        }
        if (first < 0) return '';
        return 'series has ' + ys.length + ' points, from ' + xs[first] + ' (' + formatValue(ys[first], suffix)
            + ') to ' + xs[last] + ' (' + formatValue(ys[last], suffix) + ')';
    }

    function plotlyPoint(gd, panelTitle) {
        var title = plotlyTitle(gd);
        var suffix = axisSuffix(gd);
        var hovered = (gd._hoverdata || []).filter(function (pt) { return pt && pt.y != null; });
        var bits = ['panel "' + panelTitle + '"'];
        if (!hovered.length) {
            if (!title) return null;
            bits.push('the user clicked the chart "' + title + '" (not a single point)');
            var main = gd.data && gd.data[0];
            if (main) bits.push(seriesSummary(main, suffix));
            bits.push('a dotted line, if present, is the linear trend; explain in plain words what this chart shows');
            return { text: title + ' chart', context: clip(bits.filter(Boolean).join('; '), MAX_CONTEXT) };
        }
        var pt = hovered[0];
        var name = title || (pt.data && pt.data.name) || 'value';
        var text = name + ' ' + pt.x + ': ' + formatValue(pt.y, suffix);
        bits.push('the user clicked one point of the chart "' + (title || name) + '"');
        if (pt.data && pt.data.name && pt.data.name !== title) bits.push('series "' + clip(pt.data.name, 40) + '"');
        if (pt.data) bits.push(seriesSummary(pt.data, suffix));
        bits.push(PLAIN);
        return { text: clip(text, MAX_TEXT), context: clip(bits.filter(Boolean).join('; '), MAX_CONTEXT) };
    }

    window.sfaExplainPoints = {
        describe: function (chart, panelTitle) {
            try {
                if (chart.id === 'financial-chart') return pricePoint(panelTitle);
                if (chart.classList.contains('js-plotly-plot')) return plotlyPoint(chart, panelTitle);
            } catch (err) {
                if (window.console && console.warn) console.warn('sfaExplainPoints', err);
            }
            return null;
        }
    };
})();
