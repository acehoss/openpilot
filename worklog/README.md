# Worklog: openpilot on a 2023 Jeep Renegade

> Written by Claude, the coding agent on this project (drafted on Fable 5.1, revised on Fable 5.2),
> from the session transcripts, tickets and repository history. Aaron did the bench and car work.
> He has read the summary and has not reviewed every page.

This fork steers a 2023 Jeep Renegade. No openpilot port existed for the car or its platform, the
camera cannot see whether cruise is engaged, and the security gateway is built into the body
control module. The car first engaged on 2026-08-26, and in early September Aaron drove most of
a nine-hour return trip from Oshkosh to Cleveland engaged without an EPS fault. The steering has
since been tuned for this car's EPS, and as of 2026-11-24 the fork sits on openpilot v0.11.2.

These pages cover 2026-07-13 to 2026-11-24. They say what the car turned out to be, what was
built, which approaches failed, and what is still open. Most of them were written on 2026-09-07
and tell the story up to that date. Where later work changed something, the page carries a dated
note, and the main article has a section on September to November.

## Start here

- If you are porting an FCA small-wide car (Renegade, 500X, Toro), read
  [porting-the-renegade.md](porting-the-renegade.md) and then the deep dives in the order below.
- For the result in one screen, read [summary.md](summary.md).
- For the coding-agent workflow, read [agent-workflow.md](agent-workflow.md).

## Deep dives, in dependency order

1. [finding-can-c.md](deep-dives/finding-can-c.md). Where cruise state lives, why the diagnostic
   port and a radar interposer both failed, and the XY005A inline connector with its part numbers
   and cavity map.
2. [can-findings.md](deep-dives/can-findings.md). Every bus and signal the port uses, with how
   each was proven and where decoding goes wrong.
3. [rpgw-gateway.md](deep-dives/rpgw-gateway.md). How the Red Panda gateway works: what the
   harness box does electrically, when the firmware may split the bus, which three messages it
   copies, and what the bench measured.
4. [lkas-handover.md](deep-dives/lkas-handover.md). The three EPS faults and what caused each,
   with the limits the EPS turned out to have on gaps, counter skips and torque cuts.
5. [safety-case.md](deep-dives/safety-case.md). What had to be true before `dashcamOnly` went
   False, where every limit came from, and what the current design still has to prove.
6. [capture-toolchain.md](deep-dives/capture-toolchain.md). The instruments, how two recorders
   were fitted to one clock, and the tooling failures that cost hours.
7. [port-competition.md](deep-dives/port-competition.md). Four coding agents did the port in
   parallel in one day, with peer review between rounds and two model judges. How it was run and
   what came out of it.
8. [lateral-tuning.md](deep-dives/lateral-tuning.md). The October tuning: an EPS that takes the
   torque command as a column position, the two blends that failed, the stiction pulse that
   worked, and a dither that froze the integrator.

## Where the code is

| what | where |
|---|---|
| car port | `opendbc_repo/opendbc/car/chrysler/` (SUSW platform, CarState, CarController), opendbc branch `chrysler-smallwide` |
| DBC | `opendbc_repo/opendbc/dbc/chrysler_susw.dbc` |
| safety mode | `opendbc_repo/opendbc/safety/modes/chrysler_susw.h` |
| gateway firmware | `panda/board/gateway.h`, target `panda_gateway_h7`, panda branch `renegade` |
| gateway safety policy | `opendbc_repo/opendbc/safety/modes/susw_gateway.h` |
| lateral feedforward table | `opendbc_repo/opendbc/car/chrysler/susw_lateral.py` |
| changes to openpilot itself | nine source files against v0.11.2, mainly `openpilot/selfdrive/controls/lib/latcontrol_torque.py`, `openpilot/selfdrive/controls/controlsd.py` (hysteresis on `latActive`) and `openpilot/selfdrive/car/susw_lanesense.py` |

The capture tools, bench worksheets, route data and the competition record (brief, rubric, judging
sheets, each entry's report) are in a private repository and are not published. Route numbers
cited in these pages are shortened. Device identifiers, serial numbers and hostnames have
been removed.

The three forks were rebased on 2026-10-31. Commit hashes cited on pages written before that date
are reachable through the tag `pre-rebase-v0.11.2` in each fork.
