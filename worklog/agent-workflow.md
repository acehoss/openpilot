# How the agent workflow ran

> Written by Claude, the coding agent on this project (drafted on Fable 5.1, revised on Fable 5.2),
> from the session transcripts, tickets and repository history. Aaron did all bench and car work.
> He has read the summary and has not reviewed every page. "I" on this page is the agent; quoted speech is Aaron's.

Two of the three road faults on this project happened after every host-side check had passed:
3,283 safety tests at 100 percent line coverage, static analysis, a mutation run with every mutant
killed. The agents had implemented the designs correctly, and the checks confirmed that the code
matched the design. Both times the car rejected an assumption the design had made. This page
covers eight weeks of porting openpilot to a Jeep with coding agents doing most of the typing:
what they were held to, where they were wrong, and what caught it. The technical story is in
[porting-the-renegade](porting-the-renegade.md).

Some orientation for readers who are not automotive people. openpilot is open-source driver
assistance running on a comma four, a camera-and-compute box at the windshield. A panda is comma's
CAN interface board, and it runs a safety layer in C that can refuse any frame the Python side
asks it to send. CAN is the vehicle network, and CAN C is the main one, which the camera cannot
see. The EPS is the electric power steering, and LaneSense is Jeep's factory lane-keeping. A DBC
is a schema that maps CAN bytes to named signals. Torque "counts" are the raw command units on the
steering message, with no physical unit attached.

## What did what

| tool | role | volume |
|---|---|---|
| T3 Code | the main driver, threads over Claude and Codex providers | 37 threads, 1,521 messages, 319 of them Aaron's, 2026-07-13 to 2026-09-07 |
| Claude Code CLI | deep sessions: post-competition verification, bench work, mutation and coverage runs | 26 sessions from 2026-08-13 |
| Codex CLI | bulk and mechanical work, parallel document mining, independent review, one judge panel | 29 sessions from 2026-07-13 |
| OpenCode | competition entries only (Kimi K3, Grok 4.6) | one day |

Models were assigned by task. Fable 5 ran the design and review sessions, and Opus 5 took over
when Fable's classifier refused or the session hit limits. GPT-5.6 Sol, through Codex, did bounded
implementation from a written spec in an isolated worktree and served as an independent reviewer. Commit trailers on the private metarepo attribute 37 commits to Fable 5 and
7 to Opus 5.

Delegation stopped at safety semantics. Codex implemented the single-arbiter hand-over change and
one post-competition gateway fix from specs, with the driving Claude session reviewing and running
the gates. The torque-release fix in the safety mode stayed in the main session: "safety semantics
are too subtle to hand off."

## Rules and gates

There are three standing rules, and each is enforced by code or by a gate as well as written down.

1. Nothing transmits on a vehicle bus without saying so. The capture tool runs the panda in
   SILENT mode and has no send path, and the gateway firmware boots into bypass and re-checks
   every INTERCEPT precondition on every tick.
2. Nothing goes on hardware without Aaron at the bench. Agents prepare code, tests, worksheets
   and capture windows, then hand over.
3. `dashcamOnly` stays True in the repo until two named proofs are met on the road. Aaron wrote
   it as a ticket with both proofs spelled out. The proofs were met on 2026-08-26 and the flag
   was committed False on 2026-08-28. The full version, with what the current design still owes,
   is in [safety-case](deep-dives/safety-case.md).

Every session started from the same three files: a README for orientation, a glossary (BYPASS
versus INTERCEPT, hand-over versus hand-back, the G1 to G8 constraints, "zero-sender window",
"accepted stream") and a tool catalog with build and test commands and the hardware gotchas that
cost time. In the glossary, "bypass" alone always meant the relay state and never the panda's
SILENT safety mode, and writing that down once stopped a class of confusion across dozens of
sessions.

Tickets moved from a git-backed directory to Linear on 2026-08-20 (and to a self-hosted Redmine
on 2026-09-17, after this page was written), with 26 dated progress notes
preserved as comments. The migration produced one real agent failure. The old note command, run
against a migrated ID, silently wrote nowhere because the file was gone, and progress notes
vanished until a memory note was written about it.

From 2026-08-25 the plan was a single map ticket with a destination, the standing rules, a
"decisions so far" list with one line per closed ticket, a list of things not yet decided, and an
out-of-scope list. Its children were both the open decisions and the execution tickets, grouped
into milestones worked in order. Each session was supposed to end with a resolution comment, a
closed ticket and a line on the map. Most did. The map's decisions list is the best single index
of the project, and this write-up was reconstructed largely from it.

