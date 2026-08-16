---
name: verify-output
description: Run this synth and confirm a change actually works, including the laser output path, without needing a laser. Covers launching it correctly, driving it over the WebSocket, the LaserCube simulator, and the safety invariants that must be re-checked whenever anything on the output path changes. Use whenever a change touches laserx3.py, laser_output.py, helios.py, lasercube_output.py, webui.py or static/index.html — and whenever asked to "check it works".
---

# Verifying a change

There is no test suite, and that is deliberate (CONTRIBUTING.md). The only way
to know a change works is to run the app and drive it. This is that procedure,
plus the traps that have each cost a wasted round trip.

**If the change touches the output path, read [docs/SAFETY.md](../../../docs/SAFETY.md) §6 first.**

## 1. Launch

```bash
python3 -u laserx3.py --no-audio --web-port 8099
```

- **`-u` matters.** Without it stdout is buffered and nothing reaches the log
  file, so a working app looks silent and a crashed one looks identical.
- **Port 8099, never 8080.** The user usually has their own instance on 8080.
- **Use the Bash tool's background flag**, not a shell `&`.
- Add `SDL_VIDEODRIVER=dummy` if you want `--preview` without a window.

Cleaning up: scope it to your own port and **never** `pkill -f laserx3.py` —
that pattern matches the shell command running it and kills your own tool call
(exit 144).

```bash
kill $(cat /tmp/.../app.pid)     # keep the pid, use it
```

## 2. Drive it

State comes over the WebSocket at 5 Hz; commands go the same way. The full
message list is in `webui.py`'s module docstring.

```python
import asyncio, json, aiohttp
async def main():
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect("http://127.0.0.1:8099/ws") as ws:
            await ws.send_json({"type": "arm", "value": True})
            await asyncio.sleep(0.6)          # let a state broadcast land
            async for m in ws:
                if m.type == aiohttp.WSMsgType.TEXT:
                    d = json.loads(m.data)
                    if d.get("type") == "state":
                        print(d["safety"]); return
asyncio.run(main())
```

Sleep at least one broadcast interval (200 ms) after sending before reading
state back, or you will read the value from *before* your command and
conclude it didn't work.

## 3. Testing laser output without a laser

**You never need hardware to test the output path.** Two options:

`--output none` (the default) uses `NullOutput` — the loop runs the same
DAC-bound code, so most output bugs surface anyway.

For the LaserCube, the simulator is a real device stand-in on the real ports:

```bash
python3 -u scripts/lasercube_sim.py                 # behaves
python3 -u laserx3.py --output lasercube --lasercube-ip 127.0.0.1 ...
```

It reports every datagram it receives and flags anything malformed, so wrong
framing shows up immediately rather than as a silent no-op. Make it misbehave
to test the failure paths:

| Flag | Tests |
|---|---|
| `--stall-after N` | watchdog, device-silence detection |
| `--drop 0.2` | packet loss tolerance |
| `--refuse-enable` | arm-refusal path |
| `--tiny-buffer` | backpressure — must drop, never block |
| `--temperature 45` | over-temperature refusal |
| `--interlock-open` | interlock reporting |

The simulator builds its responses **independently** of the client's parser.
Keep it that way — if it mirrored `parse_full_info()`, a shared offset error
would pass unnoticed.

Helios has no simulator; `--laser` without a DAC exits non-zero with a clear
message, which is itself the expected behaviour to check.

## 4. What to re-check when the output path changes

These are the invariants. All are cheap to verify and all have been broken at
least once:

1. **Comes up disarmed**, ceiling 5%. Read `safety` from the state message.
2. **Disarmed means colours are zero**, not "no frames sent". Check the
   simulator's `last=(... r0 g0 b0)` readout.
3. **The ceiling holds** with `brightness` at 1.0 *and* audio modulation on.
4. **All four exit paths blank**: Ctrl-C, `kill -TERM`, an exception in the
   loop body, and `atexit` alone. Test SIGTERM specifically — it was the one
   that was broken.
5. **The watchdog fires on a stall and releases on recovery** — insert a
   temporary `time.sleep(2)` in the loop body.
6. **Pacing is unregressed**: the state's `fps` should match `pps/points`.
7. **Helios still works** if you touched anything shared — `--laser` with no
   DAC must still fail fast with the same message.

## 5. Syntax checks before running

`static/index.html` has no build step, so nothing catches a JS error but the
browser. Extract and check it:

```bash
python3 -c "
import re; h=open('static/index.html').read()
open('/tmp/ui.js','w').write('\n'.join(re.findall(r'<script>(.*?)</script>',h,re.S)))"
node --check /tmp/ui.js
```

Watch for redeclaring an existing helper — `esc()` already exists.

## 6. Finishing

Repo convention (CONTRIBUTING.md): **every code change bumps `__version__` in
`laserx3.py` and adds a `CHANGELOG.md` entry.**

If you changed `laser_output.py`, `helios.py` or `lasercube_output.py`,
they are copied verbatim into laser-arcade and promptwaver — keep them
importable standalone (numpy + stdlib only, Python 3.9) and see
[docs/PORTING.md](../../../docs/PORTING.md).

Leave no test state behind: reset `output` and `max_brightness` in
`settings.json` if you changed them while testing.
