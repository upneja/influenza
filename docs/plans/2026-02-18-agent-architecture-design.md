# FluSight Edge: Agent Architecture Design

**Date:** 2026-02-18
**Status:** Approved

## Approach
Stream-Based Parallel Agents with scaffold-first strategy. One master Claude Code session (META) coordinates 10 subagents across 5 streams.

## Agent Roster

### STREAM 1: BUILD (4 agents, after scaffold)
- **BUILD-1: Delphi Pipeline** — `delphi_epidata.py`: Connect to Delphi API, pull versioned FluSurv-NET data, store revision history
- **BUILD-2: Backfill Model** — `backfill.py`: Analyze revision patterns, predict final rate from preliminary
- **BUILD-3: Wastewater Pipeline** — `wastewater.py`: Pull WastewaterSCAN data, filter to FluSurv-NET catchments
- **BUILD-4: Polymarket Scraper** — Scrape current flu market brackets, prices, volume

### STREAM 2: RESEARCH (3 agents, immediate)
- **RESEARCH-1: API Validation** — Test all API endpoints from PRD, document what works
- **RESEARCH-2: Polymarket Analysis** — Market mechanics, CLOB API docs, py-clob-client usage
- **RESEARCH-3: Historical Data** — What backtesting data exists across seasons

### STREAM 3: MATH (1 agent, immediate)
- **MATH-1: Model Design** — Elastic net spec, bracket probability conversion, Kelly sizing, Brier methodology

### STREAM 4: VETTING (1 agent, immediate)
- **VET-1: Gemini Prompts** — 3 research briefs for Gemini Deep Research

### STREAM 5: REVIEW (1 agent, on BUILD output)
- **REVIEW-1: Code Review** — Reviews BUILD stream code for quality and correctness

### META (main session)
- Scaffold project, launch agents, monitor, relay context, integrate, code review

## Execution Sequence
1. META creates scaffold (CLAUDE.md, schema.sql, config.py, directory structure)
2. Immediately launch: RESEARCH-1, RESEARCH-2, RESEARCH-3, MATH-1, VET-1
3. After scaffold: launch BUILD-1, BUILD-2, BUILD-3, BUILD-4
4. As BUILD agents complete: launch REVIEW-1

## Project Structure
Flat layout with CLAUDE.md files per directory for agent context. See root CLAUDE.md for full details.