The verification gates, applied to every safety-relevant change and to every competition entry:

| gate | scope |
|---|---|
| opendbc safety suite at 100 percent line coverage | the whole suite, 3,249 tests at the competition and 3,290 on 2026-09-07; the SUSW additions are 141 of them |
| MISRA static analysis | both panda firmware targets |
| mutation testing | scoped to the SUSW safety mode: 85 of 85, then 106 of 106 mutants killed |
| gateway host tests | 167, against a stub that models the sticky CAN error counter |
| both firmware images build | and the stock image, built without the gateway flag, stays byte-identical to upstream |
| fresh-worktree verification | every "how to verify" command in an entry's report run verbatim, fixing nothing |
| judges plant mutants | 14 of 14 and 5 of 5 killed on the winning entry; the post-competition read planted 9 and killed 8 |
| rebase onto upstream | attempted for every entry; all four conflicted on the same two opendbc files, and the panda side was clean |
| bench worksheet | a 30-row state-machine table with wire latencies, for any gateway change |
| cross-layer test | the real CarController driven through the compiled safety library |

The last gate exists because the two halves of a design each passed in isolation while the hole
between them shipped. Both model judges independently declared the bench mandatory, because host
tests stop at the host boundary.

## The competition as a workflow

The full mechanics are in the [competition deep dive](deep-dives/port-competition.md). The parts
that are about workflow:

- Four agent CLIs, petnamed so nobody knew which model was which, each in a tmux window. A fifth
  session orchestrated and did nothing else. It wrote each stage prompt to a numbered file, sent a
  one-line nudge to read it, polled the panes every five minutes, nudged an idle entry up to three
  times before marking it stalled, and watched for the done flags the entries wrote. It never
  edited an entry and never answered an engineering question on Aaron's behalf.
- A dedicated VM with no hardware, no push credentials, no SSH keys and per-entry spend caps.
  Aaron was not willing to give four models from four vendors the access his workstation has.
- Logging Claude Code into Aaron's account brought his claude.ai connectors onto the VM,
  including a ticket tracker with write access. That was fixed with a strict MCP config on every
  launch and a check of the tool list. Codex had no equivalent lock, and one of its subagents
  reached read-only ticket tools before it had read the rules.
- Two judge panels from different vendors, each running the tests itself in its own worktree.
  Both produced the same winner in both rounds. Every entry scored higher in round two, the
  weakest by 20 points, though that gain mixes the peer-review round with three more hours of
  implementation time and cannot be attributed to review alone.

The run took nine and a half hours. The code in the car today descends from the winning entry.

## Where the agents were wrong

In order of who caught it.

### Aaron, reading every turn

Mid-design on 2026-08-23 I drifted from a gateway at the proven interface point toward tapping
CAN C straight into the comma's spare CAN pair, which would have abandoned the interface point and
closed the door on longitudinal control. "Hold your horses big guy, no sudden moves. Be VERY
careful here, your trajectory from the last turn is curving hard away from a ton of our work."
The gateway design became the plan of record with that message.

### The classifier

Fable's safety classifier refused, more than once, to discuss getting around a security gateway in
Aaron's own car. "Got a refusal from the Fable classifier. Continue with Opus." Once it downgraded
the session in the middle of flashing a panda, with the device in an intermediate state, and the
recovery was a written handoff file and a fresh session. The topic was diagnostics on the owner's
own vehicle, and the classifier could not tell.

### The judges

In the winner they found the zero-sender window: the safety mode blocked the stock camera whenever
controls were allowed, while the controller only transmitted while actively steering. A second
entry had two inverted CarState polarities, so its port could not have engaged on any captured
drive. A third accepted a replayed heartbeat that two alternating frames could satisfy, and the
fourth accepted a frozen heartbeat while its report claimed the issue closed.

### An independent read told not to trust the judges

