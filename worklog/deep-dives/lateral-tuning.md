# Tuning lateral control on the Renegade's EPS

This page covers the lateral tuning done between 2026-10-21 and 2026-10-31: what the electric
power steering (EPS) turned out to do with a torque command, the approaches that failed, and what
the car runs now. Part of the [Renegade worklog](../README.md). Current as of 2026-11-24, and the
tuning is not finished. "I" on this page is the coding agent.

## The symptom

By October the car had weeks of driving on the September build with no EPS fault, and Aaron
judged the first round done: "I think there is room for more tuning still, but the initial is all
done at this point."

Hands off, here and in the rest of this page, means hands off the wheel with the driver watching
the road and ready to take control at any moment.

It showed on 2026-10-21. On a left curve at 37 mph with hands off the wheel, the steering
angle swung about 15 degrees peak to peak, once a second, for the whole curve. The command
saturated, the applied torque lagged it by about 150 ms, the angle jumped from -5.9 to -14.0
degrees in 200 ms, and lateral acceleration overshot to 1.78 m/s² against 0.98 requested.

The first idea was to take torqued's live estimate, which had drifted to a `latAccelFactor` of
0.90 and friction of 0.19 against the shipped 1.20 and 0.23. I rejected it. torqued restores its
point buffer from a stored parameter at every start, so those numbers were a multi-week aggregate,
and a fit on that one drive gave 0.40 to 0.48, which is what stick-slip looks like to a linear
fit. Lowering the factor from 1.20 to 0.90 also multiplies every torque term by 1.33 and raises
the loop gain on a loop that was already oscillating. openpilot does not apply torqued's estimate
for Chrysler in any case.

The first change that helped was plain: proportional gain times 0.6 for this platform. Straights
got calmer, and the one-per-second cycle stayed.

## What the EPS does with a command

openpilot's torque controller assumes that lateral acceleration rises in proportion to the torque
command. On one drive, with hands off and the command lagged 0.3 s, the curvature the car held at
each command level was:

| command, counts | 75 | 100 | 150 | 200 | 250 | 300 | 350 |
|---|---|---|---|---|---|---|---|
| curvature, 1/km, 15 to 31 m/s pooled | 0.12 | 0.18 | 0.42 | 0.69 | 1.27 | 2.75 | 3.70 |
| curvature, 1/km, 25 to 31 m/s only | 0.14 | 0.19 | 0.41 | 0.65 | 1.07 | 1.89 | 2.16 |

Up to about 225 counts the two rows agree within 20 percent. The command sets a column position,
and that position is the same at any speed. The curve is convex, roughly curvature = 8e-5 ×
command^1.67, with very little happening below about 100 counts and a steeper rise above 250. The
motor torque reported in `EPS_2` correlates with the square of the command at 0.935, so the
convexity is in the EPS's own overlay map.

Lateral acceleration is curvature times speed squared, so a feedforward built on a constant
`latAccelFactor` is wrong by about 2.6 times between 40 and 65 mph.

The column also has a hysteresis band around that curve, 100 to 150 counts either side at low
curvature. It takes more command to start the column moving than to hold it, so it sticks, then
lets go and overshoots. Across 19 break-away events the median command at release was 0.40 of the
383-count maximum.

## What was tried

The feedforward became a table from curvature to counts, with the controller passing vehicle speed
in, and friction dropped from 0.23 to 0.01. One town curve came out "nearly perfect", though the
drive entered it already turning. Town
straights got worse, with the median steering wobble at 34 to 45 mph going from 0.30 to 1.20
degrees peak to peak.

To calm the straights I blended a linear model in below a curvature threshold and kept the table
above it. That failed twice, once with a wide blend and once with a narrow one. Lane wander went
from a 90th percentile of 0.14 m to 0.29 m, and excursions past 0.25 m went from 1.4 a minute to
5.2. Aaron said the engagements "felt like subtle bumper bowling". At 17 m/s the wobble on a straight road and an ordinary
lane-centring request ask for the same small curvatures, so any blend that picks by magnitude
starves the centring. The narrow blend first looked like an improvement in the feedforward
numbers, and that was the blend under-commanding.

What worked was to keep the plain table and deal with the sticking directly. A stiction
compensator watches for the column sitting still while the error persists, and adds a short pulse
to break it loose. The first version pulsed 115 counts after half a second and fired up to 16
times a minute on the highway, and the report from the road was that "the whole car would jerk". The second
version scales the pulse down with speed, waits 1.5 s between pulses, and fired 1.3 times a
minute. With the blend reverted and the pulse given a floor, route 00000271 on 2026-10-23 was the
first on which no stretch of the drive showed the one-per-second cycle. Aaron: "I felt like that was the best
drive yet. No faults, no buzz."

## The dither that froze the integrator

That build also carried a 20-count dither at 3.5 Hz, meant to keep the column from settling into
the band. The spectrum showed the dither reaching the motor, at 12 times the background on its
own line, and the column did not move with it.

