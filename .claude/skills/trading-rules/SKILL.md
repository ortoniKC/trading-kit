---
name: trading-rules
description: Conventions for rules, arbitration, and decision logging in this trading kit. Use when adding or changing a rule, an arbiter threshold, a segment, or a debate prompt.
---

# Trading rules conventions

Use this skill when editing rules.py, engine.py prompts, or review.py.

1. Each rule has an id, segment, side (bull or bear), name, and a pure test function over the observed fields.
2. A rule must only read fields the engine produces. Add the field in engine.py first, then the rule.
3. Bear rules in swing can only block. They never create a sell.
4. A new rule needs a backtest record (bt_wins, bt_trials) before it can drive a decision. Until then it is
   logged and scored but cannot trigger BUY-READY.
5. Thresholds (MIN_EDGE, MARGIN, min_trials) change only with out-of-sample evidence. Record the reason in the commit message.
6. Every new rule gets a unit test in tests/test_core.py that covers firing and not firing.
7. Prompts must cite field names and exact values. Claims that do not match the snapshot block the trade.
