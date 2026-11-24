# CAN findings and the DBC

What is on the Renegade's buses, how each signal was proven, and the traps in the way. Part of
the [Renegade worklog](../README.md). The DBC itself is `opendbc/dbc/chrysler_susw.dbc` on the
`chrysler-smallwide` branch of the opendbc fork, and this page is the story behind it. Signal
names are the current DBC's. A few were renamed after the competition, and where that happened
the old name is given once. Current as of 2026-09-07.

> **Changed since, as of 2026-11-24.** `ABS_6.VEHICLE_SPEED` is 12 bits wide. The September DBC
> decoded 11, and the value wrapped above 34.8 m/s, about 78 mph; it is now `0|12@0+` with a range
> to 69.615 m/s. A capture on 2026-10-22 with LaneSense strength on high showed the same stock
> peak as medium, exactly 383 counts at 6 per frame. And openpilot now keeps the LaneSense on/off
> state itself, toggled on the 0x384 button edge, and sends `LKA_HUD_2` (0x547) to the cluster in
> the camera's place, so the LaneSense row of the consumer table describes the September design.
> The story is in [September to November](../porting-the-renegade.md#september-to-november).

| address | message | bus | rate | section |
|---|---|---|---|---|
| 0x1F6 | LKAS_COMMAND | CH | 100 Hz | [Steering](#steering) |
| 0x0DE | EPS_2 | CH | 100 Hz | [Steering](#steering) |
| 0x547 | LKA_HUD_2 | CH | 4 Hz | [Steering](#steering) |
| 0x384 | LANESENSE_BUTTON | CH | | [Steering](#steering) |
| 0x2FA | CRUISE_BUTTONS | C only | 50 Hz | [ACC](#acc-signals-which-are-on-can-c-only) |
| 0x103 | ACC_STATUS_1 | C only | 100 Hz | [ACC](#acc-signals-which-are-on-can-c-only) |
| 0x15C | ACC_COMMAND (was ACC_STATUS_2) | C only | 10 / 50 Hz | [ACC](#acc-signals-which-are-on-can-c-only) |
| 0x73C | ACC_HUD | C only | 1 Hz | [ACC](#acc-signals-which-are-on-can-c-only) |
| 0x0FC | ENGINE_1 | C and CH | | [ACC](#acc-signals-which-are-on-can-c-only) |
| 0x1F0 | ACCEL_PEDAL_DRIVER | C and CH | ~50 Hz | [ACC](#acc-signals-which-are-on-can-c-only) |
| 0x5A9 | GEAR_2 | CH | | [Body state](#body-state-from-a-parked-sweep-with-isolated-edges) |
| 0x200 to 0x3C0 | radar objects | fusion | 25 Hz | [The fusion bus](#the-fusion-bus) |

## The buses

| bus | where | rate | what |
|---|---|---|---|
| CAN C | body harness, radar, ABS, EPS, ACC, BCM | 500 kbps classic | 88 IDs parked, 107 on the road, about 59 percent load |
| CAN CH | camera side of the vehicle gateway | 500 kbps | 25 to 32 IDs forwarded from CAN C plus body traffic; about 48 IDs total |
| fusion | private camera-to-radar link | 500 kbps | 14 radar IDs at 25 Hz, 0x3C0 at 1 Hz, 0x7A9 at 10 Hz |
| CAN IHS | interior | 125 kbps | not tapped |

No CAN FD anywhere. The vehicle gateway (inside the BCM on MY2023) forwards a quarter to a third
of CAN C onto CH, with about 4.3 ms of latency measured by matching the same frames on both.

Roughly a third of the first DBC came from `fca_giorgio.dbc` (Alfa Giulia and Stelvio) and
`chrysler_cusw` (Cherokee KL) definitions that were re-checked against the captures, so it did not
start from nothing. Seventeen IDs overlap Giorgio, sixteen with identical DLC, and the Giorgio
definitions decode sane wheel speeds, steering angle, driver torque, gas, brake and RPM. The
steering command is the CUSW layout. CUSW's `STEERING` 0x1EE and `CLUSTER_1` 0x1F0 do not fit
(different DLC, CRC fails) and were dropped.

The checksum on every protected message is the FCA CRC-8 (polynomial 0x1D, init 0xFF, xor
0xFF), and 100 percent of checksum-bearing frames across every capture pass it.

## Steering

**`LKAS_COMMAND` 0x1F6.** CAN CH, 100 Hz, 4 bytes. Torque is 11 bits with a 1024 offset, the
control bit is byte 1 bit 4, and there is a 4-bit counter and a CRC. It passes the existing
Chrysler checksum on all 352,641 frames of the collection run.

- Stock torque range across all captures: -346 to +383. The EPS accepted 383.
- The stock camera moves torque by at most 6 counts per 10 ms frame in both directions, never
  exceeded in 673,913 frames, and never cuts to zero in one frame.
- Worst gap in the stock stream over a full route: 36.5 ms. The camera keeps sending torque zero,
  control bit clear, at 100 Hz with LaneSense off.
- Positive torque steers left. Left lane departures (cluster HUD yellow-left) show negative
  torque, right departures positive.
- The control bit means LaneSense is armed. It is set on 37 percent of frames, only 8.6 percent
  of those carry non-zero torque, and torque never occurs without the bit. It is 1 on 99.8
  percent of frames while the cluster shows green lanes, 100 percent while yellow, 0.7 percent
  while grey.
- Every capture behind the 383 figure was taken with LaneSense strength on medium. There is no
  strength signal decoded, so a sweep of the setting is needed to find the bit and the real
  ceiling.

**`EPS_2` 0x0DE.** CAN CH. `LKA_STATUS` takes only the values 0 and 2, and 2 agrees with the
camera's control bit on 99.95 percent of frames, so 2 means the EPS is armed. `LKA_FAULT`
was 0 on 100 percent of 674,018 frames before openpilot ever sent a command, and went to 1 three
times after. `DRIVER_TORQUE` is 11 bits, offset -1024, raw sensor counts with no physical unit
in the DBC; lock-to-lock parked saturates it. The field formerly called `UNKNOWN_TORQUE` is
`TORQUE_MOTOR`, the motor's own output (0.976 correlation with driver torque during a parked
sweep), about 0.22 to 0.24 times the LKAS command.

LaneSense arms at 15.86 to 16.01 m/s and drops at 14.88 to 14.91 m/s. The stock camera never
held its control bit below 14.86 m/s (33.2 mph) on either instrumented drive. The DBC records an
apparent EPS low-speed inhibit near 13.6 m/s and marks it unproven; it could be an assist-map
boundary. The "works down to 20 mph" impression is not in the data.

**`LKA_HUD_2` 0x547.** CAN CH, 4 Hz, the LaneSense cluster state. Byte 3 bit 6 is
`LANESENSE_DISABLED` (1 means disabled). Byte 6 is an enum: 2 grey (no lanes), 12 green (armed),
16 yellow-left, 20 yellow-right, plus bits 6 and 7 as a warning overlay. One trap: the panda's
`safety.h` invalidates any receive check declared below 10 Hz, so a message that really runs at
4 Hz must be declared at the 10 Hz floor or `controls_allowed` drops after one tick. Two competition entries
shipped that bug while each flagged it in the other's review.

**`LANESENSE_BUTTON` 0x384** byte 3 bit 6, momentary. The button is on the centre stack module,
which is on CAN C, so what reaches CH is a gatewayed copy.

## ACC signals, which are on CAN C only

**`CRUISE_BUTTONS` 0x2FA.** 50 Hz, 4 bytes, raw CAN C only. Byte 0 buttons, byte 1 low nibble
counter, byte 1 bit 7 distance-increase, byte 2 CRC-8 over bytes 0 and 1, byte 3 zero. The CUSW
message of the same name is 3 bytes.

| byte 0 | button |
|---|---|
| 0x01 | ACC on/off |
| 0x08 | resume |
| 0x10 | set / decel |
| 0x20 | accel |
| 0x40 | distance decrease |
| 0x80 | cancel |

The gap has two separate buttons, one to increase and one to decrease. Ninety presses on drive 2,
each 100 to 180 ms, with counts matching the narration exactly.

The trap: at the time, opendbc's Chrysler checksum handler assumed the CRC was the final byte. On
0x2FA it is byte 2 with byte 3 padding, so the DBC loaded and the native parser accepted 0 of
228,766 real frames, while the packer produced 0x3B where the car sends 0x56. A multi-agent review
of the three-route analyses caught it on 2026-08-23. The fix in this fork makes the handler aware
of the CRC's position, with no special case for the address, and the fixtures were written before
the CRC code was touched so the fix could not be bent to a wrong expectation. After the fix,
3,983,205 of 3,983,205 protected frames were accepted. A second trap in the same review: opendbc
only activates counter and checksum validation for signals literally named `COUNTER` and
`CHECKSUM`. `ABS_3` had them as `XCOUNTER` and `XCHECKSUM`, which look documented and enforce
nothing.

**`ACC_STATUS_1` 0x103.** 100 Hz. `ACC_ENGAGED` is byte 2 bit 5. Thirteen engaged intervals on
drive 2, each matching a narrated engage-or-resume to cancel-or-brake pair.

**`ACC_COMMAND` 0x15C**, named `ACC_STATUS_2` during the competition. Its rate changes with
state: 10 Hz disengaged and 50 Hz engaged. The INTERCEPT capture shows it arriving on the radar half, so it
is the radar's longitudinal command to the body side and the starting point for any future
longitudinal work. It is not copied to the fusion bus because it duplicates 0x103's engagement
state and has no consumer in the lateral port.

**`ACC_HUD` 0x73C.** 1 Hz plus on change, sent by the radar module. Byte 3 set speed in km/h,
byte 4 set speed in mph (0 when unset), byte 5 a five-second popup code (13 pre-enable, 14 ACC on,
15 set, 17 cancel), byte 7 bits 4 to 6 `ACC_STATE` (0 off, 1 ready, 2 engaged, 5 standby after
cancel). Byte 6's low six bits are a single eight-value enum that carries gap and lead together:
6 to 9 mean a lead is present at gaps 1 to 4, 10 to 13 mean no lead at gaps 1 to 4. Gap buttons
step by one within a bank, and lead acquire and loss jump by four. This message supplies
`cruiseState.available` and `cruiseState.speed`. It was found a day late because my first scans
stopped at ID 0x700, which is in the method notes below.

**`ENGINE_1` 0x0FC `THROTTLE_VIRTUAL`**, named `ACCEL_PEDAL` during the competition, is the
PCM's resolved throttle demand, driver or ACC: above zero on 97.5 percent of ACC-engaged frames.
Driver gas is `ACCEL_PEDAL_DRIVER` on 0x1F0, exactly zero across 2,596 s of settled ACC-engaged
driving and non-zero on 98.6 percent of a parked pedal press.

## Body state, from a parked sweep with isolated edges

| signal | location |
|---|---|
| gear | `GEAR_2` 0x5A9 byte 1 high nibble (1 P, 2 R, 3 N, 4 D, plus manual mode) on CH |
| driver door | 0x4B1 byte 0 bit 0; passenger byte 1 bit 7; rear doors undecoded |
| turn signals | 0x73E byte 2 low 2 bits (0 off, 1 right, 2 left, 3 hazards); a protected duplicate on 0x0FA byte 1 with a different layout and no hazards |
| parking brake | 0x256 byte 0 bit 3, 1 means engaged; also mirrored in `GEAR_2` and `LANESENSE_BUTTON`, agreeing on 100 percent of frames |
| blind spot | 0x5A4 byte 1 bit 4 right, bit 5 left; decoded but not consumed by the port |
| seatbelt | 0x257 byte 2 bit 5, 1 means unlatched; passenger belt moves no bit |
| wall clock | 0x73A, BCD |
| stock-ACC braking flag | 0x101 byte 0 bit 5 |

The parking brake was first read with the opposite polarity, because the parked sweep it came
from ran on-off-on and was read as off-on-off. The DBC comment records the correction with the
drive-away and end-of-route edges that settled it. The seatbelt polarity caught one competition
entry: with it inverted, and the parking brake read as set on every moving frame, its port could
not have engaged on any captured drive. Both judges matched the edges to the spoken markers.

Some things were left undecoded on purpose, because a guessed name misleads whoever reads the
DBC next: rear doors, headlamps, HUD state 22, the standby-only ACC enum values, and 0x0FD (four
frames per route, always `00 00 00 08 00 00`, each immediately after a door close).

## What CarState reads, and from where

| CarState field | message | panda bus | physical bus |
|---|---|---|---|
| `vEgoRaw` | `ABS_6.VEHICLE_SPEED`, guarded by the `ABS_1` wheel-speed mean at the ends of its range | 0 | CH |
| `steeringAngleDeg`, `steeringRateDeg` | `EPS_1`, sentinel frames dropped | 0 | CH |
| `steeringTorque`, `steeringTorqueEps` | `EPS_2.DRIVER_TORQUE`, `EPS_2.TORQUE_MOTOR` | 0 | CH |
| `steerFaultTemporary` | `EPS_2.LKA_FAULT` (temporary versus permanent is unproven; temporary is the conservative choice) | 0 | CH |
| `brakePressed` | `ABS_3.BRAKE_PEDAL_SWITCH` | 0 | CH |
| `gasPressed` | `ACCEL_PEDAL_DRIVER` | 0 | CH |
| `gearShifter`, `parkingBrake` | `GEAR_2` | 0 | CH |
| `leftBlinker`, `rightBlinker` | `STEERING_LEVERS` 0x73E | 0 | CH |
| `doorOpen`, `seatbeltUnlatched` | `DOORS`, `SEATBELT_STATUS` | 0 | CH |
| LaneSense on/off | `LKA_HUD_2.LANESENSE_DISABLED`, stale means disabled | 2 | camera side of CH |
| camera's control bit and counter | `LKAS_COMMAND` as forwarded (bus 0) and as sent (bus 2) | 0 and 2 | CH |
| `cruiseState.enabled` | `ACC_STATUS_1.ACC_ENGAGED`, and LaneSense on, and a fresh re-engage after any ACC-feed outage | 1 | copied from CAN C |
| `cruiseState.available`, `cruiseState.speed` | `ACC_HUD.ACC_STATE`, `ACC_SET_SPEED_KPH` | 1 | copied from CAN C |
| `buttonEvents` | `CRUISE_BUTTONS`, gap buttons only | 1 | copied from CAN C |

Bus 1 signals arrive only while the gateway is in INTERCEPT, and CarState treats a stale
`ACC_STATUS_1` as not engaged. The port transmits nothing on the cruise-button or HUD addresses,
because those buses cannot be written from the camera.

## The fusion bus

Fourteen radar burst IDs from 0x200 to 0x3A0 on a 0x20 stride at 25 Hz, 0x3C0 at 1 Hz with bytes
0 to 5 constant, 0x7A9 at 10 Hz as a two-byte keepalive. The competition winner decoded the object
list: 12-byte objects spread across slot pairs, with a track ID, range at 0.0625 m per count, an
inverse time-to-collision, a closing speed whose scale is uncertain, and an in-path flag. The
decode is in the DBC and is not consumed at runtime: the SUSW platform sets `radarUnavailable` and
the radar interface returns nothing.

The bus is point-to-point, 60 Ω live, terminated by the camera and the radar. The three whitelist
IDs and the rejected candidates were checked against six route artifacts for collisions before
anything transmitted (zero occurrences); the two heartbeat IDs, 0x5F0 and 0x5F1, were chosen
outside the radar's observed range.

## Fingerprinting

openpilot's CAN fingerprint uses only message IDs and DLCs, never values. A candidate is
eliminated the moment a packet arrives whose address is not in its dictionary or has a different
DLC. Elimination runs separately on bus 0 and bus 1, and a single surviving candidate on either
bus after about a second of packets wins; about two seconds without resolution means dashcam mode.
The port ships two dictionaries, a bus 0 CH census and a bus 1 fusion census, as alternatives,
because every ID you trim becomes an ID that can kill your own match.

The port has no firmware-version table, so it relies on CAN matching. Chrysler's proprietary DID
0xF132 returns a negative response on every ECU, but the standard DID 0xF181 works on 29-bit
normal-fixed addressing and the comma reads it on every boot: EPS at 0x18DA30F1 answers
`S2FI03FC00`, ABS at 0x18DA28F1, cluster at 0x18DA60F1. That is enough to build a firmware table
later. The comma transmits about 230 UDS frames in the first three seconds of every start (on CH
and on fusion) and nothing for the rest of the route.

## Method notes

- Sync recorders on a shared physical wire. The comma's bus 1 and the CANsub's channel 2 are the
  same fusion pair, so exact (address, payload) matches fit the clocks: 589,047 matches on drive 3,
  +27.7 ppm drift, 2.6 ms median residual. Steering-sweep markers and value-domain correlation
  were the fallback and never needed.
- Scan the whole ID space. A cap at 0x700 hid `ACC_HUD` for a day and nearly produced a tap on a
  fourth bus.
- In BYPASS the gateway's bus 0 and bus 2 are one wire. Every side-of-origin claim from a BYPASS
  capture is false. Direction attribution needs INTERCEPT.
- Treat narration as a witness and cross-examine it against CAN edges. The MARK/RESULT
  protocol (announce, wait two seconds, act, announce the result, ten seconds of silence) is what
  makes a negative result believable.
- Word-level timestamps for the narration came from five transcription engines reconciled by a
  text model that knew the drive's vocabulary, then force-aligned. Median disagreement between
  the timing sources was about 220 ms.
- One edge is too little to name a bit. Leave it undecoded until a second one agrees.

## Provenance

Written by Claude, the coding agent on this project (drafted on Fable 5.1, revised on Fable 5.2),
from the session transcripts, tickets and repository history. Aaron did the bench and car work.
He has read the summary and has not reviewed every page. "My first scans" above refers to the agent's own capture filter.
