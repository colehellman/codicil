# Codicil

**Give your AI coding assistant durable memory of your engineering knowledge.**

> *A codicil is a binding addition to a will: knowledge appended to a document that carries authority and outlives the moment it was written.*
> Codicil does the same for your codebase. It turns the docs, ADRs, and runbooks you already keep into persistent memory your AI assistant can search — and it keeps working when the fancy parts break.

> **Status: early / pre-release.** The core — semantic search, graceful degradation, and automatic indexing — runs in production today. Packaging and a public release are in progress. Expect rough edges and breaking changes.

---

## Why this exists

AI coding assistants are only as good as the context they're handed. But the knowledge that actually explains your systems — *why* the retry lives there, which host really runs the cron, what broke last time and how it was fixed — is scattered across docs, ADRs, incident notes, runbooks, and people's heads. So every session starts cold. The assistant re-derives what your team already learned, guesses at conventions it can't see, and confidently gets your architecture wrong.

Every engineer using an AI assistant eventually hits the same wall: *"I already documented this. Why doesn't my assistant know it?"*

**Codicil exists so that engineering knowledge compounds instead of disappearing** — so the next session, and the next engineer, start from everything the last one already learned.

I originally built Codicil because I was tired of re-explaining my own infrastructure to AI assistants every time I started a new session. The more I documented, the more obvious it became that documentation isn't the problem — durable memory is.

### The story that explains the design

Codicil was extracted from a real system that had run it in production for months, indexing every config, runbook, and architecture doc so an AI assistant could reason about the infrastructure.

Then the embedding server was retired.

**Nothing broke.** Queries quietly fell back to keyword search and the tool kept answering — for *weeks* — before anyone noticed the semantic layer was even gone.

That's not a lucky accident. It's the entire design philosophy, made concrete: a memory tool that stops working the moment its infrastructure hiccups isn't memory you can rely on. Everything below follows from that one idea.

### What it looks like

```text
  In Claude Code ───────────────────────────────────────────

  › how is the reverse proxy configured?

    codicil · searching docs…
    ▸ 4 relevant passages

    reverse-proxy/nginx.md      (score 0.88)
        server { listen 443 ssl; proxy_pass … }
    network/ingress.md          (score 0.81)
        …upstream points at the gateway host…

  → Claude answers from your actual config — not a guess.
```

*Illustrative — the Claude Code chat UI isn't something a terminal recording can reproduce.*

![Codicil answering a real query in a terminal, via keyword fallback](docs/demo/demo.gif)

*The GIF above is real, unedited output — the same `query_docs` function called directly in a
terminal instead of over MCP. No local embedding host was running when this was recorded, so
it's answering via keyword fallback, not semantic search — a live demonstration of the
degrade-don't-fail behavior this project is actually about.*

## What it is

