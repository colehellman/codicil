# The Day My Embedding Server Died and I Didn't Notice

_Draft — not yet published anywhere. Written for review before it goes out._

I run a small MCP server called [Codicil](https://github.com/colehellman/codicil) that
indexes a repo's docs — runbooks, ADRs, config, architecture notes — and hands the relevant
passages to an AI coding assistant on request. It's not a big system. It has one job:
answer "how does X work?" from what's already written down, instead of making the assistant
guess.

Codicil started life as a bespoke tool wired into my homelab — a self-hosted stack of
Proxmox, Docker, and a dozen other services I run at home — before I pulled it out into its
own package. For months, running inside that homelab, it worked against a real embedding
host — a local Ollama instance serving `nomic-embed-text` — turning every doc into vectors
and every query into a semantic search over them.

Then the embedding server was retired. A host got decommissioned in some unrelated cleanup,
and the endpoint just stopped answering.

**Nothing broke.**

Queries kept coming back. Answers kept being useful. For weeks, I didn't notice the semantic
layer was gone. Every question was quietly being answered by keyword search over the same
files instead, and the tool never said otherwise unless I went looking.

## Why that's the interesting part

The easy reaction is embarrassment: how did I not notice my "AI memory" tool lost its AI for
weeks? But the more I sat with it, the more I realized the silence was the design working
exactly as intended, not a gap in monitoring.

Most tools that depend on an external service have one failure mode when that service goes
away: they fail. A search tool that needs an embedding host to embed the query has no
fallback plan, so no host means no answer — or worse, a stack trace surfaced to a user who
just wanted to know how the reverse proxy is configured.

I'd built Codicil to refuse that outcome specifically. Every dependency has a fallback that
still returns something useful:

- **No embedding host reachable?** Fall back to keyword search, read straight off disk.
- **Index empty or not yet built?** Same fallback — there's no code path where the answer is
  just "nothing."
- **A re-index gets interrupted halfway?** New chunks are embedded *before* the old ones are
  deleted, so a crash mid-reindex leaves you with stale data, never empty data.
- **Two things try to touch the index at once, in the same process?** Serialized through a
  single lock — no corrupted-index-from-a-race failure mode to debug at 2am.
- **Two things try to touch the index at once, in *separate* processes** (a long-running
  server and a one-shot reindex from a cron job or hook)? That one actually bit me: it's the
  same failure mode described above, just at the process level instead of the thread level,
  and it wasn't guarded against for a while. A PID-file check now refuses the second process
  outright instead of letting it race the first into a crash.

None of these are exotic. They're the kind of decision that feels like overengineering right
up until the day the thing you depended on quietly stops existing — and then it's the only
reason the tool is still useful instead of dead.

## The trade nobody puts in the pitch deck

Here's the part that's easy to gloss over: keyword fallback is *worse* than semantic search.
It doesn't understand synonyms, it doesn't rank by meaning, it just counts word overlap. If
you'd shown me a side-by-side comparison of the two search qualities in isolation, semantic
search wins every time.

But "wins when it's working" isn't the same claim as "wins." A brilliant search feature that
goes dark the moment its infrastructure hiccups isn't a brilliant search feature — it's a
liability with good demo day. I'd rather have a tool that's slightly worse on its best day and
never worse than "still works" on its worst one.

That's the actual design principle underneath Codicil, stated plainly: **degrade, don't
fail.** Every other decision in the codebase — the atomic-swap reindexing, the incremental
mtime tracking, the single-writer lock — is the same idea applied to a different failure
mode. Assume the sophisticated path will break sometime. Make sure the simple path still
works when it does.

## The broader thing this taught me

Engineering knowledge decays in predictable ways. Docs go stale because nobody updates them
after the incident that made them necessary. Tribal knowledge leaves when the person who had
it does. And now, increasingly, the infrastructure that makes that knowledge *searchable* can
quietly disappear too — and if the tool sitting on top of it doesn't plan for that, the
knowledge disappears with it, just less visibly than a deleted file.

The version of "AI memory" worth building isn't the one with the best retrieval quality on a
good day. It's the one that's still telling you the truth on a bad one.

---

_Codicil is open source: [github.com/colehellman/codicil](https://github.com/colehellman/codicil)._
