# The LKAS hand-over problem

This page covers the three EPS faults on the road, the mechanism behind each, and what the
Renegade's steering ECU turned out to require of anyone who sends it 0x1F6. Part of the
[Renegade worklog](../README.md). Current as of 2026-09-07, opendbc `88a3806e`.

## The setup

Two devices can send `LKAS_COMMAND` (0x1F6) to the EPS: the stock forward camera and openpilot.
The camera sits on the camera side of the comma harness (panda bus 2); openpilot's own frames
enter on the car side (bus 0). The panda's forward hook decides, frame by frame, whether the
camera's 0x1F6 is passed through to the car or blocked, and openpilot's 0x1F6 goes through the
panda's transmit hook and its safety checks.

In stock operation the EPS receives 0x1F6 continuously, in every condition measured: 100 Hz over
673,913 frames, torque changing by at most six counts per 10 ms frame in either direction, worst
gap 36.5 ms, and torque zero with the control bit clear even with LaneSense off.

The EPS checks the 4-bit counter and the CRC on 0x1F6. When either is wrong it raises three codes:
U173087 (missing message), U196883 (counter or CRC fault on the steering control message) and,
from the camera's side, U042000 (invalid data from EPS). The cluster shows "Service LaneSense",
`EPS_2.LKA_FAULT` goes to 1, and steering assist is gone until an ignition cycle or two.

## Design one: block the camera whenever controls are allowed

The competition winner's safety mode, which was never installed in the car, blocked the camera's
0x1F6 whenever `controls_allowed` was true, and its controller sent 0x1F6 only while `latActive`
was true. Between those two conditions is a window where nobody sends: every moment below
`minSteerSpeed` with ACC engaged, which on this car is the entire 20 to 36 mph band, unbounded.
Both judges caught it and described it as the override and blinker windows. The independent read
that night found that driver override and blinker do not clear `latActive` in this openpilot, so
those windows do not exist, and the speed-gate window is the whole of it.

## Design two: block the camera only while openpilot's accepted stream is live

This design landed on 2026-08-25, before the first drive. The forward hook blocks the camera only
while `controls_allowed` is true and an openpilot 0x1F6 was accepted by the transmit hook within
the last 50 ms. A refused frame does not refresh ownership. 50 ms was chosen because the stock
stream's own worst gap is 36.5 ms and 20 ms is below what a Python controller reliably holds.
The Codex session that implemented it flagged in its own tests that hand-back still leaves up to
four zero-sender frames. Aaron accepted that residual pending a parked EPS measurement that was
planned and never run, because the road measured it first.

The trace below is from route 00000116 on 2026-08-26, which had 624 seconds of actuation across
eight episodes, at 33 mph. In this and the later traces, timestamped lines are 0x1F6 frames as the EPS received them (counter, torque,
control bit), indented lines are openpilot state changes at that instant, and text at the right
is annotation:

```text
1273.189  ctr  7  torque   0  ctl 1   <- openpilot's last frame, control bit still set
          latActive 0 at 1273.186
                                       50 ms with no 0x1F6 at all
1273.239  ctr 12  torque   5  ctl 1   counter step 5
          latActive 1 at 1273.224 (re-engaged 38 ms after dropping)
1273.298  ctr  2  torque  -1  ctl 1
          latActive 0 at 1273.294
1273.319  EPS: LKA_FAULT -> 1          (21 ms into the second hole)
                                       60 ms with no 0x1F6
1273.359  ctr  8  torque   0  ctl 0   counter step 6
1273.509  camera: LANESENSE_DISABLED 1, HUD state 32, warn 3 -> "Service LaneSense"
```

The trace shows three defects:

1. **The hand-back hole.** When openpilot goes quiet the block persists for the full timeout, so
   every hand-back is a 50 to 61 ms hole. We measured five on route 00000113, one on 00000115
   and three on 00000116.
2. **Counter discontinuity in both directions.** The camera keeps counting while blocked, so it
   resumes with a step of five or six. At hand-over, openpilot's first frame repeats the
   camera's last counter (11 to 11, 6 to 6, 10 to 10) because `CS.lkas_counter` is one frame stale
   by the time the controller runs.
