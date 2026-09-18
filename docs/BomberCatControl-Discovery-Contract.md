# BomberCatControl Discovery Contract

**Status:** Normative — v1.0
**Applies to:** every firmware image developed by Electronic Cats for the BomberCat
board that mounts the `BomberCatControl` module.
**Audience:** firmware developers (device side) and host-tool developers (CLI / GUI / TUI).
**Supersedes:** the informal notes in `vendor/bombercat-tools/docs/protocol.md` for the
subset of commands covered here (`ping`, `info`, `identify`, and the firmware hook).

> Written for: firmware and host-tool engineers who need a single source of truth for
> discovery/handshake behavior across all BomberCat firmware.

This document defines the **discovery contract**: the minimal control-plane interface
and behavior that *every* BomberCat firmware MUST implement so that any conforming host
— the `bombercat` CLI, the EMVy desktop GUI, the EMVy TUI, or a third-party tool — can
discover the board, identify it, and dispatch its firmware-specific function **identically**,
regardless of environment.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**,
**SHOULD NOT**, **MAY**, and **OPTIONAL** are to be interpreted as described in RFC 2119.

A firmware image that satisfies every **MUST** in this document is **contract-compliant**.
A firmware image that fails any **MUST** is **non-compliant** and MUST NOT claim
`has_repl = true` in the firmware registry (`vendor/bombercat-tools/modules/core/firmwares.py`).

---

## 1. Terminology

| Term | Meaning |
|---|---|
| **Device** | A BomberCat board running one firmware image. |
| **Host** | Any program that speaks this protocol over USB-serial (CLI, GUI, TUI, library). |
| **BomberCatControl** | The device-side module that implements the control-plane REPL defined here. Mounting it is what makes a firmware discoverable. |
| **Control plane** | The line-based ASCII command/response channel defined here. It carries control commands and events **only** — never relayed APDUs or payment data. |
| **Command** | One `\n`-terminated request line sent host → device. |
| **Reply** | One or more `\n`-terminated response lines device → host, ending in exactly one terminator. |
| **Terminator** | The `+OK`/`-ERR` line that ends a reply. |
| **Data line** | A `:key value` line inside a reply. |
| **Hook** | The single firmware-specific command each image contributes, invoked through the BomberCatControl dispatch hook (§6). |
| **Handshake** | The `ping` → `+OK bombercat` exchange used for discovery (§5). |

---

## 2. Transport layer (REQUIRED)

All numbered items are **MUST** unless stated otherwise.

1. The device exposes a **USB CDC-ACM** serial interface.
2. Line speed is **115200 baud**, 8-N-1. The device MUST accept this rate; it MUST NOT
   require any other rate for the control plane.
3. Character encoding is **7-bit ASCII**. Bytes ≥ 0x80 MUST NOT appear on the control
   plane. Hosts decode with ASCII and replace undecodable bytes; a device that emits
   non-ASCII on the control plane is non-compliant.
4. **Line framing:** every command and every reply line is terminated by a single `\n`
   (0x0A). A leading/trailing `\r` (0x0D) is tolerated by hosts and MUST be ignored;
   the device SHOULD NOT depend on `\r`.
5. **Line length:** no single control-plane line SHALL exceed **4096 bytes** including
   its terminator. Hosts cap a single read at 4096 bytes (`_MAX_LINE_BYTES`); a device
   that emits an unterminated stream longer than this will be read as a truncated line
   and MUST NOT rely on longer lines being reassembled.
6. **USB identity:** the device SHOULD enumerate with **VID `0x1209` / PID `0x005E`**
   (pid.codes, BomberCat application personality). A device that enumerates with a
   different VID/PID is still discoverable (hosts fall back to handshaking every
   candidate port), but discovery is faster and safer when the canonical identity is
   used. USB identity only **tags** a candidate port; it is never sufficient proof of
   compliance — the handshake (§5) is (see §7).
7. **Request/response discipline:** the control plane is strictly synchronous. For each
   command the device MUST emit exactly one reply ending in exactly one terminator
   (`+OK`/`-ERR`). The device MUST NOT emit an unsolicited terminator. Unsolicited
   `:key value` **event** lines are permitted only where a specific command has armed a
   stream (e.g. a capture/monitor mode); discovery commands (`ping`, `info`, `identify`)
   MUST NOT arm any stream.

---

## 3. Wire format (REQUIRED)

### 3.1 Command grammar

```
command   = verb *( SP arg ) LF
verb      = 1*(ALPHA / DIGIT)          ; case-insensitive on receipt (§5.1)
arg       = *(VCHAR / SP-in-tail)      ; the last arg MAY contain spaces
LF        = %x0A
```

