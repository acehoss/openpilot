# The safety case for turning dashcamOnly off

This page says what had to be true before the fork was allowed to steer the car, how each item
was proven, which rules stayed in force after, and what the current design still owes. Part of the
[Renegade worklog](../README.md). Current as of 2026-09-07.

## The standing rules

Two rules held from the first day and never changed:

1. **Nothing transmits on a vehicle bus without saying so.** The tooling enforces it. The capture tool runs the panda in `SAFETY_SILENT` and has no code path that calls
   `can_send()`. The Teensy interposer's vehicle build was listen-only at the controller level.
   The gateway firmware boots into BYPASS with the panda SILENT and drives the relay only after
   every precondition in its contract holds on every tick.
2. **Nothing goes on hardware without Aaron at the bench.** Agents prepare code, tests, worksheets
   and capture windows and hand over. The in-car gateway is flashed only after the bench
   worksheet passes.

A third rule was written the day after the competition, and this page is mostly about it.

## The dashcamOnly policy

`dashcamOnly` is the opendbc flag that keeps a car port in dashcam mode: openpilot runs, logs and
fingerprints, and never sends control. The competition winner shipped with it True. Aaron set the
policy on 2026-08-24: the flag stays True in the repo, and may be flipped locally on the device
only, until two proofs are met on the road with the full pipeline live.

**Proof 1.** With LaneSense switched off at the car, openpilot control is inhibited. In practice
that means `controls_allowed` is never true, the stock camera's 0x1F6 is never blocked, and
nothing actuates.

**Proof 2.** With the "enable openpilot" toggle off, the car is fully stock: LaneSense and ACC
work normally with the fork installed, and openpilot never transmits.

Proof 1 rests on the engagement rule Aaron gave the competition (G3): openpilot may be active only
when stock ACC is engaged and LaneSense is on. That gate is enforced in three places, which is why
a single failure in any one of them cannot enable control. `cruiseState.enabled` in CarState
requires both. `controls_allowed` in the panda safety mode is set through
`pcm_cruise_check(cruise_engaged && !lanesense_disabled)` from the same CAN bits. And the forward
hook that blocks the stock camera depends on openpilot's accepted stream, which cannot exist
without `controls_allowed`.

The plan hid a constraint collision. Under `dashcamOnly` the comma runs the panda in `noOutput`,
so the heartbeat never leaves the car and the gateway can never leave BYPASS. The first INTERCEPT
drive therefore requires `dashcamOnly` lifted, and that drive is also the first time the safety
mode, forward hook and heartbeat ever run. The shakedown design came from that: lift the flag locally with LaneSense switched off at the car, so `controls_allowed`
cannot become true and the whole pipeline runs with zero actuation.

## How the proofs were met

Route 00000107 on 2026-08-26 was 44 segments and 43 minutes, on surface streets with a stretch at
60 mph, LaneSense off:

- The `chryslerSusw` safety mode was loaded and the gateway held INTERCEPT.
- `controlsAllowed` was 0 in every one of 25,751 panda state samples.
- `sendcan` contained the heartbeat 0x5F0 and nothing else.
- Every camera 0x1F6 was forwarded to the car.