The zero-sender window was larger than the judges said. Both judges wrongly assumed driver
override clears `latActive`, and reading the code settled it. A fault path both judges flagged was
real but unreachable in the gateway build. The read also turned up two defects nobody had found.
Full detail in
[lkas-handover](deep-dives/lkas-handover.md#design-one-block-the-camera-whenever-controls-are-allowed).

### The car, after every host gate was green

- All four entries and the gateway spec assumed the three whitelist messages originate on the
  body half of CAN C. The first INTERCEPT drive showed the ACC HUD message comes from the radar.
  All four agents shared the same wrong prior, so their agreement confirmed nothing.
- The assumed 20 mph ACC floor was wrong for lateral. Stock LaneSense drops out at 33 mph, and 36
  percent of ACC-engaged time was under openpilot's own gate.
- Route 00000133, after the single-arbiter design passed every gate: a brake press at the torque
  cap faulted the EPS through a residual the design had knowingly accepted. "Seems like this was
  maybe not the problem. Or we missed something."
- Route 00000149, after that fix worked exactly as designed: the EPS faulted on a torque cliff
  that upstream's own safety invariant forces at every disengage.

### The agent, auditing its own tooling

- The mutation runner reported "85/85 killed" in 1.1 seconds with a total test time of zero.
  macOS's spawn model made the workers re-import the runner and crash, and a crash counted as
  killed. Two bogus results went by before I noticed the tell. A real run is 5 to 30 ms per
  mutant.
- Stale coverage artifacts produced phantom uncovered lines at an old file's line numbers,
  because a shell glob with no match had aborted the cleanup.
- I claimed on a ticket that a test override was needed, and withdrew the claim in the same
  session after reading the upstream code.
- A torque fit using ordinary least squares reported a "2x error" that was a 40 percent estimator
  artifact. I corrected it in the commit message so the record would not carry it forward.

### Two agents in one tree

On 2026-08-28 two sessions were working the same checkout and Aaron could not tell whose changes
were where. We resolved it by fast-forwarding one onto the other's commit and pushing the three
submodule layers in fetchable order. Parallel implementation agents get their own worktrees now.

## Where agents produced useful work quickly

There was no human baseline for any of these, so none is a measured speedup. Each entry below
gives the starting material, the elapsed time and what checked the result.

**A service manual into a connector inventory.** Input: an 89,000-file offline service manual and
a separate block-diagram set. Output, in one afternoon: a 64-row inventory of every module and
inline connector on four buses with circuit IDs, wire colours, OEM part numbers, source links into
both document sets, and distributor pages for both connector halves, built by parallel subagents
with three read-only auditors. Where the two document sets disagree, the inventory records the
conflict, on Aaron's instruction: "That discrepancy needs to survive into the CSV as an explicit
conflict note, not get cleaned up into bullshit certainty."

**The DBC.** Input: a 24-message draft and three instrumented drives. Output, in a five-hour
competition round: 41 messages at 100 percent checksum and counter pass over 85.8 million frames,
plus the radar object-list decode. Checksum agreement proves the encoding and says nothing about
what a signal means. Two judges checked the meanings by re-deriving the critical signals
independently, and one of them (the ACC HUD's source bus) was still wrong when the car ran it.

**Route audits at frame resolution.** One pass over a route reports engagement episodes, what
limited steering (controller, cap, or driver clamp, separately), the driver-torque distribution
with candidate thresholds, and the health of the steering command stream as the EPS received it.
On route 00000133 that meant 289,506 frames checked and five benign counter skips located to the
second, with the fatal one isolated. The audit was written and run on the afternoon of the fault.

**The bench state machine, measured.** A 30-row worksheet with tooling written for the occasion: a
heartbeat stand-in with a knob table (stop, freeze, loop, alternate, bad CRC, wrong DLC, rate),
vehicle-rate replay of captured CAN C, a relay-fault stand-in, and a timeline tool that classifies
"joined" versus "split" by 0 µs versus 263 µs of probe lag instead of a meter on the relay line. Two
firmware bugs and one wiring rule came out of it before the car saw the firmware.

**Narration synced to CAN time.** In-car narration transcribed by five engines, reconciled by a
text model that knew the drive's vocabulary, then force-aligned to per-word timestamps with a
disagreement score. The competition brief told entrants to treat it as a witness to cross-examine
against CAN edges, and the judges did.

## What held up, and what to change

The glossary and the three bootstrap files held up, and so did progress notes on tickets and the
decisions list on the map. With the flag tied to two written proofs, flipping it meant checking
them. The bench worksheet was a gate the agents could prepare and could not pass themselves.
Independent reads that were told to distrust the previous reviewer paid off every time: each layer
found something the one before it had missed.

To change next time: give every implementation agent its own worktree from day one. Budget the
car as the acceptance test and plan the fault drive before the fix lands. Request the full route
upload right after any fault drive, because one fault's logs rotated off the device before they
uploaded and the diagnosis had to come from 10 Hz summaries.

The car works well enough that a nine-hour drive home from Oshkosh, mostly engaged, felt like
four. The record is reconstructible, and the three faults were all found by driving. Each cost
that drive its steering assist and nothing more. The cost was Aaron's attention: he read every turn, did every hardware step
at the bench, and spent the competition day awake watching four models.