The device MUST treat the verb case-insensitively (see §5.1). Arguments are
positional; a command whose final argument is free text (e.g. `set ssid My Network`)
takes the entire remainder of the line as that argument.

### 3.2 Reply grammar

```
reply       = *data-line terminator
data-line   = ":" key SP value LF
terminator  = ok-line / err-line
ok-line     = "+OK" [ SP message ] LF
err-line    = "-ERR" SP message LF
key         = 1*(ALPHA / DIGIT / "_")
value       = *VCHAR-and-SP           ; up to end of line
message     = *VCHAR-and-SP
```

Rules:

1. A reply is zero or more **data lines** followed by **exactly one** terminator.
2. A line whose first character is **not** `:`, `+`, or `-` is **device log noise**
   and MUST be silently ignored by hosts. Devices MAY emit such noise (debug prints);
   it never counts as part of a reply. Hosts MUST NOT treat noise as an error.
3. `+OK` MAY carry a message; `-ERR` MUST carry a human-readable message.
4. Data-line keys within a single reply SHOULD be unique. If a key repeats, the host
   keeps the **last** occurrence (dictionary semantics).
5. The device MUST NOT interleave data lines of two different replies. Because the
   channel is synchronous (§2.7) this cannot happen when the device answers one command
   at a time.

### 3.3 Host parsing model (informative, but binding on hosts)

A conforming host parses a reply into a three-field result:

```
Response(ok: bool, message: str, data: dict[str, str])
```

- `ok`   — `true` for `+OK`, `false` for `-ERR`.
- `message` — the text after the marker (may be empty for `+OK`).
- `data` — the accumulated `:key value` lines.

The host reads reply lines until a terminator or until its deadline (§5.3). This model
is the same one implemented by `DeviceLink.command()` in
`vendor/bombercat-tools/modules/core/bombercat.py` and MUST be reproduced by every host.

---

## 4. Mounting BomberCatControl (REQUIRED)

To be discoverable, a firmware MUST **mount** the BomberCatControl module in its
`setup()` and **pump** it from its main `loop()`. Mounting establishes:

1. The four REQUIRED commands of §5/§6: `ping`, `info`, `identify`, and the firmware hook.
2. The wire format of §3.

Mounting requirements:

1. The module MUST be reachable **without any prior command**. In particular, `ping`
   MUST succeed on a freshly enumerated device before any configuration, arming, or
   card presence. Discovery MUST NOT require a tag, reader, WiFi association, or any
   external state.
2. The device MUST NOT print a boot banner that begins with `:`, `+`, or `-`. The
   `+OK bombercat` string is the **reply** to `ping`, never a boot print. (A banner that
   shadows the handshake reply is a conformance failure — see the `banners=()` note for
   NFCGate in the firmware registry.)
3. The module MUST drain/settle so that the **first** command a host sends after opening
   the port reads its own reply, not stale boot output. Hosts assist by sleeping briefly
   and flushing the input buffer on open (§5.4), but the device MUST NOT emit a terminator
   except in response to a command.
4. Relay/firmware-specific actions (the hook, and any of `run`/`stop`/`reboot` a firmware
   offers) MUST be provided to the module as **callbacks** from the sketch, so the
   BomberCatControl core carries no firmware-specific or radio-stack dependency.

---

## 5. Required command: the handshake (`ping`)

`ping` is the discovery primitive. It is the one command every host issues first and the
one that reconciles the GUI, the TUI, and the CLI.

### 5.1 Signature and case reconciliation (the PING/ping rule)

- **Canonical form:** `ping` (lowercase).
- **Reconciliation rule (REQUIRED):** the device MUST treat the verb
  **case-insensitively**. `ping`, `PING`, and `Ping` MUST all be accepted and produce
  the identical reply. This single rule reconciles the two historical dialects:
  - the `bombercat` CLI / `DeviceLink` issues **`ping`** (lowercase);
  - the EMVy passthrough reader (shared by both the EMVy **GUI** and the EMVy **TUI**,
    `emvy/readers/bombercat.py`) issues **`PING`** (uppercase).

  Because the reader module is shared, the GUI and TUI are byte-for-byte identical on
  the wire; the only remaining divergence is *case* against the CLI. Making the verb
  case-insensitive on the device removes that divergence permanently and is the
  contract's mechanism for GUI/TUI/CLI parity. Hosts SHOULD send the canonical lowercase
  `ping`, but MUST NOT rely on case being significant.

### 5.2 Request / response