Later that afternoon, on an errand route with the same build, Aaron switched LaneSense on with
ACC engaged. `controls_allowed` went true on the road for the first time, about 10 seconds across
four windows. The stock 0x1F6 was still never blocked, because openpilot could not engage.
`cruiseState.available` was false, since the gateway was not yet copying the ACC HUD message (see
the [gateway deep dive](rpgw-gateway.md#the-whitelist)), and the accepted-stream gate had nothing
to accept. That was the accepted-stream design proven on the road, and it was also the
last piece of Proof 1.

Proof 2 was met by accident at midday. The first parked attempt at the shakedown stayed in
dashcam mode because the enable toggle was off, which makes openpilot passive, which puts the
panda in `noOutput`, which stops the heartbeat, which leaves the gateway in BYPASS. Toggle off is
stock by construction. That is stricter than the proof as written. With the toggle off the
gateway stays in BYPASS and never reaches INTERCEPT, so the "safety mode loaded" clause of Proof 2
was never exercised and does not need to be.

Aaron met both proofs on the road on 2026-08-26 and committed the flag False on 2026-08-28, two
days later, once the single-arbiter hand-over fix had landed. In between, the device carried a
local edit that every device update silently reverted, which was one more reason to commit it.

## What the single-arbiter design changed

The proofs above were made against design two, where the camera was blocked only while
`controls_allowed` was true. Under the current design openpilot sends 0x1F6 continuously whenever
the safety mode is loaded, and the camera is blocked whenever that stream is live, LaneSense on or
off. So the literal Proof 1 clause "the stock camera's 0x1F6 is never blocked" no longer holds with
the toggle on. What still holds, and what the proof was for:

- With LaneSense off, `controls_allowed` cannot become true, so openpilot's stream carries torque
  zero and the EPS receives no lateral torque from anyone. No actuation.
- With the toggle off, openpilot is passive, no heartbeat leaves the car, the gateway stays in
  BYPASS, and the car is stock.
- After any disengage the safety layer accepts only a strict decay of the last accepted torque,
  for at most ten frames.

What the current design still owes is its own road proof: boot hand-over across several ignition
cycles, twenty minutes with LaneSense on and ACC off (the camera blocked for a whole drive), and
deliberate brake-press disengages at high torque in a curve and during a blinker lane change. The
131-minute fault-free leg on 2026-08-27 was driven on design two. The mostly engaged nine-hour
return from Oshkosh was driven on design three with the fast-path fix, before the bounded release
landed, and was not fully instrumented. Neither is evidence for the current build.

## Why the trip was driven stock

The trip to Oshkosh began one day after the first engagement, and the temptation was to use the
highway as the test session. The decision was recorded before departure: shakedown is short,
purposeful local drives, and the trip is driven stock unless first lateral is done. "It's unclear
if hours of unfocused testing data would be any more beneficial than minutes of purposeful testing
exercise data." No fork-only "enable control" toggle either; the stock enable toggle already gives
the fallback (passive, `noOutput`, BYPASS), and a Params toggle only reaches one of the three
gates. After the first fault on the evening of 2026-08-26, the enable toggle went off for the
trip and the fix was designed before it went back on.

The first drive's abort criteria, written before it and still in force:

- `EPS_2.LKA_FAULT` asserts, or `LKA_STATUS` leaves 2 while torque is being commanded.
- Any steering motion the driver did not expect, or torque that resists the driver.
- Motor torque sign disagreeing with the command for more than about 0.2 s.
- A cluster steering or LaneSense fault, or an unexpected warning.
- `canValid` drops, or the fusion-bus ACC state goes stale.
- Anything the driver simply does not like. There is no schedule pressure that justifies a
  second try.

## Limits and where they came from

Every limit shipped so far came from the car's own captures. The parked EPS probes were planned
and never run. The table separates observed values, inferred meanings and chosen margins.

| parameter | value | observed | margin chosen |
|---|---|---|---|
| `STEER_MAX` and safety `max_torque` | 383 | stock camera's peak on route 000000d8 (-346 to +383), accepted by the EPS, with LaneSense strength on medium | the EPS's own ceiling is unprobed; 383 is the medium-strength stock ceiling |
| `minSteerSpeed` | 14.9 m/s | stock LaneSense drops out at 14.88 to 14.91 m/s and arms at 15.9 to 16.0 | set at the drop-out speed, below the arm speed; below 14.9 is unmeasured |
| rate limits | 5 up, 6 down per frame | stock camera moves exactly 6 per frame | up held one below stock for jerk headroom |
| `max_rt_delta` | 180 | 26 frames per 250 ms window at 6 per frame is 156 | about 1.2 times the fastest legal movement |
| driver allowance and multiplier | 160, 3 | engaged driver-torque distribution on route 00000123: p50 62, p90 137, p99 194, p99.5 208; resting-hands p90 on route 00000113 was 103 | the assist reaches zero at 160 + 383/3 = 288 counts, inside the 360-count peak seen |
| `SUSW_STEER_THRESHOLD` | 160 | 120 read 16 percent of engaged frames as an override that never happened, freezing the PID integrator; p99.5 would support 220 | Aaron held at 160 for fear of driver-induced oscillation |
| `latAccelFactor` | 1.20 | total-least-squares fit over 104,631 points from route 00000123 | an OLS fit gave 0.74 and was wrong; OLS attenuates a noisy regressor's slope |
| friction | 0.23 | same fit | |
| `MAX_LAT_ACCEL_MEASURED` | 1.4 | p99.5 of lateral acceleration while engaged | fleet convention |
| release rate at disengage | 60 counts per frame, 10 frames | survived cuts were 205 or less; faults were 279 or more | under the tolerated cliff, ten times the stock rate |

The limit is on driver torque because a motor-torque limit does not work on this car.
`EPS_2.TORQUE_MOTOR` is the motor's output, about 0.23 times the command, and the difference
between command and motor torque reaches 397. A motor-torque check with upstream's 80-count error limit would reject 36 to 44 percent of
the stock camera's own frames. The stock camera is the reference the EPS was built for, so a check
that fails it is the wrong check for this platform.

openpilot's on-device `torqued` will not learn parameters for Chrysler (not in its allowed list,
and it needs 4,000 bucketed points above 15 m/s), so the fit has to be done offline, with
torqued's own estimator. The first attempt used ordinary least squares and reported a factor of
0.74 as a "2x error" in the borrowed value. OLS was the wrong estimator, and the correction went
into the commit message so the record would not carry the mistake forward.

## Verification gates

The full gate list is in [agent-workflow](../agent-workflow.md#rules-and-gates). Three of them
carry the safety argument on this page:

- The opendbc safety suite at 100 percent line coverage, with mutation testing scoped to the SUSW
  safety mode (106 of 106 mutants killed at the current commit). The gateway changes sit behind a
  build flag and leave the stock `panda_h7` target unchanged.
- The bench worksheet for any gateway change.
- A cross-layer test that drives the real CarController through the compiled safety library,
  added after both halves of a design were green in isolation while the hole shipped.

The car is the last gate. Two of the three road faults came after every host gate was green. The
host tests check that the code does what the design says, and it took the EPS to show whether the
design was right.

## The rule as it stands

Since 2026-08-28: `dashcamOnly` is False for the Renegade. With the enable toggle on, the car
engages whenever ACC is set and LaneSense is on, and stock LaneSense never steers. With the toggle
off the car is stock. Keep LaneSense off on every drive except a deliberate lateral session.

Still open: the single-arbiter road proof drive, the parked EPS characterisation that would
replace drive-derived limits with measured ones, and a capture with LaneSense strength on
maximum.

## Changed since, as of 2026-11-24

This page describes the safety case as it stood on 2026-09-07. Later work changed these parts of
it, and [September to November](../porting-the-renegade.md#september-to-november) has the story.

- The road proof was closed on 2026-10-05, on daily driving. The proof drive described above was
  never run as written. Aaron reported dozens of engaged hours on the bounded-release build with
  no EPS fault, including disengagements mid-turn at significant torque. No route audit covers
  those weeks, and no EPS fault has been recorded since.
- The LaneSense half of the engagement gate now reads openpilot's own toggle. Since 2026-10-22
  openpilot sends the cluster frame `LKA_HUD_2` (0x547) on bus 0, the safety mode reads
  `LANESENSE_DISABLED` from openpilot's accepted frame, and the panda drops controls on the rising
  edge of the LaneSense button. The stock hands-off warning no longer reaches the cluster, which
  leaves openpilot's own camera-based driver monitoring to watch the driver.
- The driver allowance and `SUSW_STEER_THRESHOLD` went from 160 to 220 on 2026-10-28, with a
  0.2 s debounce. Over 40 minutes of hands resting on the wheel on one route, the threshold at 160
  flagged an override 1,932 times an hour, against 40 at 220.
- The feedforward is a curvature table since 2026-10-22, with friction at 0.01.
  `latAccelFactor` stays at 1.20 for friction scaling and the ISO limit test. See
  [lateral tuning](lateral-tuning.md).
- A capture with LaneSense strength on high showed the stock camera peaking at exactly 383 counts,
  the same as on medium. `STEER_MAX` stays at 383, and the EPS's own ceiling is still unprobed.
- A stricter run of the mutation check, one process per mutant, counted 111 mutants on the SUSW
  safety mode: 106 killed and 5 survivors, all five equivalent mutants. After the rebase onto
  v0.11.2 the suite is 3,281 tests at 100 percent line coverage, and the stock mutation runner
  over the whole safety suite kills 2,826 of 2,829.
- The safety mode ids are now 39 for `chryslerSusw` and 40 for `suswGateway`.
- With the toggle off the car is still fully stock. Flip the toggle with the car off, because
  flipping it on the road costs 10 to 20 seconds while openpilot restarts.
- The parked EPS characterisation has still not been run, and nothing below 14.9 m/s is measured.

## Provenance

Written by Claude, the coding agent on this project (drafted on Fable 5.1, revised on Fable 5.2),
from the project's transcripts, tickets and repository history. Aaron did the bench and car work.
He has read the summary and has not reviewed every page.
