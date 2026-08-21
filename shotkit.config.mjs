/**
 * screenshot-kit config for SearchForAlpha Lab.
 *
 * Run:  node C:/Personal_utilities/screenshot-kit/shotkit.mjs --serve
 *
 * Two app-specific things the runner cannot guess:
 *
 * 1. The price chart is TradingView Lightweight Charts, not Plotly. Python only
 *    writes `chart-payload-store`; the client asks for the first payload by
 *    clicking the hidden `#chart-boot-btn` (see assets/10-sfa-chart.js). That
 *    glue gives up after ~6s, and the first payload build takes ~15s on a cold
 *    process, so every shot re-clicks the button itself and waits for a canvas.
 *    `setup()` does it once up front to warm the server-side enriched cache.
 * 2. `run_dashboard()` opens a real browser tab on boot. The server command
 *    below neuters `webbrowser` so a capture run does not hijack the desktop.
 */

const BASE = 'http://127.0.0.1:8060';
const TICKER = 'TSLA';

/** Park the cursor in a dead corner so no crosshair / tooltip is in frame. */
async function park(page) {
  await page.mouse.move(2, 2);
  await page.waitForTimeout(400);
}

/** Click the hidden boot button until Lightweight Charts has a canvas. */
async function bootChart(page) {
  await page.waitForSelector('#chart-boot-btn', { state: 'attached', timeout: 90000 });
  await page.evaluate(() => {
    const btn = document.getElementById('chart-boot-btn');
    if (btn) btn.click();
  });
  await page.waitForSelector('canvas', { timeout: 180000 });
  await page.waitForTimeout(1200);
}

/** MAX on TSLA is 16 years of bars — zoom in so candles read as candles. */
async function zoomLastBars(page, bars) {
  await page.evaluate((n) => {
    const st = window.sfaChart && window.sfaChart._state;
    if (!st || !st.chart || !st.payload || !st.payload.candles) return;
    const total = st.payload.candles.length;
    st.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, total - n), to: total + 3 });
  }, bars);
  await page.waitForTimeout(1000);
}