| Direction | Bytes on the wire |
|---|---|
| Host → device | `ping\n` (or `PING\n`) |
| Device → host | `+OK bombercat\n` |

- The reply MUST be a `+OK` terminator whose message **contains the token `bombercat`**
  (case-sensitive token, lowercase). The host handshake predicate is:
  `response.ok AND "bombercat" in response.message`.
- The reply MUST NOT include data lines. `ping` carries no payload.
- The reply MUST arrive as the first terminator after the command, with no intervening
  terminator.

### 5.3 Timeout behavior (REQUIRED)

- Discovery uses a **short per-attempt timeout**. The reference discovery timeout is
  **1.0 s** per port (`discover_devices(..., timeout=1.0)`); the default interactive
  `DeviceLink` per-readline timeout is **2.0 s**.
- The device MUST answer `ping` within **1.0 s** of receiving the command line under
  normal operation. A device that cannot answer `ping` within 1.0 s is non-compliant
  (it will be missed by fast discovery and reported as "present but not answering").
- Hosts compute a deadline and read reply lines until the terminator or the deadline.
  A readline that returns nothing (a timeout tick) is not an error; the host keeps
  waiting until the overall deadline. Reaching the deadline with no terminator is a
  timeout and MUST surface as a discovery **miss**, not a crash.

### 5.4 Buffer / boot-banner handling (REQUIRED of hosts)

On opening a port, before the first command, a host MUST:

1. Wait a short settle interval (reference: **0.3 s**) for the CDC to come up and any
   autostart/boot log to drain.
2. Flush the input buffer (`reset_input_buffer()`).
3. Before **each** command, flush stale input again (strict request/response), then
   write the command and flush the output.

This guarantees the handshake reply is matched against the `ping` command that produced
it and not against boot noise. Devices support this by never emitting a terminator
except in reply to a command (§2.7, §4.2).

### 5.5 Error handling (REQUIRED)

| Condition | Host behavior | Device requirement |
|---|---|---|
| No reply before deadline | Treat as **miss** (device not a compliant BomberCat on that port). MUST NOT raise to the user as a fatal error during discovery. | Answer within 1.0 s. |
| `+OK` without `bombercat` token | Treat as **miss** (some other REPL). | MUST include `bombercat` in the `ping` message. |
| `-ERR …` to `ping` | Treat as **miss**. | `ping` MUST NOT fail; it takes no arguments and has no failure mode. |
| Write timed out (device not draining USB-OUT) | Surface a clean transport error ("device did not accept … it may be wedged or not running the firmware"), skip the port. | Keep the USB-OUT endpoint drained. |
| Serial/OS error (port vanished, permission) | Skip the port, continue discovery. | n/a |

Hosts MUST NOT open a port that carries no BomberCat USB tag *and no candidate hint*
purely to guess, when tagged candidates exist — opening a port can reset some MCUs.
(See the discovery algorithm, §7.)

### 5.6 Environment-specific considerations that MUST be abstracted away

The following differences between environments MUST NOT change the observed handshake
result. Each is neutralized by a rule above:

- **Verb case** (`PING` vs `ping`) → §5.1 case-insensitivity.
- **Line endings** (`\n` vs `\r\n`) → §2.4 `\r` ignored.
- **Boot banners / autostart logs** → §5.4 settle + flush, §3.2 noise ignored.
- **Slow CDC enumeration** → §5.3 deadline-based reads, §5.4 settle interval.
- **USB VID/PID reported by stock Arduino profiles** (`2341:005E`) vs the BomberCat
  identity (`1209:005E`) → §7 candidate tagging + handshake confirmation.
- **Which host process asks** (CLI vs GUI vs TUI) → all use the same command, predicate,
  timeouts, and flush discipline defined here. A conforming firmware cannot tell them
  apart and MUST behave identically.

---

## 6. Required commands: `info`, `identify`, and the firmware hook

### 6.1 `info` (REQUIRED)

Reports a machine-readable snapshot so a host can name the firmware without guessing.

| Direction | Wire |
|---|---|
| Host → device | `info\n` |
| Device → host | one or more `:key value` data lines, then `+OK\n` |

Requirements:

1. `info` MUST emit at least the key **`fw_name`** — the firmware's stable slug
   (e.g. `nfcgate`, `detecttags`, `magspoof`), matching an `id` in the firmware registry.
   This is what lets a host identify the image directly instead of sniffing a boot banner.
2. `info` SHOULD also emit **`fw`** — the firmware version string (e.g. `0.9.7`).
3. Additional keys are firmware-specific and OPTIONAL (e.g. `role`, `state`, `ssid`).
   Keys not understood by a host MUST be ignored, not rejected.
