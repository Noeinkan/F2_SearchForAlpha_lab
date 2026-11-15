"""Check the browser payoff calculator against the four-leg example."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_four_leg_expiry_payoff_and_break_even():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed to evaluate the Flow browser calculator")
    asset = Path(__file__).resolve().parents[1] / "dash" / "assets" / "52-flow-strategy.js"
    script = r"""
const fs = require('fs'), vm = require('vm');
const window = {}, document = {readyState: 'loading', addEventListener() {}};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {window, document});
const legs = [
  {cp:'P',strike:50,ask:2.55,bid:2.55,multiplier:100,qty:5,side:'sell'},
  {cp:'C',strike:50,ask:2.40,bid:2.40,multiplier:100,qty:5,side:'sell'},
  {cp:'C',strike:55,ask:0.80,bid:0.80,multiplier:100,qty:5,side:'buy'},
  {cp:'P',strike:45,ask:0.85,bid:0.85,multiplier:100,qty:5,side:'buy'},
];
const result = window.sfaFlowStrategy.analyze(legs);
const call = window.sfaFlowStrategy.analyze([
  {cp:'C',strike:390,ask:10.15,bid:10,multiplier:100,qty:1,side:'buy'},
]);
const put = window.sfaFlowStrategy.analyze([
  {cp:'P',strike:390,ask:10.15,bid:10,multiplier:100,qty:1,side:'buy'},
]);
console.log(JSON.stringify({
  credit: result.netCredit, roots: result.roots,
  maxProfit: result.maxProfit, maxLoss: result.maxLoss,
  low: window.sfaFlowStrategy.payoff(legs, 40),
  center: window.sfaFlowStrategy.payoff(legs, 50),
  high: window.sfaFlowStrategy.payoff(legs, 60),
  callRoot: call.roots[0], callLoss: call.maxLoss, callUnlimited: call.maxProfit === Infinity,
  putRoot: put.roots[0], putLoss: put.maxLoss,
}));
"""
    completed = subprocess.run(
        [node, "-e", script, str(asset)], capture_output=True, text=True, check=True,
    )
    result = json.loads(completed.stdout)
    assert result == {
        "credit": 1650,
        "roots": [46.7, 53.3],
        "maxProfit": 1650,
        "maxLoss": -850,
        "low": -850,
        "center": 1650,
        "high": -850,
        "callRoot": 400.15,
        "callLoss": -1015,
        "callUnlimited": True,
        "putRoot": 379.85,
        "putLoss": -1015,
    }
