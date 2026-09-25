# Agent instructions

## Live documentation (livedocs)

Notes under `docs/vault/` are bound to the code they mention (names in backticks). A pre-commit gate blocks
any commit that changes code a note mentions until the note is reconciled: edit the note and commit
again (the commit stamps it), or if the note is still correct run
`livedocs stamp <note> --ack --reason "<why>"`, `git add -A`, and commit. New and edited notes are stamped
by the commit that contains them; nothing else to run. `livedocs affected` lists the notes your
uncommitted changes touch; `livedocs coverage` shows which claims are anchored.
Write notes in `docs/vault/` (see `docs/vault/Home.md` for the layout); commit them and they are stamped. Session logs go in `Sessions/` and are never checked.
