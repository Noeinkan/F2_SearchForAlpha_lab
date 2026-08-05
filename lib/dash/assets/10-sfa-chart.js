/**
 * SearchForAlpha — TradingView Lightweight Charts glue.
 *
 * Owns the price chart end to end on the client. Python ships a data payload
 * (see lib/dash/chart_payload.py) into `chart-payload-store`; a clientside
 * callback hands it here and this module renders it. Pan, zoom, crosshair and
 * autoscale never touch the server.
 *
 * The chart instance is created ONCE and mutated in place. Recreating it on
 * every update is what makes web charts feel janky — it drops the user's
 * scroll position and re-runs the whole canvas setup. `apply()` therefore
 * diffs series by id and calls setData() on the survivors.
 *
 * Loaded after 00-lightweight-charts.standalone.production.js by filename
 * order; `ensureLib()` still guards in case that ever changes.
 */
(function () {
    'use strict';

    if (window.sfaChart) { return; }

    var CONTAINER_ID = 'financial-chart';

    // Numeric enum fallbacks. The standalone bundle exposes these as getters on
    // the global, but the values are part of the documented public API and are
    // stable, so a rename degrades instead of blanking the chart.
    var PRICE_SCALE_MODE = { normal: 0, log: 1, percent: 2 };
    var LINE_STYLE = { solid: 0, dotted: 1, dashed: 2 };
    var CROSSHAIR_MODE = { normal: 0, magnet: 1 };

    var state = {
        chart: null,
        container: null,
        legendEl: null,
        series: new Map(),      // id -> { api, spec, pane }
        priceLines: new Map(),  // seriesId -> [priceLine handles]
        markers: null,          // createSeriesMarkers plugin handle
        paneKeys: [],           // pane key per pane index
        payload: null,
        chartType: 'candles',
        scaleMode: 'normal',
        rangeHandler: null,
        clickHandler: null,
    };

    // ---------------------------------------------------------------- helpers

    function ensureLib() {
        return (typeof window !== 'undefined' && window.LightweightCharts) || null;
    }

    function enumValue(name, key, fallbackMap) {
        var lib = ensureLib();
        var group = lib && lib[name];
        if (group && typeof group === 'object') {
            var direct = group[key];
            if (typeof direct === 'number') { return direct; }
        }
        return fallbackMap[key];
    }

    function seriesConstructor(type) {
        var lib = ensureLib();
        if (!lib) { return null; }
        return lib[(type || 'Line') + 'Series'] || lib.LineSeries;
    }

    /**
     * Chart-wide options derived from the payload's theme block.
     *
     * `initial` gates the options that describe a *viewport* rather than an
     * appearance. `barSpacing`/`rightOffset` are where the chart should start,
     * not where it should always be — and this object is re-applied on every
     * payload update, so including them unconditionally silently reset the
     * user's zoom whenever they toggled an indicator, cycled the theme, or
     * changed chart type. Measured: a 1,962-bar window snapped back to 126.
     */
    function chartOptions(theme, meta, initial) {
        var t = theme || {};
        var opts = {
            autoSize: true,
            layout: {
                background: { color: t.bg || '#0A0A0A' },
                textColor: t.text_secondary || '#8A8A8A',
                fontFamily: t.font || 'Source Sans 3, sans-serif',
                fontSize: 11,
                // Apache-2.0 attribution — see assets/VENDOR.md. Do not disable.
                attributionLogo: true,
                panes: {
                    separatorColor: t.border || '#2A2A2A',
                    separatorHoverColor: t.accent || '#FFA726',
                    enableResize: true,
                },
            },
            grid: {
                vertLines: { color: t.grid || '#1A1A1A', style: LINE_STYLE.dotted },
                horzLines: { color: t.grid || '#1A1A1A', style: LINE_STYLE.dotted },
            },
            crosshair: {
                mode: enumValue('CrosshairMode', 'normal', CROSSHAIR_MODE),
                vertLine: { color: t.accent || '#FFA726', width: 1, style: LINE_STYLE.dashed, labelBackgroundColor: t.accent || '#FFA726' },
                horzLine: { color: t.accent || '#FFA726', width: 1, style: LINE_STYLE.dashed, labelBackgroundColor: t.accent || '#FFA726' },
            },
            rightPriceScale: {
                borderColor: t.border || '#2A2A2A',
                scaleMargins: { top: 0.08, bottom: 0.08 },
            },
            timeScale: {
                borderColor: t.border || '#2A2A2A',
                // Intraday payloads carry epoch seconds; without this the axis
                // shows dates only and every bar in a session looks identical.
                timeVisible: !!(meta && meta.subdaily),
                secondsVisible: false,
                // LWC defaults minBarSpacing to 0.5px, which silently caps how
                // far `fitContent` can zoom out: a 3,473-bar 1H series needs
                // 1,736px and only gets ~1,090px, so FIT showed 58% of the data
                // with the rest loaded but off-screen and no hint it was there.
                // 0.02px/bar fits ~50k bars in a 1,000px pane.
                minBarSpacing: 0.02,
            },
            localization: {
                priceFormatter: function (p) {
                    return p == null ? '' : p.toFixed((meta && meta.precision) != null ? meta.precision : 2);
                },
            },
        };
        if (initial) {
            opts.timeScale.barSpacing = 8;
            opts.timeScale.rightOffset = 4;
        }
        return opts;
    }

    // ----------------------------------------------------------------- legend

    function buildLegend() {
        if (state.legendEl && state.legendEl.parentNode) { return state.legendEl; }
        var el = document.createElement('div');
        el.className = 'sfa-chart-legend';
        el.setAttribute('aria-live', 'off');
        state.container.appendChild(el);
        state.legendEl = el;
        return el;
    }

    function fmt(value, precision) {
        if (value == null || isNaN(value)) { return '--'; }
        return Number(value).toFixed(precision != null ? precision : 2);
    }

    function fmtVolume(value) {
        if (value == null || isNaN(value)) { return '--'; }
        var v = Number(value);
        if (v >= 1e9) { return (v / 1e9).toFixed(2) + 'B'; }
        if (v >= 1e6) { return (v / 1e6).toFixed(2) + 'M'; }
        if (v >= 1e3) { return (v / 1e3).toFixed(1) + 'K'; }
        return String(Math.round(v));
    }

    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    /** Decimals for a series readout, keyed by payload pane. */
    function seriesPrecision(paneKey, metaPrecision) {
        if (paneKey === 'price' || paneKey === 'vwap') {
            return metaPrecision != null ? metaPrecision : 2;
        }
        if (paneKey === 'macd' || paneKey === 'atr') { return 4; }
        if (paneKey === 'obv') { return 0; }
        if (paneKey === 'volume') { return 0; }
        return 2;  // rsi / cci / adx
    }

    function formatSeriesValue(paneKey, value, metaPrecision) {
        if (paneKey === 'volume') { return fmtVolume(value); }
        if (paneKey === 'obv') { return fmtVolume(value); }
        return fmt(value, seriesPrecision(paneKey, metaPrecision));
    }

    /**
     * Collect visible overlay/pane values at the crosshair from LWC's
     * param.seriesData. Skips the price candle and the main volume histogram
     * (those already appear in the OHLC row as C / V).
     */
    function collectIndicatorRows(seriesData, metaPrecision) {
        var rows = [];
        if (!seriesData || !state.payload) { return rows; }
        var specs = state.payload.series || [];
        for (var i = 0; i < specs.length; i++) {
            var spec = specs[i];
            if (!spec || !spec.id || spec.id === 'volume') { continue; }
            var entry = state.series.get(spec.id);
            if (!entry) { continue; }
            var pt = seriesData.get(entry.api);
            if (!pt) { continue; }
            var value = pt.value != null ? pt.value : pt.close;
            if (value == null || isNaN(value)) { continue; }
            var opts = spec.options || {};
            var title = opts.title || spec.id;
            var color = pt.color || opts.color || opts.lineColor || opts.topColor
                || (state.payload.theme && state.payload.theme.text_secondary) || '#8A8A8A';
            // Histogram bar colours often carry an alpha suffix (e.g. #26C28199).
            if (typeof color === 'string' && /^#[0-9A-Fa-f]{8}$/.test(color)) {
                color = color.slice(0, 7);
            }
            rows.push({
                title: title,
                color: color,
                text: formatSeriesValue(spec.pane, value, metaPrecision),
            });
        }
        return rows;
    }

    /**
     * Anchor the info panel near the crosshair, flipping when near an edge.
     * `point` null → park top-left (idle / cursor-left fallback).
     */
    function positionLegend(point) {
        if (!state.legendEl || !state.container) { return; }
        var el = state.legendEl;
        if (!point || point.x == null || point.y == null) {
            el.style.left = '12px';
            el.style.top = '8px';
            return;
        }
        var pad = 8;
        var offset = 14;
        var maxW = state.container.clientWidth || 0;
        var maxH = state.container.clientHeight || 0;
        var w = el.offsetWidth || 0;
        var h = el.offsetHeight || 0;
        var x = point.x + offset;
        var y = point.y + offset;
        if (maxW && x + w + pad > maxW) { x = point.x - w - offset; }
        if (maxH && y + h + pad > maxH) { y = point.y - h - offset; }
        if (x < pad) { x = pad; }
        if (y < pad) { y = pad; }
        el.style.left = Math.round(x) + 'px';
        el.style.top = Math.round(y) + 'px';
    }

    /**
     * Render the floating O/H/L/C + visible indicator readout.
     * `bar` null → last bar, parked top-left. `point` positions the panel.
     */
    function updateLegend(bar, volume, indicatorRows, point) {
        if (!state.legendEl || !state.payload) { return; }
        var meta = state.payload.meta || {};
        var theme = state.payload.theme || {};
        var precision = meta.precision != null ? meta.precision : 2;
        var following = !!(point && point.x != null && point.y != null);

        if (!bar) {
            var candles = state.payload.candles || [];
            bar = candles.length ? candles[candles.length - 1] : null;
            if (!bar) { state.legendEl.innerHTML = ''; return; }
            var vols = state.payload.volumes;
            volume = vols && vols.length ? vols[vols.length - 1].value : null;
            if (!indicatorRows) {
                indicatorRows = lastBarIndicatorRows(bar.time, precision);
            }
        }

        var up = bar.close >= bar.open;
        var color = up ? (theme.up || '#26C281') : (theme.down || '#EF5350');
        var change = bar.close - bar.open;
        var pct = bar.open ? (change / bar.open) * 100 : 0;
        var sign = change >= 0 ? '+' : '';

        var cells = [
            ['O', fmt(bar.open, precision)],
            ['H', fmt(bar.high, precision)],
            ['L', fmt(bar.low, precision)],
            ['C', fmt(bar.close, precision)],
        ];
        if (volume != null) { cells.push(['V', fmtVolume(volume)]); }

        var html = '<div class="sfa-chart-legend-row">';
        html += '<span class="sfa-chart-legend-symbol">' + escapeHtml(meta.ticker || '') + '</span>';
        html += '<span class="sfa-chart-legend-interval">'
            + escapeHtml((meta.interval || '').toUpperCase()) + '</span>';
        for (var i = 0; i < cells.length; i++) {
            html += '<span class="sfa-chart-legend-cell"><i>' + cells[i][0] + '</i>'
                + '<b style="color:' + color + '">' + cells[i][1] + '</b></span>';
        }
        html += '<span class="sfa-chart-legend-cell"><b style="color:' + color + '">'
            + sign + fmt(change, precision) + ' (' + sign + pct.toFixed(2) + '%)</b></span>';
        html += '</div>';

        if (indicatorRows && indicatorRows.length) {
            html += '<div class="sfa-chart-legend-inds">';
            for (var j = 0; j < indicatorRows.length; j++) {
                var row = indicatorRows[j];
                html += '<div class="sfa-chart-legend-ind">'
                    + '<i style="color:' + escapeHtml(row.color) + '">'
                    + escapeHtml(row.title) + '</i>'
                    + '<b style="color:' + escapeHtml(row.color) + '">'
                    + escapeHtml(row.text) + '</b></div>';
            }
            html += '</div>';
        }

        state.legendEl.innerHTML = html;
        state.legendEl.classList.toggle('sfa-chart-legend--follow', following);
        positionLegend(following ? point : null);
    }

    /** Idle fallback: last-bar values from payload.series data (no seriesData). */
    function lastBarIndicatorRows(time, metaPrecision) {
        var rows = [];
        var specs = (state.payload && state.payload.series) || [];
        for (var i = 0; i < specs.length; i++) {
            var spec = specs[i];
            if (!spec || !spec.id || spec.id === 'volume') { continue; }
            var data = spec.data || [];
            if (!data.length) { continue; }
            var pt = null;
            if (time != null) {
                for (var k = data.length - 1; k >= 0; k--) {
                    if (data[k].time === time) { pt = data[k]; break; }
                }
            }
            if (!pt) { pt = data[data.length - 1]; }
            var value = pt.value != null ? pt.value : pt.close;
            if (value == null || isNaN(value)) { continue; }
            var opts = spec.options || {};
            rows.push({
                title: opts.title || spec.id,
                color: opts.color || opts.lineColor || opts.topColor
                    || (state.payload.theme && state.payload.theme.text_secondary) || '#8A8A8A',
                text: formatSeriesValue(spec.pane, value, metaPrecision),
            });
        }
        return rows;
    }

    // ------------------------------------------------------------------ panes

    /**
     * Grow/shrink the pane count to match the payload and apply height weights.
     *
     * Panes are addressed by index, so removing one shifts every pane after it.
     * Rebuilding from the tail avoids invalidating indices mid-loop.
     */
    function syncPanes(payload) {
        var panes = payload.panes || [];
        var existing = state.chart.panes();

        for (var i = existing.length; i < panes.length; i++) {
            state.chart.addPane();
        }
        existing = state.chart.panes();
        for (var j = existing.length - 1; j >= panes.length; j--) {
            try { state.chart.removePane(j); } catch (e) { /* pane already gone */ }
        }

        existing = state.chart.panes();
        for (var k = 0; k < panes.length && k < existing.length; k++) {
            var weight = panes[k].height || 1;
            if (typeof existing[k].setStretchFactor === 'function') {
                existing[k].setStretchFactor(weight);
            }
        }
        state.paneKeys = panes.map(function (p) { return p.key; });
    }

    // ----------------------------------------------------------------- series

    function priceSeriesOptions(payload) {
        var theme = payload.theme || {};
        var meta = payload.meta || {};
        var up = theme.up || '#26C281';
        var down = theme.down || '#EF5350';
        var precision = meta.precision != null ? meta.precision : 2;
        var format = { priceFormat: { type: 'price', precision: precision, minMove: Math.pow(10, -precision) } };

        switch (state.chartType) {
            case 'hollow':
                // LWC has no hollow mode; a transparent up-body over a colored
                // border is exactly what TradingView's hollow candles look like.
                return Object.assign({
                    upColor: 'rgba(0,0,0,0)', downColor: down,
                    borderUpColor: up, borderDownColor: down,
                    wickUpColor: up, wickDownColor: down,
                }, format);
            case 'bars':
                return Object.assign({ upColor: up, downColor: down, thinBars: false }, format);
            case 'line':
                return Object.assign({ color: theme.accent || '#FFA726', lineWidth: 2 }, format);
            case 'area':
                return Object.assign({
                    lineColor: theme.accent || '#FFA726', lineWidth: 2,
                    topColor: (theme.accent || '#FFA726') + '55', bottomColor: (theme.accent || '#FFA726') + '05',
                }, format);
            case 'baseline':
                return Object.assign({
                    topLineColor: up, bottomLineColor: down,
                    topFillColor1: up + '44', topFillColor2: up + '05',
                    bottomFillColor1: down + '05', bottomFillColor2: down + '44',
                }, format);
            default:
                return Object.assign({
                    upColor: up, downColor: down,
                    borderUpColor: up, borderDownColor: down,
                    wickUpColor: up, wickDownColor: down,
                }, format);
        }
    }

    function priceSeriesType() {
        switch (state.chartType) {
            case 'bars': return 'Bar';
            case 'line': return 'Line';
            case 'area': return 'Area';
            case 'baseline': return 'Baseline';
            default: return 'Candlestick';   // candles + hollow
        }
    }

    /** Candles carry OHLC; line/area/baseline need a single value per point. */
    function priceSeriesData(payload) {
        var type = priceSeriesType();
        if (type === 'Candlestick' || type === 'Bar') { return payload.candles || []; }
        return (payload.candles || []).map(function (c) {
            return { time: c.time, value: c.close };
        });
    }

    function clearPriceLines(id) {
        var lines = state.priceLines.get(id);
        var entry = state.series.get(id);
        if (lines && entry) {
            lines.forEach(function (h) {
                try { entry.api.removePriceLine(h); } catch (e) { /* series gone */ }
            });
        }
        state.priceLines.delete(id);
    }

    function removeSeries(id) {
        var entry = state.series.get(id);
        if (!entry) { return; }
        clearPriceLines(id);
        try { state.chart.removeSeries(entry.api); } catch (e) { /* already detached */ }
        state.series.delete(id);
    }

    /**
     * Diff the series set against the payload.
     *
     * A series is recreated only when its type or pane changed — otherwise it
     * keeps its handle and just takes new data, which is what preserves the
     * viewport across sidebar toggles.
     */
    function syncSeries(payload) {
        var lib = ensureLib();
        var specs = payload.series || [];
        var wanted = new Set(['__price__']);

        // Price series first so it owns pane 0's price scale.
        var priceType = priceSeriesType();
        var priceEntry = state.series.get('__price__');
        if (!priceEntry || priceEntry.spec !== priceType) {
            if (priceEntry) { removeSeries('__price__'); }
            var ctor = seriesConstructor(priceType);
            var api = state.chart.addSeries(ctor, priceSeriesOptions(payload), 0);
            priceEntry = { api: api, spec: priceType, pane: 0 };
            state.series.set('__price__', priceEntry);
            state.markers = null;   // marker plugin is bound to the old handle
        } else {
            priceEntry.api.applyOptions(priceSeriesOptions(payload));
        }
        priceEntry.api.setData(priceSeriesData(payload));

        for (var i = 0; i < specs.length; i++) {
            var spec = specs[i];
            var paneIndex = state.paneKeys.indexOf(spec.pane);
            if (paneIndex < 0) { continue; }
            wanted.add(spec.id);

            var entry = state.series.get(spec.id);
            var signature = spec.type + '@' + paneIndex;
            if (entry && entry.spec !== signature) {
                removeSeries(spec.id);
                entry = null;
            }
            if (!entry) {
                var seriesApi = state.chart.addSeries(
                    seriesConstructor(spec.type), spec.options || {}, paneIndex
                );
                entry = { api: seriesApi, spec: signature, pane: paneIndex };
                state.series.set(spec.id, entry);
            } else {
                entry.api.applyOptions(spec.options || {});
            }
            entry.api.setData(spec.data || []);

            clearPriceLines(spec.id);
            if (spec.priceLines && spec.priceLines.length) {
                var handles = spec.priceLines.map(function (line) {
                    return entry.api.createPriceLine({
                        price: line.price,
                        color: line.color,
                        lineWidth: line.lineWidth || 1,
                        lineStyle: LINE_STYLE[line.style || 'dashed'],
                        axisLabelVisible: line.axisLabel !== false,
                        title: line.title || '',
                    });
                });
                state.priceLines.set(spec.id, handles);
            }
        }

        state.series.forEach(function (_entry, id) {
            if (!wanted.has(id)) { removeSeries(id); }
        });

        // Volume lives on its own overlay scale so it never squashes price.
        var volumeSpec = specs.filter(function (s) { return s.id === 'volume'; })[0];
        if (volumeSpec) {
            var volEntry = state.series.get('volume');
            if (volEntry) {
                volEntry.api.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
            }
        }

        applyMarkers(payload, priceEntry.api, lib);
    }

    function applyMarkers(payload, priceApi, lib) {
        var markers = payload.markers || [];
        if (!lib || typeof lib.createSeriesMarkers !== 'function') { return; }
        if (!state.markers) {
            state.markers = lib.createSeriesMarkers(priceApi, markers);
        } else {
            state.markers.setMarkers(markers);
        }
    }

    // ------------------------------------------------------------- lifecycle

    function ensureChart(payload) {
        var lib = ensureLib();
        if (!lib) { return null; }

        var container = document.getElementById(CONTAINER_ID);
        if (!container) { return null; }

        if (state.chart && state.container === container) {
            state.chart.applyOptions(chartOptions(payload.theme, payload.meta));
            return state.chart;
        }

        // Container was replaced (route change / layout rebuild) — start clean.
        if (state.chart) { destroy(); }

        state.container = container;
        state.chart = lib.createChart(container, chartOptions(payload.theme, payload.meta, true));
        buildLegend();

        state.chart.subscribeCrosshairMove(function (param) {
            var priceEntry = state.series.get('__price__');
            var volEntry = state.series.get('volume');
            var meta = (state.payload && state.payload.meta) || {};
            var precision = meta.precision != null ? meta.precision : 2;
            if (!param || !param.time || !priceEntry) { updateLegend(null); return; }
            var bar = param.seriesData.get(priceEntry.api);
            var vol = volEntry ? param.seriesData.get(volEntry.api) : null;
            if (!bar) { updateLegend(null); return; }
            // line/area payloads only carry `value`; fall back to a flat bar.
            if (bar.close == null) {
                bar = { open: bar.value, high: bar.value, low: bar.value, close: bar.value };
            }
            var inds = collectIndicatorRows(param.seriesData, precision);
            updateLegend(bar, vol ? vol.value : null, inds, param.point || null);
        });

        state.rangeHandler = function () { publishVisibleRange(); };
        state.chart.timeScale().subscribeVisibleLogicalRangeChange(debounce(state.rangeHandler, 120));

        return state.chart;
    }

    function destroy() {
        if (state.chart) {
            try { state.chart.remove(); } catch (e) { /* already disposed */ }
        }
        if (state.legendEl && state.legendEl.parentNode) {
            state.legendEl.parentNode.removeChild(state.legendEl);
        }
        state.chart = null;
        state.container = null;
        state.legendEl = null;
        state.series = new Map();
        state.priceLines = new Map();
        state.markers = null;
        state.paneKeys = [];
    }

    function debounce(fn, ms) {
        var timer = null;
        return function () {
            var args = arguments, self = this;
            if (timer) { clearTimeout(timer); }
            timer = setTimeout(function () { fn.apply(self, args); }, ms);
        };
    }

    // ------------------------------------------------------ store round-trips

    /**
     * Mirror the visible window into a hidden input so Dash can persist it.
     *
     * Writing through the native value setter + a synthetic `input` event is
     * the same trick the splitter uses in callbacks/layout.py — React ignores a
     * plain `.value =` assignment.
     */
    function writeToInput(id, value) {
        var el = document.getElementById(id);
        if (!el) { return; }
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(el, value);
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function publishVisibleRange() {
        if (!state.chart || !state.payload) { return; }
        var range = state.chart.timeScale().getVisibleRange();
        if (!range) { return; }
        writeToInput('chart-range-input', JSON.stringify({ start: range.from, end: range.to }));
        updateBarCount(range);
    }

    /**
     * Recompute the toolbar bar-count readout locally.
     *
     * Deliberately not a server callback: it would fire on every pan frame and
     * put Python back in the interaction loop, which is the whole thing this
     * migration removes.
     */
    function updateBarCount(range) {
        var el = document.getElementById('chart-bar-count');
        if (!el || !state.payload) { return; }
        var candles = state.payload.candles || [];
        var meta = state.payload.meta || {};
        if (!candles.length) { el.textContent = ''; return; }

        var visible = candles;
        if (range) {
            visible = candles.filter(function (c) {
                var t = typeof c.time === 'string' ? c.time : c.time;
                return t >= range.from && t <= range.to;
            });
        }
        if (!visible.length) { visible = candles; }

        var label = (meta.interval || '').toUpperCase();
        el.textContent = visible.length.toLocaleString() + ' bars · ' + label
            + ' · ' + formatStamp(visible[0].time, meta.subdaily)
            + ' → ' + formatStamp(visible[visible.length - 1].time, meta.subdaily);
    }

    function formatStamp(time, subdaily) {
        if (typeof time === 'string') { return time; }
        var d = new Date(time * 1000);
        var iso = d.toISOString();
        return subdaily ? iso.slice(0, 16).replace('T', ' ') : iso.slice(0, 10);
    }

    // -------------------------------------------------------------- public API

    /**
     * Ask the server for a first payload.
     *
     * Dash will not dispatch `update_chart_payload` on page load: it sits
     * downstream of `load_data`, which PreventUpdates once the server bootstrap
     * has already fetched the data, and Dash drops callbacks downstream of one
     * that never ran. A real click is a fresh dispatch, so the chart asks for
     * its own data as soon as the container exists. Polls because the glue can
     * evaluate before Dash has finished rendering the layout.
     */
    function requestFirstPayload() {
        var attempts = 0;
        var tick = function () {
            // Only stop once we actually have bars — an empty placeholder must
            // not cancel the boot click that fetches real data.
            if (state.payload && state.payload.candles && state.payload.candles.length) {
                return;
            }
            var btn = document.getElementById('chart-boot-btn');
            var frame = document.getElementById(CONTAINER_ID);
            if (btn && frame) {
                btn.click();
                // Keep polling. A single click used to `return` here, which
                // raced the Dash round-trip: empty_payload landed, apply()
                // correctly rejected it, and boot never asked again — black
                // void with DATA rows in the footer. Space retries so we do
                // not hammer update_chart_payload while Yahoo is still warm.
                if (++attempts < 24) { setTimeout(tick, 250); }
                return;
            }
            if (++attempts < 60) { setTimeout(tick, 100); }
        };
        tick();
    }

    var api = {
        /** Render a payload. Safe to call repeatedly; the chart is reused. */
        apply: function (payload) {
            // Empty candles [] is truthy in JS — reject it so boot can retry
            // and we never treat a placeholder payload as a successful render.
            if (!payload || !payload.candles || !payload.candles.length) {
                return false;
            }
            var meta = payload.meta || {};
            var previous = (state.payload || {}).meta || {};
            // A different symbol or bar size is a different series, so the old
            // viewport is meaningless against it — switching D→1H would
            // otherwise leave you zoomed onto a handful of bars. Toggling an
            // indicator is not, and must keep the user where they were.
            var isNewSeries = !state.payload
                || meta.ticker !== previous.ticker
                || meta.interval !== previous.interval;

            try {
                state.payload = payload;
                if (!ensureChart(payload)) { return false; }
                syncPanes(payload);
                syncSeries(payload);
                if (isNewSeries) { state.chart.timeScale().fitContent(); }
                updateLegend(null);
                updateBarCount(state.chart.timeScale().getVisibleRange());
                api.nudge();
                return true;
            } catch (err) {
                // A mid-apply throw (bad pane, missing series ctor) used to
                // leave a half-built chart and a stuck black frame. Tear down
                // so the next payload / boot retry starts clean.
                try { destroy(); } catch (e) { /* ignore */ }
                state.payload = null;
                if (typeof console !== 'undefined' && console.error) {
                    console.error('sfaChart.apply failed', err);
                }
                return false;
            }
        },

        /** Re-run apply() with the last good payload (post-reparent wake-up). */
        reapply: function () {
            if (!state.payload || !state.payload.candles || !state.payload.candles.length) {
                return false;
            }
            return api.apply(state.payload);
        },

        setChartType: function (type) {
            if (!type || type === state.chartType) { return; }
            state.chartType = type;
            if (state.payload) { api.apply(state.payload); }
        },

        setScaleMode: function (mode) {
            state.scaleMode = mode || 'normal';
            if (!state.chart) { return; }
            state.chart.priceScale('right').applyOptions({
                mode: enumValue('PriceScaleMode', state.scaleMode, PRICE_SCALE_MODE),
            });
        },

        setTheme: function (theme) {
            if (!state.chart || !theme) { return; }
            if (state.payload) { state.payload.theme = theme; }
            state.chart.applyOptions(chartOptions(theme, state.payload && state.payload.meta));
            if (state.payload) { syncSeries(state.payload); }
        },

        fitContent: function () {
            if (state.chart) { state.chart.timeScale().fitContent(); }
        },

        /** Scroll to a window without rebuilding — used by the Data tab. */
        setVisibleRange: function (from, to) {
            if (!state.chart || from == null || to == null) { return; }
            try { state.chart.timeScale().setVisibleRange({ from: from, to: to }); }
            catch (e) { state.chart.timeScale().fitContent(); }
        },

        screenshot: function (filename) {
            if (!state.chart) { return; }
            var canvas = state.chart.takeScreenshot();
            canvas.toBlob(function (blob) {
                var url = URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.href = url;
                a.download = filename || 'chart.png';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            });
        },

        isReady: function () { return !!state.chart; },

        /**
         * After a DOM reparent (e.g. Optimizer overlay hosts #chart-area-home),
         * autoSize may still think the canvas is 0×0. Force a resize once layout
         * has settled.
         */
        nudge: function () {
            if (!state.chart || !state.container) { return; }
            var run = function () {
                var w = state.container.clientWidth;
                var h = state.container.clientHeight;
                if (w > 0 && h > 0) {
                    try { state.chart.resize(w, h); } catch (e) { /* ignore */ }
                }
            };
            requestAnimationFrame(function () {
                requestAnimationFrame(run);
            });
        },

        _state: state,
    };

    window.sfaChart = api;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', requestFirstPayload);
    } else {
        requestFirstPayload();
    }
}());