3. **No hysteresis on `latActive`.** Upstream `controlsd.py` computes `standstill` as speed at or
   below `minSteerSpeed`, with nothing else. The only hysteresis in the code base is on the
   "below steer speed" alert, and the control state does not have any. Cruising on the gate produced four
   transitions in 110 ms.

Route 00000113 had come within one transition of the same fault, with four edges in 120 ms and
counter steps of four. The EPS rode through single 50 to 61 ms holes many times across three
routes, and two inside 110 ms faulted it. The fault stayed asserted for the remaining 138 s of
the drive. The next route still showed it, the one after was recovering, and the third was clean.

## Design three: one sender

We costed three candidate designs side by side on 2026-08-28:

| property | A+ (keep the hand-off, shrink it) | C-enabled | C-full single-arbiter |
|---|---|---|---|
| openpilot sends 0x1F6 | only while `latActive` | while ACC and LaneSense are on | always while `chrysler_susw` is loaded |
| hand-overs per drive | every `latActive` edge | every ACC set or cancel | once at boot in normal operation |
| hole at hand-back | timeout + counter step | same, per ACC cancel | only if openpilot stops sending |
| the two-edges-in-110-ms fault | still reachable | unreachable by a human | unreachable |
| stock LaneSense with the toggle on | when openpilot inactive | when ACC off | never |

C-full removes the hand-over mechanism altogether, and it is fewer fork lines than A+: the
`if CC.latActive` gate and the previous-transmit bookkeeping are deleted and the SUSW branch of the
controller collapses to "every other Chrysler plus a counter argument". Shrinking the timeout to
20 ms had already been rejected, because Python jitter produces two-sender flicker, and 30 ms is
the floor.

Sub-decisions:

- The idle frame is torque zero with the control bit mirrored from the camera's own latest
  blocked frame, so `EPS_2.LKA_STATUS` keeps tracking what the camera asked for. Camera torque can
  never be relayed; the safety layer refuses non-zero torque outside `controls_allowed`.
- The boot hand-over counter is extrapolated from the last forwarded camera frame that
  reached the EPS: `counter + round(elapsed / 10 ms) + 1`. The parsed value is stale by then.
- `latActive` hysteresis in the fork's `controlsd.py`: drop at `minSteerSpeed` (14.9 m/s), re-arm
  1.0 m/s above it, which is stock LaneSense's own arm and drop band. Replayed on route 00000116
  the burst disappears: 16 edges become 10, all of them real engages and disengages. It is the
  fork's only
  edit to that file, and the upstream lines are byte-identical on master.
- Cost accepted: with the toggle on, stock LaneSense corrections never reach the EPS, ACC on or
  off. With the toggle off the car is fully stock.
- Safety model change accepted: openpilot's liveness alone silences the camera, so the failure
  class moves from unexpected actuation to loss of assist.

"Once at boot" describes normal operation, and it is not enforced. The forward hook still hands
the camera back after 50 ms without an accepted openpilot frame, so a controller restart, a
process crash or a burst of refused frames produces a hand-back on the road, with the same hole
and counter step design two had. Those cases are the residual risk of this design, and the road
proof that is still open includes provoking them.

The forward hook after the change, from `opendbc/safety/modes/chrysler_susw.h`:

```c
static bool chrysler_susw_fwd_hook(int bus_num, int addr) {
  bool block_msg = false;

  if ((bus_num == 2) && (addr == 0x1F6)) {
    // openpilot owns LKAS_COMMAND while its accepted stream is live. A refused command cannot
    // refresh ownership; stock returns after the last accepted frame reaches the timeout.
    bool op_stream_live = false;
    if (chrysler_susw_lkas_tx_seen) {
      const uint32_t ts_elapsed = safety_get_ts_elapsed(microsecond_timer_get(), chrysler_susw_lkas_tx_ts);
      op_stream_live = ts_elapsed < CHRYSLER_SUSW_LKAS_TX_TIMEOUT;
    }
    block_msg = op_stream_live;
  }

  return block_msg;
}
```

There is no `controls_allowed` term. Upstream's `lateral.h` accepts torque-zero frames outside
`controls_allowed`, so continuous transmission needed no test override at this point. The ticket
had first claimed that it would, and that claim was withdrawn in the same session.

