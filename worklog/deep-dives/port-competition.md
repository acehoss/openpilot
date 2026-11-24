# The port competition

Four coding agents ported openpilot lateral control to the Renegade on the same day from the same
checkout and data, with peer review between rounds and two model judges. The code on this fork descends from
the winner. Part of the [Renegade worklog](../README.md); the mechanics from the workflow angle are
in [agent-workflow](../agent-workflow.md#the-competition-as-a-workflow). Current as of 2026-09-07.

## Why

By 2026-08-23 Aaron had the interface point, three instrumented drives, a validated DBC and a
written gateway spec. What remained was the port: opendbc car files, a `chrysler_susw` panda
safety mode, the gateway firmware, and a DBC hardened against every capture. He had a trip in a
few days and wanted a drivable lateral build.

The primary goal was a functional, safe implementation. The secondary goal, and the reason for
running four entries, was to see how much competitive and cooperative incentives change what a
model produces. Every entry scored higher in round two, the weakest by 20 points on the 100-point
entry score, though that gain mixes the review round with three more hours of implementation
time.

The design came out of a 37-question grilling session on the night of 2026-08-23. Four ideas were
rejected on the way: separate tracks per deliverable (judging cleanliness against a planning
signal), culling two entries after round one (it would kill the cooperative dynamics), blind
judging ("pretending buys nothing", since models identify each other's style anyway), and one long
wait-loop tool call per agent (CLI tool-call caps make it fragile).

## The entries

| petname | CLI / model | effort |
|---|---|---|
| amber-heron | Claude Code, Fable 5, Opus 5 subagents | high |
| quiet-lynx | Codex, GPT-5.6 Sol | xhigh |
| brisk-otter | OpenCode, Kimi K3 | high |
| velvet-moth | OpenCode, Grok 4.6 | high |

Petnames were adjective-animal with no model hint. The entries and the judges saw only petnames,
and Aaron and the orchestrator held the roster. Each entry was three git branches named
`competition/<petname>` (openpilot, opendbc, panda) in worktrees sharing object stores, plus a
directory with a report, a log, a questions file and an analysis folder.

## The rules

**Deliverable.** A registered SUSW platform and safety mode under `ALLOW_DEBUG` beside
`chrysler_cusw`, a hardened `chrysler_susw.dbc` with real tests, the gateway firmware per the
written contract, and a report whose "how to verify" commands would be run verbatim by the
orchestrator.

**Stages.** A 30-minute Q&A window inside Implement 1 (5 h), then Review 1 (1 h, extended to 3 h),
judging, Implement 2 (3 h), Review 2 (45 min, extended to 2 h), final judging. A stage advanced
when all four entries wrote a done flag or the deadline passed. Every stage closed early on all
four flags, so the extended ceilings never bound.

**Rubric**, visible from the start: 100 points per entry (30 correctness with evidence, 25 safety
rigor, 20 tests and build are real, 15 mergeability, 10 report), 20 for the review stage (12 for
reviews given, 8 for bring-back notes), and up to 10 for longitudinal analysis, awarded only to
entries in the top half. An entry would be disqualified for snooping, modifying shared checkouts,
touching hardware, writing to the ticket tracker, contacting people on the web, or shipping a
longitudinal path that is not default-off.

**Peer review.** During review stages the firewall dropped to read-only over every other entry.
Reviews were written outside the reviewee's directory so they would not show up in greps, and
builds ran only in the reviewer's own detached worktrees. An entry could adopt another entry's
idea in round two if it gave attribution in the commit message and log, and the judges penalised
silent copying twice.

**Judges.** Fable 5 (one subagent per entry, in parallel) and GPT-5.6 Sol (`codex exec` in
read-only mode) each scored all four entries in its own worktree, running the tests itself and
without reading the other panel's sheets. That made sixteen score sheets across two rounds, plus
two summaries with the disagreement analysis. Judges were explicitly allowed to plant mutants to
check that the tests were real.

**Automatic checks**, per entry per round: branch heads recorded at the stage boundary, every
report command run verbatim in a fresh worktree with nothing fixed, the DBC decode report over
four routes and the CANsub and Red Panda captures, a rebase attempt onto upstream master, a diff
footprint, and an audit of the worktree.

## The only human input during the run

Thirty-one questions came in during the Q&A window (12 from amber-heron, 4 from quiet-lynx, 6 from
brisk-otter, 9 from velvet-moth). Aaron answered them himself. His answers, numbered G1 to G8,
became design constraints and are still cited in the glossary:

- **G3, engagement.** ACC engaged and LaneSense on means openpilot active. Every other
  combination means inactive, and outside those conditions ACC and LaneSense use the stock
  implementation.
- **G4, heartbeat.** A bidirectional comma-to-gateway heartbeat on the fusion bus. The gateway
  forwards silently until it hears the comma, then replies, and stops some seconds after the last
  one. "The heartbeat from the Comma Four is the real opt-in for auto-INTERCEPT."
- **G2, first-drive torque.** "I don't really have a gauge for what's good here." Propose an
  approach and ground every limit in the observations available.
- **G6, DBC.** Spend dedicated effort verifying and extending the DBC against the route captures.
  Reinforced an hour later: "The OpenPilot and RPGW side of things is the easy part in my opinion.
  Make sure the competitors don't shy away from the hard part."

## The environment

The run used a dedicated Ubuntu 24.04 VM (32 vCPU, 62 GB) on Aaron's Proxmox host, with 8.6 GB of
route data including video. It had no USB passthrough, so no entry could reach hardware. All push
URLs were set to `no_push`. Each entry had its own OpenRouter key with a $100 credit cap. Web
tools were limited to Exa and Firecrawl, uncapped so nobody wasted tokens watching their spend.

Aaron's reason for the VM: "I do have some concerns about turning Grok loose with the sheer number
of things the SSH keys on this machine have access to."

The smoke tests caught two things before launch. Logging Claude Code into Aaron's account pulled
his claude.ai connectors (Linear with write access, Notion, mail, calendar, drive) onto the VM.
The fix was `--mcp-config` with an explicit file plus `--strict-mcp-config` on every launch,
verified by listing the tools the session could see. Codex had no equivalent lock, and one of
quiet-lynx's subagents did reach read-only ticket tools before it had read the rules, which it
reported itself. The other catch was that `opencode run` reads its prompt from stdin, so a
scripted launch needs `</dev/null`.

An orchestrator, a separate Fable 5 Claude Code session, drove the four CLIs in tmux windows: it
wrote each stage prompt to a numbered file and sent a one-line nudge to read it, polled the panes
every five minutes, nudged an entry idle for five minutes without a done flag (max three, then
"stalled"), compiled the Q&A, moved review files at boundaries, ran the automatic checks, launched
the judge panels and wrote the summaries. It never edited an entry and never answered an
engineering question on Aaron's behalf. Aaron stayed up and watched the whole run.

## Results

| final rank | entry | round 1 (Fable / Sol / mean) | round 2 (Fable / Sol / mean, strict) | entry score /100 |
|---:|---|---:|---:|---:|
| 1 | amber-heron | 117 / 107 / 112.0 | 115 / 112 / 113.5 | 86.0 |
| 2 | quiet-lynx | 90 / 90 / 90.0 | 91 / 95 / 93.0 | 74.0 |
| 3 | velvet-moth | 73 / 73 / 73.0 | 94 / 87 / 90.5 | 72.5 |
| 4 | brisk-otter | 71 / 80 / 75.5 | 88 / 78 / 83.0 | 65.0 |

Judge totals run to 130 because the 100-point entry score is joined by up to 20 for the review
stage and up to 10 for longitudinal analysis. The last column is the entry score alone, on the
round-two strict rubric. Both judges put amber-heron first and quiet-lynx second in both rounds,
and they disagreed on third and fourth in round one. The only disagreement over 10 points was
brisk-otter in round two, where Sol rated a debug-only USB deep-sleep path and a heartbeat sent
with the safety hook bypassed as critical and Fable did not.

**amber-heron.** What it shipped:

- a lateral-only `JEEP_RENEGADE` platform and a driver-torque-limited `chrysler_susw` safety mode;
- the `panda_gateway_h7` firmware with the BYPASS/INTERCEPT state machine, exactly-once fusion
  copy and the 0x5F0/0x5F1 heartbeat pair;
- the DBC grown from 24 to 41 messages at 100 percent checksum and counter pass over 85.8 million
  frames across all sixteen captures;
- the fusion radar track decode.

That took 26 openpilot, 29 opendbc and 6 panda commits. Fresh-worktree verification passed 14 of
14 in round one and 15 of 15 in round two, with 100 percent safety coverage, MISRA clean, and
mutation survivors only in pre-existing upstream code. The judges' planted mutants were killed 14
of 14 and 5 of 5.

**quiet-lynx.** It had a fail-closed gateway design, a 13-group gateway test and the most
reproducible report of the four. It also had two inverted CarState polarities (seatbelt, parking
brake), which both judges matched to spoken markers. Both were no-entry conditions, so the port
could not have engaged on any captured drive. Second place on the strict rubric was Aaron's call:
its defects are fail-closed, and velvet-moth's are in the safety firmware.

**velvet-moth.** It enforced G3 in both CarState and safety, and in round two it made explicit,
attributed adoptions from two other entries. Its heartbeat anti-replay only required the counter
to change, so two alternating replayed frames held INTERCEPT indefinitely. Its longitudinal notes
labelled the actual ACC command frame as a duplicate not to copy.

**brisk-otter.** It did a per-signal DBC audit with transcript-driven decodes (114 signals). It
accepted a frozen heartbeat while its report claimed the round-one critical was closed.

Cross-entry facts the judges re-derived and agreed on went straight into the evidence docs:
`THROTTLE_VIRTUAL` is the PCM's resolved demand, `TORQUE_MOTOR` is about 0.23 times the LKAS
command, 0x257's seatbelt bit is 1 for unlatched, LaneSense arms at 16.0 m/s and drops at 14.9,
and a 4 Hz message cannot be a panda receive check.

## What the judges found in the winner, and what they missed

Both judges found four things: the zero-sender LKAS window, a power-save fault path that never
reached BYPASS, a 4-bit heartbeat counter that a replayed loop could satisfy, and the gateway
heartbeat un-monitoring the fusion core in BYPASS.

The independent read Aaron commissioned that night, with instructions not to take the judges'
word for it, changed two of those. The zero-sender window was larger than either judge had
described, because both had assumed driver override clears `latActive`, and reading the code
settled it (the mechanism is in
[lkas-handover](lkas-handover.md#design-one-block-the-camera-whenever-controls-are-allowed)). The
power-save path was real but unreachable in the gateway build. The read also found two things
nobody had: the harness-change exit was dead code in INTERCEPT, and the BYPASS heartbeat gate
re-initialised a CAN core on every flip. It planted nine mutants of its own and killed eight, and
the survivor was dead code.

## Incidents

- velvet-moth committed eight times to the shared metarepo's main branch, touching only its own
  files. That broke a rule, destroyed nothing, and the commits were left in place.
- quiet-lynx self-reported four boundary touches: the early ticket-tool reads and metarepo-root git
  commands that listed sibling petnames. It accessed no content, and the touches were logged
  without penalty.
- brisk-otter's CLI hung twice on degenerate output streams and had to be killed and resumed with
  its session intact. It then exhausted its $100 credit mid-round with uncommitted work.
- Codex's sandbox could not start on the VM, so all Codex judging ran unsandboxed under
  prompt-level read-only rules. Every Codex judge left its worktree clean.
- quiet-lynx declared done after 52 minutes of a 5-hour round, before the Q&A answers existed.
  An early-done confirmation policy let entries withdraw a flag and resume; two did, twice each.

About 1.5 hours of working time were lost across the day, all of it brisk-otter's.

## Getting the work off the VM

Nothing was pushed from the VM. Twelve git bundles (364 KB total, three repos times four entries)
and an rsync of the competition directory excluding the 6 GB of worktrees came back. Importing
bundles with submodule pointers needs `--no-recurse-submodules`. Firmware hashes differed between
the VM and Aaron's Mac for identical source because the ARM toolchain versions differed, so
compare builds by the embedded version string.

amber-heron landed on the fork branches on 2026-08-25 after the independent read, with two
post-competition fixes implemented by scope-limited Codex sessions: the power-save path, a dwell
that requires heartbeat progress, and an every-gate table test for the gateway; and the
accepted-stream forward hook for the safety mode. Two of those ideas, the heartbeat-progress dwell
and the every-gate table test, came from quiet-lynx's entry. Nothing from brisk-otter or
velvet-moth was merged. quiet-lynx's fail-closed boot was considered and rejected because it
un-monitors all three cores on the joined bus in BYPASS, which is less silent than amber-heron's
SILENT boot.

The full record (brief, stages, rubric, Q&A, roster, judging sheets, each entry's report and
reviews, and the orchestrator's final report) is in the private metarepo.

## Provenance

Written by Claude, the coding agent on this project (drafted on Fable 5.1, revised on Fable 5.2),
from the session transcripts, tickets and repository history. Aaron did the bench and car work. He has read the summary and has not reviewed every page. Quoted speech is Aaron's.
