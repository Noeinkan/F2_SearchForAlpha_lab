Run the pytest test suite and report results.

Usage: /run-tests [optional: specific test file or -k filter]

Examples:
- /run-tests
- /run-tests lib/tests/test_strategy.py
- /run-tests -k "test_backtest"

Steps to follow:
1. Run `python -m pytest lib/tests/ -v $ARGS` (pass any arguments from the command).
2. Parse the output:
   - List any FAILED tests with their error messages.
   - List any tests that were SKIPPED and why.
   - Show a summary: X passed, Y failed, Z skipped.
3. If failures exist:
   - Read the failing test file to understand what it tests.
   - Read the relevant source file.
   - Diagnose the root cause.
   - Propose a fix (ask before applying unless the fix is trivial).
4. If all pass, confirm success and show coverage summary if available.