A small [Model Context Protocol](https://modelcontextprotocol.io) server that indexes a repository's documentation and exposes it as a search tool to any MCP-compatible assistant (built and tested against **Claude Code**). Point it at a repo, and your assistant can ask *"how is the reverse proxy configured?"* or *"what's the runbook when the scanner hangs?"* and get back the passages that matter — not whole files, just the relevant chunks, at a fraction of the token cost of opening everything.

Codicil isn't really about search. It's about ensuring engineering knowledge compounds instead of disappearing. Search is simply how your AI assistant reaches that memory.

## What makes it different

The "give agents memory" space is crowded. Codicil deliberately occupies the corner most of it skips:

- **Doc-native.** It reads the markdown, YAML, and shell docs already in your repo. There is no separate knowledge store to curate or keep in sync — your version-controlled docs *are* the memory.
- **Zero-infra.** A local index and optional local embeddings. No cloud account, no managed vector database, no API key required to get started.
- **Reliability-first.** This is the whole point. If the embedding host is unreachable, Codicil **degrades to keyword search over your files instead of failing.** An index that can't answer semantically is not a dead end — it falls back to grep.
- **Yours.** Plain files, a local index, knowledge you can read, edit, and diff in git. No lock-in, nothing leaves your machine unless you choose an external embedder.

## How it works

```
Your repo's docs                Codicil                    Your assistant
─────────────────             ───────────                 ───────────────
markdown · ADRs                                            "how does X work?"
runbooks · configs   ──────►  chunk + index   ──MCP──►     relevant passages,
architecture notes            + semantic search           scoped and ranked
                              (grep fallback)
```

1. **Index** — Codicil walks your repo, chunks docs along their structure (markdown headings), and stores embeddings in a local index. Re-indexing is incremental: only changed files are touched.
2. **Search** — Your assistant calls a search tool over MCP. Codicil embeds the query, returns the closest passages, and drops anything below a relevance threshold rather than padding the answer with noise.
3. **Degrade** — If no embedding backend is reachable, the same query is answered by keyword search read straight off disk. Same tool, same call, no configuration change, no failure.
4. **Stay fresh** — Optional git hooks re-index on commit and on doc edits, so the index tracks reality without you thinking about it.

## Reliability by Design

Most tools *claim* reliability. Here are the specific decisions that implement it — each one is a deliberate choice in the code, not a slogan:

- **Graceful degradation.** Every dependency has a fallback that still returns a useful answer. No embedding host? Keyword search off disk. Empty index? Same. The tool has no single point of "returns nothing."
- **Atomic-swap reindexing.** New content is embedded *before* the old content is removed. A failed or interrupted re-index can never leave you with *less* memory than you started with — the worst case is stale, never empty.
- **Incremental indexing.** Re-indexing compares file modification times and touches only what changed. A no-op pass is a cheap stat sweep, so keeping the index fresh is nearly free.
- **Concurrent-safe writes.** Index access is serialized so a live query never races a re-index, and only one process is ever allowed to own the store — the failure modes that corrupt embedded databases are structurally excluded, not hoped against.

## Design principles

These aren't aspirational — they're why the code is shaped the way it is:

- **Degrade, don't fail.** Every dependency has a fallback that still returns a useful answer.
- **The docs are the source of truth.** Codicil never becomes a second copy you have to reconcile. Knowledge compounds instead of disappearing after every incident.
- **Own your data.** Local by default; plain files; nothing you can't inspect.
- **Never lose what you already had.** Indexing embeds new content *before* it removes the old — a failed re-index can't empty your memory.

## Roadmap

Today Codicil is intentionally small: **single repository, single user, file-based retrieval.** That's the honest scope, and it's enough to be useful. Directions being explored — pulled by real use, not pushed by ambition:

- Pluggable embedding backends (local Ollama today; any OpenAI-compatible endpoint next).
- Relationship awareness between documents (what depends on what).
- First-class *incident* and *decision* memory — "what broke last time, and what did we do?"
- Cross-repository knowledge for multi-service setups.

Long term, Codicil aims to grow from document search into **durable engineering memory** — preserving decisions, incidents, and operational knowledge across the software lifecycle so it compounds instead of evaporating. The bet: the version of engineering memory that wins is the reliable, own-your-data one — and that's the version worth building.

## Lessons learned

Building Codicil clarified something about engineering knowledge: it decays in predictable ways. Documentation goes stale. Tribal knowledge walks out the door when people leave. Embedding infrastructure gets retired. Assistants hallucinate the moment context runs thin.

Software engineering is full of systems that fail eventually. The goal isn't to eliminate failure — it's to design systems that continue providing value when failure inevitably happens. Every significant decision in Codicil favors graceful degradation over peak retrieval quality, local ownership over managed convenience, and preserving what you already have over chasing the perfect answer. When those goals conflict, reliability wins.

That trade — accepting that the sophisticated path will sometimes fail, and making sure the simple path still works — is the throughline. It's why the embedding server could die without anyone noticing.

## Status & scope

Pre-release and evolving. The core runs; the packaging, docs, and public polish are the work in progress. Use it, break it, tell me what's missing.

## License

Released under the [MIT License](LICENSE).
