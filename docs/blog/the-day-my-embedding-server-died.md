# My embedding server died and I didn't notice for two weeks

I built a small MCP server called [Codicil](https://github.com/colehellman/codicil) that
indexes docs in a repo and lets an AI coding assistant search them instead of guessing.
Runbooks, config notes, whatever I've written down about my homelab. It's just for me, one
repo, one user, nobody else touches it.

For months it ran against a real Ollama box doing embeddings with `nomic-embed-text`, so
every query was an actual semantic search over vectors. Then I decommissioned that box for
unrelated reasons and the embedding endpoint went dark.

I didn't notice for something like two weeks. Queries still came back with reasonable
answers so I just kept using it. Turns out it had fallen back to grepping the raw files the
whole time, and it never said a word about it.

I don't remember exactly what tipped me off at this point, just that at some point I went
looking and realized it had been running on keyword fallback for a while.

Honestly my first thought was that this is a little embarrassing. I'm the only person who
uses this thing, so I'm also the only monitoring it has, and I went two weeks without
checking. But then I actually looked at why it didn't just break, and that part I don't
think is embarrassing at all.

Most tools like this have one failure mode when the embedding service goes away: they stop
working. No embedding, no vector, no search. I didn't want that, so a bunch of the code is
just "what happens if this specific thing isn't there" handling, scattered around instead of
centralized:

- No embedding host reachable? Falls back to grepping files off disk directly.
- Index empty or never built? Same fallback.
- Reindex dies halfway through a file? New chunks get written before old ones are deleted, so
  a crash mid-run leaves you stale, not empty.
- Two processes hit the store at once? This one actually got me for real, not hypothetically.
  A long-running `serve` process and a one-off `codicil index` from a cron job raced each
  other and it wasn't pretty. There's an exclusive `fcntl.flock` on the store now
  (`fcntl.flock(fd, LOCK_EX | LOCK_NB)`), so the second process gets refused outright instead
  of getting to touch anything.

None of that is exotic, it's just annoying to write and easy to skip. I skipped some of it
the first time through, which is how the process-race thing happened.

Keyword search is worse than semantic search, for the record. It doesn't get synonyms, it
just counts overlapping words. If I ran both side by side on the same queries, semantic wins
most of the time. But it only wins when the embedding host is actually up, and mine wasn't,
for two weeks, and I didn't know.

There's also a dumber bug I found while doing all this that's worth mentioning because it's
the kind of thing that's obvious in hindsight: each embedding model gets its own Chroma
collection now (`docs_<sha256-of-model-name>[:12]`), because Chroma fixes a collection's
vector dimension the first time you write to it. Before that fix, switching embedding models
against the same collection would've just broken silently the next time you tried to write a
different-sized vector into it. I hadn't hit this one in practice, I just noticed it could
happen and fixed it before it did.

I've been putting off publishing this because I kept trying to make the ending land on some
bigger point about AI tooling and knowledge decay, and every version of that ending sounded
like something off a conference slide. So I'm just going to leave it here: the embedding
host died, I didn't notice, and the reason I didn't notice is the only part of this worth
writing down.

---

_Codicil's open source: [github.com/colehellman/codicil](https://github.com/colehellman/codicil)._