It did harm somewhere else. Aaron drove the build to Chicago on 2026-10-24, three hours on the
first route, and I gave the data to four models for a blind review. Three of them found what I
had missed. openpilot's `controlsd` flags the steering as limited by safety whenever the newest
command and the car's reported output differ by more than 1 percent, and it freezes the integrator
while the flag is set. The reported output lags two frames. The dither's slope was 2.8 counts per
frame, so the two differed by 5.6 counts and the flag was up on 75 to 79 percent of frames. The
integrator was working about a fifth of the time. It had already been frozen 41 to 74 percent of
the time before the dither, for the same reason on ordinary command movement.

The fix removed the dither and changed the test for this platform: the output is limited only if
it matches none of the last three commands. It went onto the car remotely that night, at the
hotel. Integrator
freeze on the highway fell to between 8 and 14 percent, the ratio of delivered to requested
curvature in bends rose from 0.82 to 0.86 up to 0.91 to 0.99, and lane RMS above 24 m/s went from
0.257 m to 0.182 m.

On the drive home, on 73 mph interstate in the left lane, sloping left, the new build held the
lane no better than the old one. The Chicago routes had flattered it.
The like-for-like table for the trip, hands off with lane changes masked. The first two routes
are the drive out, the next two are Chicago expressways at 58 to 62 mph, and the last three are
the drive home at a median 73 mph:

| route | build | minutes | integrator frozen above 32 m/s | lane RMS, 26 to 32 m/s | lane RMS above 32 m/s | excursions over 0.5 m per hour |
|---|---|---|---|---|---|---|
| 00000277 | with dither | 172 | 78 % | 0.239 m | 0.264 m | 110 |
| 00000279 | with dither | 23 | 76 % | 0.174 m | 0.221 m | 44 |
| 0000027a | without | 32 | 10 % | 0.183 m | 0.171 m | 38 |
| 0000027b | without | 50 | 6 % | 0.194 m | 0.138 m | 58 |
| 0000027f | without | 50 | 9 % | 0.194 m | 0.279 m | 146 |
| 00000282 | without | 98 | 9 % | 0.261 m | 0.259 m | 101 |
| 00000284 | without | 136 | 9 % | 0.197 m | 0.240 m | 63 |

Aaron's report matched the table: "I honestly felt like it drove the same as the drive into
Chicago, like we didn't improve anything."

With the integrator working again, it wound up through long bends and took 7 to 15 seconds to unwind at the exit, leaving the car a median 0.51 m off centre
after 38 such exits in 5.4 hours. The integrator now unwinds three times as fast when the error
opposes it.

Road crown showed up on the same drive. In a left lane that slopes left, the car sat 0.26 m left
of centre on both builds, about 10 cm per degree of roll, with the controller error near zero and
the model's own path within 1 cm of the line the car drove. The offset is in the model's target,
upstream of the lateral controller.

## What the car runs now

As of 2026-10-31, on the fork's master:

- Feedforward from the curvature table in `opendbc/car/chrysler/susw_lateral.py`, counts 0 to 383
  against 0.0 to 2.40 per km. `latAccelFactor` stays at 1.20 for friction scaling and the ISO
  limit test, with friction at 0.01.
- In `latcontrol_torque.py`: proportional gain times 0.6, integrator unwind times 3, and the
  stiction pulse. The pulse triggers on a 0.3 s low-passed error of 0.30e-3 per metre, easing to
  0.20e-3 between 25 and 32 m/s, after the column has held for 0.5 s. It is 0.3 of the maximum,
  scaled down by (20/v)² above 20 m/s to a floor of 0.2, and it steps up by 0.05 each time a
  pulse fails to move the column, back to 0.3 at most. A pulse lasts 0.4 s at most and the next
  waits 1.5 s.
- `STEER_MAX` 383, 5 counts up and 6 down per frame. The steering-pressed threshold and the driver
  allowance both went from 160 to 220, with a 0.2 s debounce. Over 40 minutes of hands resting on
  the wheel on one route, the threshold at 160 flagged an override 1,932 times an hour, against 40
  at 220.

The first route on the current build, 00000293 on 2026-10-31 after the rebase, had 16 hands-off
minutes with one stretch of the one-per-second cycle, the integrator frozen 8 percent of the time
above 26 m/s, and no EPS fault. The two routes before it, 26 minutes engaged, fired about one
pulse a minute, and on each of them between 64 and 85 percent of pulses moved the column.

Still open: bends at 65 mph that deliver less than 0.85 of the requested curvature, two short
oscillations at 2 to 3 Hz in those 26 minutes, a table that tops out at 2.4 per km when highway
ramps show the car reaching 6 to 10, and the crown offset.

## For the next porter

- Plot steady-state curvature against command at two speed bands before you fit anything. If the
  bands agree, the EPS is taking position commands, and a lateral-acceleration feedforward will
  be wrong by the square of speed.
- torqued's live numbers are a stored aggregate over weeks, and for Chrysler openpilot does not
  use them. Fit offline, on one drive at a time.
- A blend that switches models by command size will starve lane centring at town speeds.
- A dither inside the hysteresis band does nothing to the column and can freeze the integrator
  through `steer_limited_by_safety`. Check how often that flag is set before you tune anything
  else.
- Compare builds on the same kind of road. A crowned left lane and a flat right lane give
  different answers for the same code.

---

Written by Claude, the coding agent on this project, from the project's tickets, route analyses
and repository history. The tuning sessions ran on Fable 5.1 and this page was written on Fable
5.2. Aaron did the driving. He has read the summary and has not reviewed every page.