export default {
  baseUrl: BASE,
  outDir: '.shots',
  viewport: { width: 1440, height: 900 },
  colorScheme: 'dark',
  settleMs: 1500,

  server: {
    command:
      'python -c "import webbrowser; webbrowser.open_new = lambda *a, **k: True; webbrowser.open = lambda *a, **k: True; import main; main.main()"',
    env: { DASH_DEV: '0', DASH_RELOAD: '0', DASH_PORT: '8060' },
    readyUrl: BASE + '/',
    // Boot bootstraps a full TSLA session from Yahoo before it serves anything.
    timeoutMs: 300000,
  },

  async setup(page) {
    await page.goto(`${BASE}/ticker/${TICKER}`, { waitUntil: 'load', timeout: 180000 });
    await bootChart(page);
  },

  shots: [
    {
      name: '01-terminal',
      path: `/ticker/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 180000,
      waitFor: '#chart-frame canvas',
      settleMs: 2000,
      shows: 'the terminal: TSLA daily candles with Bollinger Bands plus volume, RSI, CCI and MACD panes, indicator rail left, strategy panel right',
      alt: 'Dark trading terminal showing TSLA candlesticks with Bollinger Bands and four indicator panes',
      async prepare(page) {
        await bootChart(page);
        await zoomLastBars(page, 320);
        await park(page);
      },
    },

    {
      name: '02-backtest',
      path: `/ticker/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 180000,
      waitFor: '#backtest-results',
      settleMs: 1500,
      shows: 'a finished backtest: BB Breakout buy/sell signals plotted as entry/exit markers on the chart, with portfolio value, return, Sharpe and drawdown cards',
      alt: 'Backtest result panel with return and Sharpe metrics beside a chart marked with entry and exit signals',
      async prepare(page) {
        await bootChart(page);
        await page.locator('div.buy-toggle input[value="BB_Breakout_Buy"]').click();
        await page.waitForTimeout(2500);
        await page.locator('div.sell-toggle input[value="BB_Breakout_Sell"]').click();
        await page.waitForTimeout(3000);
        await page.click('#run-backtest-btn');
        await page.waitForFunction(
          () => {
            const el = document.getElementById('backtest-results');
            return el && el.innerText.trim().length > 120;
          },
          null,
          { timeout: 180000 },
        );
        await page.waitForTimeout(1500);
        await zoomLastBars(page, 320);
        await page.evaluate(() => {
          const el = document.getElementById('backtest-results');
          if (el) el.scrollIntoView({ block: 'start' });
        });
        await page.waitForTimeout(800);
        await park(page);
      },
    },

    {
      name: '03-optimizer',
      path: `/optimize/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 240000,
      waitFor: '#optimization-results tbody tr',
      settleMs: 2000,
      shows: 'the signal-combination optimizer after a 100-combo grid search: ranked leaderboard of buy/sell stacks with score, return, Sharpe and drawdown',
      alt: 'Optimizer workspace with a ranked leaderboard of signal combinations',
      async prepare(page) {
        await bootChart(page);
        // The rail only populates its signal universe once the chart has data.
        await page.waitForFunction(
          () => {
            const el = document.getElementById('preview-combo-count');
            return el && parseInt(el.innerText, 10) > 0;
          },
          null,
          { timeout: 120000 },
        );
        await page.click('#run-optimization-btn');
        await page.waitForFunction(
          () => document.querySelectorAll('#optimization-results tbody tr').length > 3,
          null,
          { timeout: 240000 },
        );
        // Let the run finish so the shot is a leaderboard, not a progress bar.
        await page
          .waitForFunction(
            () => {
              const el = document.getElementById('optimization-progress');
              return el && !/Testing/i.test(el.innerText || '');
            },
            null,
            { timeout: 240000 },
          )
          .catch(() => {});
        await page.waitForTimeout(2500);
        await page.evaluate(() => {
          const el = document.getElementById('optimization-results');
          if (el) el.scrollIntoView({ block: 'start' });
        });
        await page.waitForTimeout(800);
        await park(page);
      },
    },

    {
      name: '04-fundamentals',
      path: `/fundamentals/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 240000,
      // Yahoo fetch + render takes ~20s cold; the table only exists once loaded.
      waitFor: '#fundamentals-content table tbody tr',
      settleMs: 2500,
      shows: 'the fundamentals workspace: the Big Five quality table (ROIC, equity/EPS/sales/FCF growth, debt) across 11 fiscal years with 10Y/5Y/1Y roll-ups and trend charts',
      alt: 'Fundamentals page showing a colour-coded Big Five metrics table and growth charts',
      async prepare(page) {
        await park(page);
      },
    },

    {
      name: '05-flow-scanner',
      path: `/flow/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 120000,
      waitFor: '.sfa-flow-ticker-card',
      settleMs: 2000,
      shows: 'the options flow scanner: unusual-activity score breakdown, call/put split, top strikes and the sentiment flags behind the call',
      alt: 'Options flow scanner card for TSLA with a bullish score breakdown and top strikes',
      async prepare(page) {
        await park(page);
      },
    },

    {
      name: '06-symbol-search',
      path: `/ticker/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 180000,
      waitFor: '.sfa-symsearch-row-body',
      settleMs: 1500,
      shows: 'the Ctrl+/ symbol search over the committed ~13k-row universe, matching on business category with live quotes, sector, exchange and starred watchlist',
      alt: 'Symbol search modal listing semiconductor companies with live prices and sectors',
      async prepare(page) {
        await bootChart(page);
        await page.keyboard.press('Control+Slash');
        await page.waitForSelector('#symbol-search-query', { state: 'visible', timeout: 30000 });
        await page.click('#symbol-search-query');
        await page.keyboard.type('semiconductor', { delay: 45 });
        await page.waitForTimeout(2500);
        await park(page);
      },
    },

    {
      name: '07-command-palette',
      path: `/ticker/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 180000,
      waitFor: '.sfa-palette-row',
      settleMs: 1500,
      shows: 'the Ctrl+K command palette: every terminal action (load data, run backtest, export CSV/PNG, navigate) with its keyboard shortcut',
      alt: 'Command palette overlay listing data and navigation commands with shortcuts',
      async prepare(page) {
        await bootChart(page);
        await page.keyboard.press('Control+k');
        await page.waitForTimeout(2000);
        await park(page);
      },
    },
  ],
};
