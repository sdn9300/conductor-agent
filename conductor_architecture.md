# conductor_architecture.md

**Component:** Conductor — Component #6, Coordination Layer
**Status:** UNLOCKED — Mission Plan v1.5 §13 criterion satisfied
**Author:** Soumyadeep Nath
**Date:** 2026-08-25

---

## The Three Questions

### 1. What does Conductor do first when a job search is triggered?

Conductor is the execution layer of the system — the **hands**, where the Memory Module is the **brain**. On trigger, it coordinates the specialist agents in sequence: Harvester and Research Agent / Future Fit surface opportunities and market signal, AlignResume tailors the resume against a target role via the Groq API, Overture drafts and sends outreach, and Sentiment Classifier reads and labels whatever comes back — all of it written to the Memory Module as it happens.

### 2. In what order does it call AlignResume, Harvester, and Overture?

AlignResume tailors the resume first, Harvester collects the hiring-company list second, Overture cold-emails third — though the first two steps can trade places depending on whether a specific job description already exists to tailor against.

### 3. What does Conductor return to the user at the end?

Not a single verdict — a distribution. Every outreach lands somewhere on a spectrum: ghosted, rejected outright, rejected politely, put on hold, strung along, or approved. Conductor's real output is that these outcomes get captured and classified, run over run, so the system gets smarter about what "approved" tends to look like.

---

This file satisfies the unlock criterion in full. It is deliberately left in its original, hand-written form — the six companion documents below formalize it and resolve the one open question it surfaces (the AlignResume/Harvester ordering), addressed explicitly as ADR-1 in the Architecture Design document. Nothing in this file should be rewritten to look more polished after the fact; the roughness is the record of when this actually started.
