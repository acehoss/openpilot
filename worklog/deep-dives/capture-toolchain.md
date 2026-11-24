# The capture toolchain

This page is for anyone repeating these captures with the same instruments. It covers what each
instrument gives you, how two recorders were fitted to one clock, and the failures that cost
hours: a TLS version mismatch, an IPv6 lookup stall, a send thread that dies without a word, and a
USB cabling rule that looks like two dead pandas. Part of the [Renegade worklog](../README.md).
The tool sources are in the private metarepo, so this page says what they do and what they
taught.
Current as of 2026-09-07.

## Instruments

| instrument | where | what it gives |
|---|---|---|
| comma four | camera connector via a splitter | route logs with video, CAN CH (bus 0 and 2), fusion (bus 1), openpilot state |
| CANsub.4 | four channels, at the gateway taps or on the bench | hardware timestamps, error frames, ACK control per channel |
| Red Panda (gateway) | inline at XY005A, USB to a laptop | all three gateway buses with side-of-origin in INTERCEPT, gateway status |
| Teensy interposer (retired) | at the radar connector | raw waveform mirrors of CAN C and fusion for the CANsub |
| AlfaOBD | diagnostic port | DTC scans before and after every session |

The panda has no hardware timestamps, cannot see error frames at all, and overloads its bus field
(+128 for its own transmit echo, +192 for rejected). The substitute is its per-bus health
counters: total received, lost, errors, bus-off and last error. Its USB batching measured in the
car:

| measurement | value |
|---|---|
| inter-batch spacing | p50 0.48 ms, p99 2.13 ms, max 12.3 ms |
| unique frames per batch | about 1.24 |
| agreement with the CANsub over an identical 120 s window | within 63 frames, 0.02 percent |

Good enough for everything except latency measurement, which is what the CANsub is for.

## Syncing recorders

The comma and the CANsub see the same physical fusion wire (comma bus 1 at the camera, CANsub
channel 2 at the gateway), so exact (address, payload) matches fit one clock to the other:

| drive | matches | drift | residual median / p99 / max |
|---|---:|---:|---|
| 2026-08-21 | 112,475 | +48.9 ppm | 2.5 / 5.5 / 10.7 ms |
| 2026-08-22 | 589,047 | +27.7 ppm | 2.6 / 7.6 ms |
| 2026-08-23 | 603,592 | +25.7 ppm | 2.7 / 5.6 / 9.4 ms |

The sync tool refuses a fit under 1,000 matches or with a residual p99 over 20 ms. The residual
is the panda's USB batch jitter, since the CANsub stamps frames in hardware. A cross-check on a bus not used for the fit
(the 25 to 32 CAN C IDs the vehicle gateway forwards onto CH) gives a median of -4.3 ms, which is
the vehicle gateway's own forwarding latency, CAN C leading CH.

Raw CAN C then gets injected into the route's rlogs as bus 3. The merge keeps the original rlog
and always rebuilds from it, so re-runs never double-inject. Cabana shows body, fusion, raw CAN C
and video on one timeline. The earlier plan, three lock-to-lock steering sweeps parked before and
after each script as a value-domain sync marker, was never needed.

Two Cabana notes. Remote playback appears to update CAN once every 30 s because video streams from
the small qcamera files while CAN comes from the 40 to 70 MB rlogs, one segment at a time; play
from a local copy with an absolute data directory. And the video view needs a real terminal for
its GL context; launched from an agent's shell it dies on a texture assertion.

## The CANsub.4 from Python

The vendor's Python package fails out of the box on modern macOS, and every failure mode in it is
silent. The fixes, grouped by what they touch.

### Getting connected

- Firmware API 03.00 drops any TLS connection whose ClientHello offers TLS 1.3. Python 3.12 on
  OpenSSL 3.6 offers it by default. Clamp both the websocket and REST contexts to TLS 1.2 maximum.
  With 1.2 forced the device certificate validates fully, so verification stays on.
- An `AF_UNSPEC` lookup of the device's `.local` name stalls a flat 5.01 s waiting for a AAAA
  record that never comes. Each channel open makes about six REST calls, so opening three
  channels cost 16 s. Disabling IPv6 in the HTTP library drops it to 1.5 s.
- Pinning the IP must keep the hostname for SNI and certificate matching, because the device
  certificate has DNS names only. Two patches: address resolution for REST and the socket connect
  for the websocket, which hands a hostname straight to C.
- The device serves nine concurrent TLS connections and each open channel costs two (websocket
  plus a REST keep-alive). Four channels is eight of nine and the tool's own pooled client held the
  ninth. An earlier "three connection limit" claim was wrong and Aaron said so at the time; the
  fix is `Connection: close` on the API client plus retries, since slots from a killed process come
  back on their own.

### Keeping the capture alive

- Host-paced sending does not pace anything. Send only queues, the library batches onto the
  websocket, and the device drains at bus rate. That saturated the link and killed the library's
  send loop thread on a socket write timeout, raising nothing to the caller. The receive path can
  die the same way. The tool polls the device's own frame counters on a monitor thread and
  reconciles at end of run. A capture that stops halfway through a drive and says nothing costs
  the whole drive, and you will not know until you are back at the desk.
- A frame sent with `is_rx=False` is dropped by the device (the encoder sets a protocol transmit
  flag). Leave the default.
- A channel that has gone error-passive from ACK starvation can wedge the vendor library on the
  next send. Two more wedges on the bench: under a 50 Hz probe (10 Hz was enough for every row),
  and when the device receives a forwarded copy of a frame it just sent on another channel with
  the same payload if the ID is 0x73C. We never explained that last one and only worked around
  it.
- Control ACK per channel. A global setting would put an ACKing node on the diagnostic port at
  an unconfirmed bit rate, where it would inject error frames at the instrument cluster.