4. `info` MUST terminate with `+OK`. It MUST NOT require arguments.
5. `info` is **read-only**: it MUST NOT change device state.

Example:

```
info
:fw_name nfcgate
:fw 0.9.7
:role reader
:state idle
+OK
```

### 6.2 `identify` (REQUIRED)

Lets a user physically tell one board from several.

| Direction | Wire |
|---|---|
| Host → device | `identify\n` |
| Device → host | `+OK\n` |

Requirements:

1. `identify` MUST return its terminator **immediately** (within the discovery timeout,
   §5.3); the visual indication (LED blink, ≈2 s) MUST run asynchronously from the
   sketch loop and MUST NOT block the control plane.
2. `identify` MUST be non-destructive and idempotent: calling it MUST NOT change any
   persisted or operational state.
3. A firmware that has no controllable indicator MUST still accept `identify` and reply
   `+OK` (no-op) so the command is universally safe to issue. It MAY additionally omit
   the `identify` capability from its registry entry, but MUST NOT reply `-ERR`.

### 6.3 The firmware hook (REQUIRED)

Every firmware contributes **exactly one** firmware-specific command — its *hook* —
through the BomberCatControl dispatch mechanism. The hook is what makes the firmware
useful beyond discovery (e.g. `run` for NFCGate, `tags` for DetectTags, `mag` for
magspoof).

Requirements on the hook:

1. **Registration:** the hook MUST be registered with BomberCatControl as a **callback**
   supplied by the sketch (§4.4). The core MUST route any verb it does not itself handle
   (i.e. not `ping`/`info`/`identify` and not another built-in) to the registered hook.
2. **Reply shape:** the hook MUST obey §3 exactly — zero or more `:key value` data lines
   followed by exactly one `+OK`/`-ERR` terminator. This is the property that lets a host
   dispatch *any* firmware's function through the same `command()`/`Response` code path.
3. **Unknown verb:** if the device receives a verb that is neither a built-in nor handled
   by the hook, it MUST reply `-ERR unknown command <verb>` (single terminator). It MUST
   NOT stay silent (which would force the host to wait out its deadline) and MUST NOT
   emit a bare `+OK`.
4. **Arguments:** the hook defines its own positional arguments per §3.1. If a required
   argument is missing or malformed, it MUST reply `-ERR <reason>` rather than crash or
   hang.
5. **Non-blocking long actions:** a hook that starts a long-running action (relay,
   emulation) MUST return a terminator promptly (`+OK accepted` / `-ERR <reason>`) and
   expose progress through a separate pollable command (e.g. `status`) or an armed event
   stream — it MUST NOT hold the control plane for the duration of the action. (This
   mirrors `run` becoming non-blocking; see `DeviceLink.run()`.)
6. **Capabilities:** the hook's function MUST be reflected as a capability in the firmware
   registry entry so hosts can advertise/refuse it (`CAP_*` in `firmwares.py`).

---

## 7. Discovery algorithm (REQUIRED of hosts, defines the device's obligations)

Discovery is the composition of USB tagging and the handshake. Every host MUST implement
the following, and every device MUST behave such that this algorithm classifies it
correctly.

1. **Enumerate** serial ports; obtain each port's USB VID/PID when the OS reports one.
2. **Tag** as *candidates* the ports whose (VID, PID) is a known BomberCat identity
   (`1209:005E` and the documented alternates, plus `2341:005E` for stock-Arduino-profile
   builds, plus any `BOMBERCAT_VID`/`BOMBERCAT_PID` override). Tagged ports are probed
   first.
3. If **any** port is tagged, probe **only** tagged ports (do not open untagged ports —
   opening can reset an MCU). If **no** port is tagged, every candidate port MAY be probed.
4. **Handshake** each probed port: open (with settle + flush, §5.4), send `ping`, apply
   the predicate `ok AND "bombercat" in message` within the discovery timeout (§5.3).
5. **Classify** each port:
   - handshake succeeds → a **confirmed** BomberCat (the only state that earns the `✓` in
     `device list` and counts for auto-detection).
   - tagged by USB but handshake fails → **present but not serving the REPL** (host tells
     the user the board is there but its firmware isn't answering — the device is
     non-compliant or mis-flashed).
   - neither → not a BomberCat.
6. **Numbering / selection** (`resolve_port`): `--port` wins as-is; `--device/-d <id>`
   selects a stably numbered confirmed device without handshaking the others; otherwise
   auto-detect — exactly one confirmed device is used, zero or many is an error that tells
   the user to pass `-d`/`--port`. `--port` and `--device` are mutually exclusive.

