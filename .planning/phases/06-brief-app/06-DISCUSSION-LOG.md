# Discussion Log — Phase 6: Brief app

**Gathered:** 2026-07-04
**Mode:** Default (interactive, no flags)

## Area 1: Serving approach

**Decision:** Render SAB on `GET /sab` request OR if previous render ≥24h old. Serve cached SAB if <24h.

| Question | Options presented | Selection |
|----------|------------------|-----------|
| Serving model | (a) FastAPI serving files via FileResponse, (b) stdlib asyncio server | (a) FastAPI with 24h staleness gate |

**Notes:** Replaced speculative `?window=24h` parameter with file-mtime staleness check.

## Area 2: Output file strategy

**Decision:** All four files — cluster.md, brief.md, list.md, bluf.md to `data/digests/`.

| Question | Options presented | Selection |
|----------|------------------|-----------|
| Output files | All four files / Brief+BLUF only / Brief+BLUF+list | All four files |

## Area 3: BLUF synthesis in event-driven path

**Decision:** BLUF generated only for CCIR/CNR sections with new items since last render. Previous BLUFs preserved.

| Question | Options presented | Selection |
|----------|------------------|-----------|
| BLUF strategy | Always run BLUF / BLUF optional toggle / BLUF only for new items | BLUF only for new items |

## Area 4: Window selection

**Decision:** Time window rendered incrementally. Each `verdict.ready` updates "last update" timestamp. First render after restart falls back to "since yesterday 16:00" (same as today's default).

| Question | Options presented | Selection |
|----------|------------------|-----------|
| Window model | Time window / Since last render / Time window rendered incrementally | Time window rendered incrementally |

## Deferred Ideas

- None — discussion stayed within phase scope.

---

*Phase: 06-brief-app*
*Discussion logged: 2026-07-04*