- The hardware transmit scheduler rejects periods under 1 ms, so loopback transmit caps at
  1000 fps.

### Reading the timestamps

- The device's host-side timestamp lies at channel open: the websocket buffers about 0.9 s of
  frames and dumps them in one burst. Compare on the device timestamp, never the host one. This
  produced one false "0.74 percent panda frame loss" alarm.
- Loopback bench numbers for the tool: 56,802 consecutive sequence-numbered frames at 1000 fps
  over 57 s with zero drops, spacing 1000 µs ± 2.1 µs, host lag median 3.3 ms, p99 10.2 ms.
  Parquet output is about 12 bytes per frame, so a 17-minute three-channel route is about 45 MB.

## The Red Panda from a Mac

- A USB-C-plug-to-USB-A-plug cable will not power a panda from a USB-C host. The C plug presents
  as a device, so the Mac takes the sink role and never sources VBUS. Use a C-to-A-female adapter
  and an A-to-A data cable into the panda's USB-A receptacle. We wrote off two pandas as dead
  before working this out.
- Shop-bought pandas carry a RELEASE bootstub with no debug fallback. A self-built firmware
  flashes "successfully", the device resets, comes back reporting bootstub mode, and the health
  call returns nonsense versions because the flasher is answering. Plain flashing can never fix
  it. Recover by resetting into the bootloader, using the DFU class to replace the bootstub, then
  flashing. No physical DFU button needed. The version string flips to `-DEBUG`.
- `Panda.reconnect()` and `PandaDFU.close()` both hang on this Mac in an agent session. Use a
  fresh process with `reconnect=False` and wait for enumeration, wrap long calls in an outer
  timeout, and redirect output to a file.
- Set SILENT before disabling the heartbeat, and disable power save. Otherwise power save turns off
  CAN interrupts on the non-main buses mid-capture and you lose bus 1 and one CAN C bus with no
  error.
- The set-bitrate handler ignores an unsupported rate without complaint. Read it back.
- In BYPASS the gateway's bus 0 and bus 2 are one physical segment. Expect exact duplicates, and
  make no side-of-origin claim.
- The USB handle takes about 4 s to free after a status logger stops; a reset issued sooner can
  return without resetting.

The comma's own panda API from the device needs its venv Python (the manager's interpreter lacks
`usb1`), and `Panda(serial, claim=False)` coexists with the running `pandad`.

## The comma four

- Install the fork over SSH, never the setup-UI installer, which requires an uninstall that wipes
  `/data` (params, SSH keys, Wi-Fi, routes).
- Repoint `.gitmodules` at your forks. Upstream's relative URLs (`../../commaai/opendbc.git`)
  resolve to commaai's repositories against any origin, so the device would fetch upstream's
  opendbc and panda and never see the fork's commits. One-line fix, found on the first clone.
- Clone with the device offroad. The driving stack holds about 2.1 GB of the 3.6 GB, and the
  git-LFS checkout runs out of memory, leaving an empty index with every file a staged deletion.
  Recover with `git reset --hard HEAD` and a submodule re-init. `git restore` does not do it.
- `/data/safe_staging/merged` is an overlay mount; unmount it lazily before removing the
  directory.
- Push every fork branch before the device clones or updates. An unpushed submodule commit fails
  with `not our ref`.
- Force an update with a HUP to the updater, but bracket the pattern (`"[s]ystem.updated"`) or
  the `pkill` matches your own SSH command line and kills your shell.
- Every update overwrites local uncommitted edits. Commit or re-apply.
- Boot to a running build is 6.5 minutes (scons plus model compile). The stock RELEASE-bootstub
  recovery for the comma's internal panda runs inside `pandad` with no intervention.
- Routes rotate off the device at about 89 percent disk. Request an upload right after any fault
  drive; one fault's full logs were lost this way.
- Route segments upload out of order; a stable count is not "complete". Poll until three
  consecutive checks show no missing files.

## Narration

In-car narration is the only way to label events the CAN bus does not announce (what Aaron
pressed, what the cluster showed). The transcription pipeline runs five engines (a cloud model,
Gemini, WhisperKit large-v3-turbo, Parakeet v3, whisper.cpp large-v3), reconciles them with a text
model that knows the drive's vocabulary and marker protocol, then force-aligns with a CTC model
for per-word timestamps with a score, a spread between four independent timing estimates, and
flags. Segmentation is the union of a neural voice detector and an energy detector; either alone
misses part of a windy route. Final counts: 1,700 words at 220 ms median spread on the collection
run, 1,312 at 234 ms on drive 3. A July route with the windows down had 67 percent of words
flagged. Local Parakeet alone produced garbled text on short clips; per-burst clips sent to a
cloud model with a domain vocabulary prompt cost pennies per route.

The competition brief told entrants to treat the transcript "as a witness to be cross-examined
against CAN edges, not as ground truth." The judges did, matching the CAN edges to the spoken
markers.

## In-car sessions

Each capture runs in its own named window of a tmux session on a dedicated socket, one window per
instrument, so Aaron can attach from the driver's seat and watch the live status lines. Captures
stop with Ctrl-C sent to the window, never by killing the pane; both tools write their output
files on SIGINT. Every session starts with a DTC scan and ends with one. A preflight mode runs the
live dashboard without writing any files, so you can confirm the capture works after the car
starts and before the route begins. The dashboard shows the device's own bus load next to seconds
since the last frame, which is the pair that separates an idle bus, a miswired pair, and a stream
that died.

## Provenance

Written by Claude, the coding agent on this project (drafted on Fable 5.1, revised on Fable 5.2),
from the session transcripts, tickets and repository history. Aaron did the bench and car work.
He has read the summary and has not reviewed every page.
