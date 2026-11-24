# openpilot on a 2023 Jeep Renegade, in one screen

> Written by Claude, the coding agent on this project (drafted on Fable 5.1, revised on Fable 5.2),
> from the session transcripts, tickets and repository history. Aaron did the bench and car work.
> He has read the summary and has not reviewed every page.

openpilot is open-source driver assistance that runs on a comma four, a small camera-and-computer
box at the windshield. It supports about 300 cars. The 2023 Jeep Renegade was not one of them, and
neither was anything else on its platform. Eight weeks after the first session, having started
with no access to the car's data at all, it was steering itself on the highway. The long version
is [porting-the-renegade](porting-the-renegade.md).

## Why this car was hard

Before openpilot may steer, it has to know that the factory adaptive cruise is engaged. The
Renegade broadcasts that on its main vehicle network, CAN C, which the camera is not wired to. The
OBD port is no help, because the security gateway that filters it is built into the body computer
and there is nothing to unplug or bypass. So the first job was plumbing: find a place to reach CAN
C and carry three messages from there to the camera.

## Finding the network

Aaron built a cable for the diagnostic port and learned in one parked session that the port
carries diagnostic requests and nothing periodic. He then built an interposer for the radar
connector around a Teensy board. It worked on the bench and failed its first install on bad
crimps, behind a front fascia that takes an hour and a bag of trim clips to remove. Putting the
car back together, he noticed a 14-position inline connector in the wheel well carrying the same
six wires. The 84,728-page factory manual has no end view of it. Photos and one caliper
measurement identified it (27.0 mm across six cavity gaps gives the connector family), and the
mating parts cost two dollars each. [More](deep-dives/finding-can-c.md).

## The gateway

A Red Panda, comma's CAN interface board, sits inline at that connector in a comma harness box,
running its own firmware. While openpilot sends it a heartbeat, it splits CAN C into a body half
and a radar half, forwards every frame between them in software, and copies the three cruise-state
messages onto the private radar link where the camera side can read them. With no heartbeat the
switch never opens and the car behaves as it did from the factory, as long as the box has power.

On the bench it forwarded 349,913 of 349,913 frames at vehicle rate with a median latency of
390 µs. The bench also found a CAN controller error state that the firmware could never have left
by itself. The first drive then showed that one of the three messages comes from the radar side.
Every design had put all three on the body side. [More](deep-dives/rpgw-gateway.md).

## The port

Four coding agents (Claude Code, Codex, and OpenCode with two models) built the car port in
parallel from the same checkout in one day. There were two implementation rounds, a peer-review
round after each, and two model judges scoring against a rubric published at the start. The winner
shipped a 41-message signal database, a torque-limited safety layer for the panda, and the gateway
firmware. It also had a blocking defect, a window in which no device sent the steering command at
all. The judges caught it, an independent read that night showed it was bigger than they had said,
and it was fixed before the first drive. [More](deep-dives/port-competition.md).

## Three EPS faults

The electric power steering (EPS) faulted three times on the road, and two of those came after
every host-side check had passed.

The first was at hand-back, when the camera takes the steering command back from openpilot: a
50 ms hole in the command, then a counter skip. The fix was to stop handing over. openpilot now
sends the command all the time, so the hand-over happens once, at boot, and the speed gate that
had been flapping it on and off got hysteresis.

The second happened because the panda disengages one frame before the Python side does, and under
the single-sender design the frames it refuses in between use up counter values. Python now reads
the disengage inputs from the same frame the panda uses.

The third was a torque cut from 279 counts to zero in one frame, reconstructed from 10 Hz logs
because the full logs were lost. Upstream openpilot sends no torque while disabled, which forces
that cut at every disengage, and the stock camera never moves more than six counts per frame.
Torque now comes off on a bounded ramp that the safety layer enforces as a strict decay. In the
captures, every disengage the EPS survived cut 205 counts or less, and the two that faulted cut
279 or more. [More](deep-dives/lkas-handover.md).

## The first long drives

Aaron drove part of the trip to Oshkosh engaged and most of the nine-hour return to Cleveland,
without an EPS fault. The return was on the single-sender build, and he said those nine hours were
about as tiring as four: the car kept itself between the lines while he kept his attention on the
road and his hands on the wheel, which the car's own nag insists on.

The longest fully instrumented and audited leg is 131 minutes at 48 to 74 mph on 2026-08-27, on
the build before that.

## Since September

On the return trip, lateral control had dropped out whenever the car passed about 78 mph, because
the speed signal is 12 bits wide and we had decoded 11. That was fixed within the week. Aaron kept
driving the car, and on 2026-10-05 he reported dozens of engaged hours with no EPS fault, which
closed the road proof for the single-sender design.

In late October openpilot took over the LaneSense button and the lane-keeping frame on the
instrument cluster, so the stock camera's hands-off chime no longer reaches the driver. Lateral
tuning that same week found that this EPS treats a torque command as a column position, with a
hysteresis band around it. Two blended models failed, and
what the car runs now is a curvature table with a small stiction pulse.
[More](deep-dives/lateral-tuning.md). On 2026-10-31 the fork was rebased onto openpilot v0.11.2
for Chestnut, comma's external GPU dock, and the car ran the big driving model on its first
drives that day.

## Where it stands, 2026-11-24

No EPS fault has been recorded since 2026-09-03, and the safety suite is 3,281 tests at 100
percent line coverage. Still open are the rest of the lateral tuning, EPS characterisation
with the car parked, and longitudinal control, which has not been started.
[More](deep-dives/safety-case.md).

## How the work was run

Every session started from the same three files: an orientation README, a glossary and a tool
catalog. On top of those were tickets with progress notes, a plan kept as a map with a running
list of decisions, and a flag that stayed off until two named proofs had been met on the road.
Agents prepared everything, and nothing touched hardware without Aaron at the bench. What that
bought and what it missed is in [agent-workflow](agent-workflow.md).
