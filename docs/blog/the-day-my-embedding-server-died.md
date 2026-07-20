# The Day My Embedding Server Died and I Didn't Notice

I've got a little MCP server called [Codicil](https://github.com/colehellman/codicil) that
I use to search my own documentation: runbooks, config notes, the stuff I write down about
my homelab so I don't have to remember it. It's just for me. One repo, one user, no team,
nothing shared. An AI coding assistant can ask "how does X work" against my own docs instead
of guessing.

It started as something hacked into my actual homelab setup. I've got a small Proxmox +
Docker stack running at home, and for months this thing ran against a real Ollama instance
doing embeddings with `nomic-embed-text`. Every doc got turned into vectors, every query was
a real semantic search.

Then at some point I decommissioned that box. Wasn't even about this project, just general
cleanup. And the embedding endpoint went quiet.

Nothing broke, though. That's the part worth sitting with.

I kept using it. Queries kept coming back with useful answers. It was probably a couple of
weeks before I even noticed the semantic search wasn't happening anymore, and there was
never going to be anyone else to notice it first. I'm the only user this thing has. It had
quietly fallen back to plain keyword matching over the same files, and the only reason I
found out was that I went looking, not because anything alerted me.

## I should probably be embarrassed about that

My first reaction was "how did I not notice my own tool lost half its brain for two weeks."
But that's not really a surprising failure of monitoring: I'm both the only user and the
only person who'd ever check. The more interesting part, to me, is that it didn't matter
that I hadn't checked.

Most tools like this have exactly one failure mode when the embedding service disappears:
they just stop working. No embeddings, no search, maybe a stack trace if you're unlucky,
right when you actually needed the answer.

I'd specifically tried to avoid that when I built this. Not with some elaborate resilience
framework, just a handful of "okay, what happens if this specific thing isn't there"
decisions scattered through the code. No embedding host? Fall back to grepping the files
directly. Index hasn't been built yet? Same fallback, still returns something instead of
nothing. Reindex dies halfway through? New chunks get written before the old ones are
deleted, so worst case you're stale, not empty.

The one that actually got me, though (not in theory, for real), was two processes touching
the index at the same time. A long-running server and a one-off reindex from a cron job,
say. I hadn't guarded against that for a while, and it's the kind of thing that only bites
you when it bites you. There's a lock on it now that just refuses the second process outright
instead of letting them race each other into a corrupted store.

None of this is clever. It's the boring kind of engineering that looks like overkill right up
until the exact day it isn't, and then it's the only reason the thing still works.

## The part that's easy to skip past

Keyword search is worse than semantic search. I don't think that's controversial: it
doesn't get synonyms, doesn't understand meaning, it's just counting overlapping words. Put
them side by side and semantic search wins basically every time.

But "better when everything's working" and "better" aren't the same claim, and I think that
distinction gets lost a lot. A search feature that's great until the one dependency it needs
goes missing, and then it's just broken. That's not actually a good feature, it's a demo
that only works in the demo. I'd rather have something a little worse on a good day that
doesn't fall over on a bad one.

That's basically the whole design philosophy here, if you can call it that: degrade instead
of failing outright. The atomic reindexing, the incremental updates by file timestamp, the
single-writer lock: it's all the same instinct applied in different places. Assume the fancy
path breaks eventually. Make sure there's a dumb path underneath it that still works.

## Why I'm even writing this down

Docs go stale because nobody updates them after whatever incident made them necessary in the
first place. People who actually know how something works leave, and the knowledge leaves
with them. And now there's a new version of that same problem: the infrastructure that makes
your docs *searchable* can quietly die too, and if nothing's built to handle that, you lose
the knowledge again, just more quietly than a deleted file.

I don't think the interesting version of "let an AI search your docs" is the one with the
best retrieval numbers on a good day. I think it's the one that's honest about what it's
actually doing on a bad one, instead of just going dark.

---

_Codicil's open source, if you want to look at how any of this actually works:
[github.com/colehellman/codicil](https://github.com/colehellman/codicil)._
