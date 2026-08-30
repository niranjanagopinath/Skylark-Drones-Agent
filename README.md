# Skylark BI Agent

A conversational **business-intelligence agent** over messy monday.com data
(sales **Deals** pipeline + **Work Orders** execution/finance). Ask founder-level
questions in plain English and get **auditable** answers with explicit
data-quality caveats.

> Built for the Skylark Drones Full-Stack Developer assignment.

**Status:** under active development. Full architecture, setup, and decision
documentation land in this README and `DECISION_LOG.md` as the build progresses.

## Core design principle

A hard wall between **AI reasoning** and **arithmetic**:

- The **LLM** interprets the question and narrates the answer.
- A **deterministic Python BI engine** computes every number — and is unit-tested,
  so any figure shown to a user can be independently reproduced.

More docs incoming.
