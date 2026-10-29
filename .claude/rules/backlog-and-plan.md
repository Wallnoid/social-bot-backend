# Backlog and plan files

- `docs/backlog.md` holds the current backlog (user stories). It is temporary: overwrite it whenever the backlog changes.
- `docs/plan.md` holds the plan for the story being worked on right now. It is temporary: overwrite it whenever we start another story or the plan changes.
- Neither file is history. Do not append, version or keep old copies.
- Never commit them: both are listed in `.gitignore`. Do not stage them or include them in a commit or PR, even when they are the only changes left.
- When you start working on a story, read `docs/backlog.md` for its context and dependencies (`Requires: #N`), then write `docs/plan.md` for that story only.
- Stories are created in the tracker (ClickUp) only after the user explicitly says yes and after the list to be created has been shown. Destination: space `social-bot`, list `project`.