Gates on landing: 3,283 safety tests at 100 percent line coverage, MISRA clean, 85 of 85 mutants
killed on `chrysler_susw.h`, and a cross-layer test that drives the real CarController through
the compiled safety library, because both halves of design two were green in isolation when the
hole shipped.

## Fault two: refused frames burn counters

Route 00000133 on 2026-08-30 ran 48 minutes with the stream itself clean: 289,506 accepted
frames, zero CRC mismatches, a max gap of 44 ms (one, at boot), no gap over 50 ms, and three clean
hand-overs. The fault came at a brake press on a ramp, while slowing under ACC at the torque cap:

```text
2622.804  accepted ctr 7  tq 353 ctl 1          <- last good frame (saturated at 383)
2622.815  carState brakePressed=1
2622.81x  panda: controls_allowed -> 0          (same brake frame, receive side)
2622.814  REFUSED ctr 8 tq 347
2622.817  selfdriveState disabled (pedalPressed)
2622.823  REFUSED ctr 9 tq 341
2622.833  accepted ctr 10 tq 0 ctl 1
2622.844  EPS: LKA_FAULT -> 1, LKA_STATUS -> 0
2622.965  camera: "Service LaneSense"
```

The panda drops `controls_allowed` on the brake CAN frame, one to two 10 ms frames before
Python's `latActive` follows. Under the old hand-off design that window produced silence. Under
single-arbiter the counter free-runs, so two refused frames at 350 counts became a 29 ms hole and
a counter skip from 7 to 10. The same window fired at every disengage on the route, with one
refused frame at 68 counts and one at 210, and the EPS survived both. A skip of two at 210 or
less survived repeatedly, and a skip of three with a 29 ms hole from 353 faulted.

The fix reads the disengage inputs (brake pressed, cruise state not enabled) from the same
CarState frame the panda uses, and commands zero torque on that frame, so the in-flight refusal
window is at most one frame.

## Fault three: the torque cliff

This was route 00000149 on 2026-09-03. Its full logs rotated off the device at 89 percent disk
before they uploaded, so the reconstruction rests on the 10 Hz summary logs (CarState,
CarControl, CarOutput and panda state) plus the previous route's full CAN. Those summaries show no
refused frame, no gap in the stream and a continuous counter, and the EPS faulted anyway. Times
below mix CAN-side and openpilot-side clocks:

```text
1330.5   right blinker, lane change right; torque ramps -36 -> -336 over 0.7 s
1331.5   applied -327 / -289 / -295 / -279, driver torque +36 .. +114 opposing
1331.93  brake pressed -> panda controls_allowed 0
1331.95  carControl torque 0 (fast path, same frame), no refused frame
1331.97  carState steerFaultTemporary = 1
```

The evidence points to a torque cliff. What the EPS saw was -279 to 0 across one 10 ms frame,
probably with the control bit dropping 1 to 0 in the same frame (the idle frame mirrors the
camera's bit, and with a blinker on the camera's bit is set only 18 percent of the time). Every
disengage on record:

| route / time | cliff | control bit | other | EPS |
|---|---|---|---|---|
| 133 / 496.1 | 74 to 0 | 1 to 1 | 1 refused frame | ok |
| 133 / 1079.6 | 205 to 0 | 1 to 1 | 1 refused frame | ok |
| 133 / 2622.8 | 353 to 0 | 1 to 1 | 29 ms hole, skip 3 | fault |
| 149 / 507.3, 592.7 | about 0 to 0 | | 1 refused frame each | ok |
| 149 / 1331.9 | -279 to 0 | probably 1 to 0 | none seen at 10 Hz | fault |

Every disengage the EPS survived was a cliff of 205 or less. Both faults were 279 or more, and
one of them also had a hole and a skip. The stock camera never cuts, and it moves at most six
counts per frame.

Upstream's invariant, no torque when `controls_allowed` is false, forces the cliff. The fix is a
bounded release in both layers. The controller ramps toward zero at 60 counts per frame (383 to 0
in seven frames, 70 ms), control bit held until zero. The safety mode, once `controls_allowed`
drops, accepts a non-zero command only as a strict decay of the last accepted one:

- same sign as the last accepted torque,
- at least six counts smaller in magnitude (the stock rate, so it cannot hover),
- control bit set,
- for at most ten accepted frames after the drop; the budget resets on any allowed frame.

