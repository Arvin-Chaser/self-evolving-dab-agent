# G13.1 convergent Data Agent

G13.1 keeps G13's task-time requirement decomposition and evidence-driven tool
selection, but adds the convergence behavior missing in the three-task pilot.
It remains a prompt-policy experiment on the ordinary DAB database/Python action
space; it introduces no carrier, ledger, sidecar, helper, or Graph interface.

The added controls are:

- necessary versus optional requirements;
- explicit evidence-sufficiency conditions;
- at most two acquisition attempts per requirement;
- normally at most three Python calls;
- a target of completing acquisition within 12 of 20 model turns;
- an irreversible synthesis phase with at most one final verification action;
- explicit permission to return a bounded answer with unresolved limitations.

Entry point:

```powershell
python -m experiments.run_dab_tool_agent_g0131_convergent <normal run arguments>
```

The first evaluation reuses the same three tasks and controls as the G13
intent-first pilot. It is exploratory and must not mutate the formal G13 Graph.
