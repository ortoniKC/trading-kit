---
description: Analyze one NSE stock for intraday or swing
argument-hint: SYMBOL intraday|swing
---
Run `./run.sh analyze $ARGUMENTS` from the project root.
Show the output as returned. Do not add forecasts, targets, or probabilities of future price moves.
If the output says WAIT, explain the reason it gives. If it says a stop was logged, say that the stop is a risk limit.
If the command reports no valid Kite login, tell the user to run `./setup.sh login`.