Zero always passes, and from an idle stream nothing non-zero can start, so a controller that is no
longer allowed to steer can only complete a ramp it already started. The bound is count-based:
ten accepted non-zero frames, with no elapsed-time deadline and no freshness check on the last
accepted torque, and a frame that qualifies as a release skips the usual rate and driver-torque
checks (it can drop by more than six per frame). From `opendbc/safety/modes/chrysler_susw.h`,
where `chrysler_susw_lkas_torque_last` is the last accepted torque and `steer_req` is the control
bit:

```c
    bool release = false;
    if (!controls_allowed && (desired_torque != 0)) {
      const int last = chrysler_susw_lkas_torque_last;
      const int last_abs = (last < 0) ? -last : last;
      const int desired_abs = (desired_torque < 0) ? -desired_torque : desired_torque;
      const bool same_sign = ((last > 0) && (desired_torque > 0)) || ((last < 0) && (desired_torque < 0));
      release = same_sign && steer_req && (desired_abs <= (last_abs - CHRYSLER_SUSW_RELEASE_MIN_STEP)) &&
                (chrysler_susw_release_frames < CHRYSLER_SUSW_RELEASE_MAX_FRAMES);
    }
```

60 per frame sits under the 205 cliff the EPS tolerated in the captures and is ten times the stock
rate. This is a documented departure from upstream's rule with an override of
`test_steer_safety_check`, and the cross-layer test ramps to the cap through the compiled safety
library, presses the brake with `latActive` still true, and asserts one sender, a continuous
counter, and the accepted 323 / 263 / 203 / 143 / 83 / 23 / 0 ramp. Gates: 141 SUSW tests, 3,290
safety tests at 100 percent coverage, MISRA clean, 106 of 106 mutants killed.

## What survived and what faulted in these captures

These brackets come from drive evidence, with the variables above unresolved, and no parked probe
has been run:

| condition | survived | faulted |
|---|---|---|
| single hole | 50 to 61 ms, many times | two holes inside 110 ms |
| counter skip | 2, at up to 210 counts, repeatedly | 3, with a 29 ms hole, from 353 |
| one-frame torque cut | up to 205 counts | 279 (alone, at 10 Hz resolution) and 353 (with a hole and a skip) |
| stock camera's own behaviour | 6 counts per frame, max gap 36.5 ms | never observed faulting |

Between the faults, the Oshkosh leg ran 786,234 EPS-received frames with zero gaps over 25 ms
across 131 minutes, on the design-two build, and the return to Cleveland ran mostly engaged for
about nine hours on design three with the fast-path fix, without a fault, before the bounded
release landed. The single-arbiter road proof (boot hand-over across
ignition cycles, 20 minutes with LaneSense on and ACC off, deliberate high-torque brake disengages
in curves and during a blinker lane change) is the next drive on the map.

> **Changed since, as of 2026-11-24.** That proof drive was never run as written. Aaron drove the
> car daily on the bounded-release build from 2026-09-12, and on 2026-10-05 reported dozens of
> engaged hours with no EPS fault, including disengagements mid-turn at significant torque. The
> road proof was closed on that report. Since 2026-10-22
> openpilot also sends the cluster frame `LKA_HUD_2` (0x547) on bus 0, beside 0x1F6. See
> [September to November](../porting-the-renegade.md#september-to-november).

## Porter's notes

- Shortening the timeout on a gated forward hook shrinks the hole. It does not close it, and the
  blocked camera keeps counting through it.
- Extrapolate the hand-over counter from the last frame that reached the EPS. A parsed value is
  a frame stale.
- Mirror the panda's disengage inputs from the same CarState frame. The panda is one to two
  frames ahead of `latActive`.
- If your EPS is like this one, commanding torque zero the instant control is disallowed will
  fault it. Ramp the torque down, and make the safety layer enforce the ramp.
- Two halves that each pass in isolation do not add up to a tested design. Drive the real
  controller through the compiled safety library.

## Provenance

Written by Claude, the coding agent on this project (drafted on Fable 5.1, revised on Fable 5.2),
from the project's transcripts, tickets and repository history. Aaron did the bench and car work.
He has read the summary and has not reviewed every page.
