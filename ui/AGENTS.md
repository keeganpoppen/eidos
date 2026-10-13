# Workbench UI guidance

Read [root instructions](../AGENTS.md), [INTERACTION](../docs/vision/INTERACTION.md), and the selected [V1 scenario](../docs/roadmap/V1.md).

The product is not a generic dashboard or a thread list with a JSON pane. Build linked apertures around actual evidence, context, pending questions, diffs, and results. The UI is a projection of durable state, not a competing source of truth.

Preserve object identity and focus across layout changes, updates, and reload. Display original evidence versus interpretation, historical versus live state, and unknown outcomes explicitly. A renderer must not invent authority. An action needs a subject, precondition, scope, and receipt/error path.

Prioritize readable typography, keyboard behavior, noncontiguous source navigation, large histories, native artifact rendering, and stable scroll/focus. Restrained experimental aesthetics should improve bandwidth, not reduce accessibility. Do not add ornamental KPI cards to fill empty space.

Run `bun install`, `bun run check`, and `bun run build` from this directory. For presentation changes also inspect the rendered UI with representative sanitized data and preserve a screenshot or interaction record. Build success is not usability evidence. Coordinate shared API changes through the integrator.
