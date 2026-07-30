# SOP · Alert triage (M1.5 built-in)

When the user asks to triage alerts or prioritize noise:

1. **Cluster** similar alerts (same host, same signature, same timeframe).
2. **Rank** by: active exploitation signal > asset criticality > blast radius > novelty.
3. **Ask for missing context** only if it changes the top 3 (do not stall on nice-to-haves).
4. **Output** a short Markdown report:
   - Top findings (ordered)
   - Why each matters
   - Suggested next action (investigate / contain / suppress / need more data)
   - Explicit uncertainty

Constraints: prefer read-only investigation. Do not claim host changes unless the
user explicitly authorized operator actions (M2+ sandbox required for real tools).