A device's only obligations here are: enumerate with a recognizable identity when it can
(§2.6), and answer the handshake within the timeout (§5). If it does both, it is discovered
identically by every host.

---

## 8. Conformance

### 8.1 Compliance checklist

A firmware is contract-compliant **iff** all of the following hold. Each maps to a MUST above.

- [ ] C-1  Exposes USB CDC-ACM at 115200 8-N-1; control plane is ASCII, `\n`-framed. (§2)
- [ ] C-2  No control-plane line exceeds 4096 bytes. (§2.5)
- [ ] C-3  Synchronous: exactly one `+OK`/`-ERR` per command; no unsolicited terminators. (§2.7, §3.2)
- [ ] C-4  Lines not starting with `:`/`+`/`-` are the only permitted log noise. (§3.2)
- [ ] C-5  BomberCatControl is reachable before any configuration/state; no `:`/`+`/`-` boot banner. (§4.1, §4.2)
- [ ] C-6  `ping` (case-insensitive) → `+OK bombercat`, no data lines, within 1.0 s. (§5.1–§5.3)
- [ ] C-7  `PING`, `Ping`, and `ping` produce the identical reply. (§5.1)
- [ ] C-8  `info` → `:fw_name <slug>` (+ recommended `:fw`) then `+OK`; read-only. (§6.1)
- [ ] C-9  `identify` → `+OK` immediately; indication is async; never `-ERR`. (§6.2)
- [ ] C-10 Exactly one hook command, registered as a callback, reply-shaped per §3. (§6.3.1, §6.3.2)
- [ ] C-11 Unknown verb → `-ERR unknown command <verb>` (never silent, never bare `+OK`). (§6.3.3)
- [ ] C-12 Long hook actions return a terminator promptly and report progress out-of-band. (§6.3.5)
- [ ] C-13 Registry entry sets `has_repl = true` and declares its `CAP_*` capabilities. (§6.3.6, §1)

### 8.2 Conformance test vectors

A host-side conformance harness MUST send each stimulus and assert the response. `<t>`
is a fresh port opened per §5.4.

| # | Stimulus | Required response | Asserts |
|---|---|---|---|
| T-1 | `ping\n` | `+OK` whose message contains `bombercat`, ≤ 1.0 s, 0 data lines | C-6 |
| T-2 | `PING\n` | byte-identical reply to T-1 | C-7 |
| T-3 | `info\n` | `:fw_name <non-empty slug>` present; ends `+OK` | C-8 |
| T-4 | `info\n` (repeat) | identical `fw_name`; device state unchanged (verify via T-1 still works) | C-8 |
| T-5 | `identify\n` | `+OK` within 1.0 s | C-9 |
| T-6 | `zzznotacommand\n` | `-ERR unknown command zzznotacommand` | C-11 |
| T-7 | `<hook> <bad-args>\n` | `-ERR <reason>` (single terminator, no hang) | C-3, C-6.3.4 |
| T-8 | open port, wait 0.3 s, flush, then T-1 | T-1 passes on the first command (no stale banner consumed) | C-5 |
| T-9 | send `ping\n`, read until terminator; assert exactly one terminator seen | pass | C-3 |

A firmware that passes T-1 … T-9 and satisfies the §8.1 checklist is certified
contract-compliant and MAY be registered with `has_repl = true`.

### 8.3 Interop guarantee

Two independent teams implementing this contract — one on the device, one on the host —
produce compatible artifacts, because:

- the device's observable behavior is fully specified by §2–§6 and pinned by the T-1…T-9
  vectors;
- the host's behavior is fully specified by §3.3, §5.3–§5.5, and §7;
- every environment-specific difference (verb case, line endings, banners, USB identity,
  which host asks) is explicitly neutralized in §5.6.

Any deviation is therefore a checklist failure that T-1…T-9 will catch — which is what
makes it impossible for a compliant firmware to behave differently across the CLI, GUI,
or TUI.

---

## 9. Reference implementations

- **Host (control plane + discovery):** `vendor/bombercat-tools/modules/core/bombercat.py`
  (`DeviceLink`, `discover_devices`, `resolve_port`) and
  `vendor/bombercat-tools/modules/core/usb_connection.py` (transport, USB tagging, numbering).
- **Firmware registry (capabilities, `has_repl`):**
  `vendor/bombercat-tools/modules/core/firmwares.py`.
- **Protocol notes (superseded here for the discovery subset):**
  `vendor/bombercat-tools/docs/protocol.md`.
- **EMVy passthrough reader (the `PING`/uppercase dialect this contract reconciles):**
  `emvy/readers/bombercat.py`.
