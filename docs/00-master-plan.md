# Master Orchestrator Plan

## Purpose

This document is the high-level control plane for the Air Quality Intelligence System project. It coordinates multiple LLM agent instances working on different scopes, prevents duplication, and defines the order of operations.

---

## Project Overview

**Title:** Air Quality Intelligence System: Automated Data Warehouse and Pollution Risk Prediction Using OpenAQ Data

**Courses:** Advanced Data Warehouse Technologies + Advanced Database Management Systems (combined submission)

**Instructor:** István Vassányi, University of Pannonia, Spring 2026

**Repository:** `~/git/advanced-data-warehouse-and-database-management-systems-submission`

**Azure DevOps Board:** https://dev.azure.com/dop3bp/AirQualityIntelligence

**Deployment Target:** https://mw79on-demo.online (Oracle Cloud VM + Docker Compose)

---

## Agent Coordination Model

```
┌──────────────────────────────────────────────────────────┐
│                   MASTER ORCHESTRATOR                      │
│  (this plan — human or coordinating agent reads this)     │
└──────────────┬───────────────────────────┬───────────────┘
               │                           │
    ┌──────────▼──────────┐     ┌──────────▼──────────┐
    │  EXPLORATION AGENT   │     │ IMPLEMENTATION AGENT │
    │  (reads 01-context)  │     │  (reads 02-impl)     │
    │  discovers & records │     │  executes work items  │
    └─────────────────────┘     └──────────────────────┘
```

### Rules for Agents

1. **Always read the Context Registry (01-context-registry.md) first** before doing any exploration or implementation.
2. **Always check the Implementation Plan (02-implementation-plan.md)** to know what work item you're executing.
3. **One agent works on one Issue at a time.** Mark it `In Progress` on the Azure DevOps board.
4. **Each work item is self-contained.** Its description + the context registry should be enough to execute without re-reading the entire project.
5. **After completing a work item,** update the board to `Done` and note any new context discovered in the context registry.
6. **If you discover a blocker or dependency issue,** update the board and stop. Don't proceed into another agent's scope.

---

## Execution Phases

### Phase 0: Foundation (Do First)
- [x] Project scaffolding & repo structure (Issue #50)
- [x] PostgreSQL setup & schema init (Issue #51)
- [x] Docker Compose local dev (Issue #54)

### Phase 1: Data Pipeline (Depends on Phase 0)
- [x] OpenAQ API client & ingestion worker (Issue #52)
- [x] Operational database tables (Issue #57)
- [x] Incremental load & scheduling (Issue #53)

### Phase 2A: DBMS Layer (Depends on Phase 1)
- [x] Threshold alert business process (Issue #58)
- [x] Triggers & loose coupling (Issue #59)
- [x] Transactions & error handling (Issue #60)
- [x] FastAPI backend (Issue #61)
- [ ] Streamlit operational GUI (Issue #62)
- [ ] Columnstore/indexing & partitioning (Issue #63)
- [ ] Backup & maintenance jobs (Issue #64)

### Phase 2B: Data Warehouse Layer (Depends on Phase 1)
- [ ] Star schema design & DW tables (Issue #65)
- [ ] ETL pipeline staging → DW (Issue #66)
- [ ] SCD2 implementation (Issue #67)
- [ ] Risk classification (Issue #68)
- [ ] PM2.5 prediction model (Issue #69)
- [ ] Dashboard (Issue #70)
- [ ] Automated DW refresh (Issue #71)

### Phase 3: Deployment (Depends on Phase 2A + 2B)
- [ ] Cloud deployment — Oracle Cloud VM (Issue #55)
- [ ] CI/CD pipeline — GitHub Actions (Issue #56)

### Phase 4: Documentation & Presentation (Can start in parallel with Phase 2)
- [ ] Architecture diagrams (Issue #76) — start early, refine as system develops
- [ ] DBMS course PDF (Issue #72)
- [ ] DW course PDF (Issue #73)
- [ ] DBMS presentation slides & demo script (Issue #74)
- [ ] DW presentation slides & demo script (Issue #75)

---

## Parallelism Opportunities

These groups can be worked on simultaneously:

| Parallel Track A | Parallel Track B | Parallel Track C |
|---|---|---|
| Phase 2A (DBMS layer) | Phase 2B (DW layer) | Phase 4 (docs, partial) |
| Issues #57–#64 | Issues #65–#71 | Issues #76 (arch diagram) |

Within Phase 2A, these can be parallelized:
- FastAPI (#61) and Streamlit GUI (#62) can be developed independently
- Triggers (#59) and Transactions (#60) are independent of each other
- Backup (#64) and Indexing (#63) are independent

Within Phase 2B, these can be parallelized:
- Star schema (#65) must come first
- Then ETL (#66), SCD2 (#67), Classification (#68) can be parallel
- Dashboard (#70) depends on having data in the DW

---

## Key Decisions & Constraints

| Decision | Choice | Rationale |
|---|---|---|
| Database engine | PostgreSQL | Open-source, Docker-friendly, supports OLTP + DW schemas in one deployable engine; see `01-context-registry.md` for alternatives considered |
| Frontend | Streamlit | Satisfies "GUI" requirement with minimal effort |
| Backend API | FastAPI | Clean REST API, auto Swagger docs for demo |
| ETL tool | Python scripts | More portable than SSIS, demonstrates the concept equally well |
| Dashboard | Streamlit (primary) + optional Power BI/Looker | Streamlit is self-hosted; Power BI can be added as bonus |
| ML | scikit-learn | Simple, well-known, sufficient for the scope |
| Deployment | Docker Compose on Oracle Cloud VM | Free tier, full control, impressive for demo |
| Reports/Slides | LaTeX (article + beamer) | Clean typesetting, version-controlled, consistent styling |
| Project management | Azure DevOps (Epics/Issues/Tasks) | Structured tracking for multi-agent coordination |

---

## Critical Path

```
Scaffolding → PostgreSQL → Ingestion → OLTP Tables → ETL → Star Schema → Dashboard → Deploy → Docs
     #50         #51          #52         #57        #66       #65         #70        #55    #72-76
```

This is the minimum path to a working end-to-end demo. Everything else adds depth and marks.

---

## How to Use This Plan

1. **Starting a new work session:** Read this plan, check the Azure DevOps board for current status, pick the next available item from the current phase.
2. **Handing off to an agent:** Give it this file path, the context registry path, and the specific Issue number/description.
3. **Checking progress:** Query the Azure DevOps board or read the Implementation Plan status markers.
4. **Adding new work:** Create an Issue on the board, add it to the appropriate phase here, update the implementation plan with details.
