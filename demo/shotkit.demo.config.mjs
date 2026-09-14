/**
 * screenshot-kit config for the PUBLIC DEMO (the landing card's four frames).
 *
 * Run against the live demo:
 *   node C:/Personal_utilities/screenshot-kit/shotkit.mjs --config demo/shotkit.demo.config.mjs --out .shots/demo
 * or a local one (DEMO_MODE=true DEMO_PORT=8071 python -m demo.server):
 *   SHOTKIT_BASE=http://127.0.0.1:8071 node ... --config demo/shotkit.demo.config.mjs
 *
 * The frames are shot at 1440x900 @2x and resized to the landing page's
 * 1200x750 slot. Differences from ./shotkit.config.mjs (the local workspace):
 *
 * - No server block: the demo is already running somewhere.
 * - The demo banner is dismissed first (it is per browser session and sits
 *   over the chart); the header badge "DEMO · DATA <date>" stays in every
 *   frame, which is the point.
 * - Nothing waits on Yahoo: the snapshot loads in about a second.
 */

const BASE = process.env.SHOTKIT_BASE || 'https://alpha.demos.noeinsolutions.com';
const TICKER = 'TSLA';
const DEMO_HOST = new URL(BASE).hostname;

async function park(page) {
  await page.mouse.move(2, 2);
  await page.waitForTimeout(400);
}

/** The banner is plain HTML with a sessionStorage flag; close it like a visitor would. */
async function dismissBanner(page) {
  await page.evaluate(() => {
    const btn = document.getElementById('sfa-demo-banner-close');
    if (btn) btn.click();
  });
}

/** Click the hidden boot button until Lightweight Charts has a canvas. */
async function bootChart(page) {
  await page.waitForSelector('#chart-boot-btn', { state: 'attached', timeout: 90000 });
  await page.evaluate(() => {
    const btn = document.getElementById('chart-boot-btn');
    if (btn) btn.click();
  });
  await page.waitForSelector('canvas', { timeout: 120000 });
  await page.waitForTimeout(1500);
}

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
  outDir: '.shots/demo',
  viewport: { width: 1440, height: 900 },
  colorScheme: 'dark',
  settleMs: 1500,
  allowHosts: [DEMO_HOST, 'fonts.googleapis.com', 'fonts.gstatic.com'],

  async setup(page) {
    await page.goto(`${BASE}/ticker/${TICKER}`, { waitUntil: 'load', timeout: 120000 });
    await dismissBanner(page);
    await bootChart(page);
  },

  shots: [
    {
      name: 'f2-search-for-alpha',
      path: `/ticker/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 180000,
      waitFor: '#backtest-results',
      shows: 'a finished BB Breakout backtest on the frozen TSLA tape: entry/exit markers on the chart, portfolio, return, Sharpe and drawdown cards',
      async prepare(page) {
        await dismissBanner(page);
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
          { timeout: 120000 },
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
      name: 'f2-search-for-alpha-terminal',
      path: `/ticker/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 180000,
      waitFor: '#chart-frame canvas',
      settleMs: 2000,
      shows: 'the terminal: TSLA daily candles with Bollinger Bands plus volume, RSI, CCI and MACD panes, indicator rail left, strategy panel right',
      async prepare(page) {
        await dismissBanner(page);
        await bootChart(page);
        await zoomLastBars(page, 320);
        await park(page);
      },
    },

    {
      name: 'f2-search-for-alpha-optimizer',
      path: `/optimize/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 240000,
      waitFor: '#optimization-results tbody tr',
      settleMs: 2000,
      shows: 'the signal-combination optimiser after a capped search: ranked leaderboard of buy/sell stacks with return, Sharpe and drawdown',
      async prepare(page) {
        await dismissBanner(page);
        await bootChart(page);
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
        await page
          .waitForFunction(
            () => {
              const el = document.getElementById('optimization-progress');
              return el && /Completed/i.test(el.innerText || '');
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
      name: 'f2-search-for-alpha-fundamentals',
      path: `/fundamentals/${TICKER}`,
      waitUntil: 'load',
      timeoutMs: 180000,
      waitFor: '#fundamentals-content table tbody tr',
      settleMs: 2500,
      shows: 'the fundamentals workspace on the frozen snapshot: Big Five quality table across eleven fiscal years with growth charts',
      async prepare(page) {
        await dismissBanner(page);
        await page
          .waitForFunction(
            () => {
              const el = document.querySelector('.sfa-fundamentals-hero-value');
              return el && el.innerText.includes('$');
            },
            null,
            { timeout: 60000 },
          )
          .catch(() => {});
        await park(page);
      },
    },
  ],
};
