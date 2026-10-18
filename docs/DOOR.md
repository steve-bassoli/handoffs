# The door: proving it, taking it off, putting it back

ASE has one door: signed-in identity, real human acceptance, sign-offs for irreversible actions,
protected rule texts and the intake screen. While Steve and Nate build, the door can come off with one
switch so large changes move in without unlocking it each time (task eabd11e7).

## 1. Prove the door works (each of Steve and Nate, once)

From the HANDOFFS checkout, set your own password. Type it yourself; never let an agent or the relay set
or see it.

    .venv\Scripts\python.exe scripts\credentials.py password <your user id>

Then open the board (`HANDOFFS_URL`), sign in with the form at the top, and on the Sign-offs page approve
one pending sign-off with a note. History shows `decision_mode: human` and your name. That is the proof.

## 2. Check every lock before changing the door

    .venv\Scripts\python.exe scripts\door_check.py --url <HANDOFFS_URL>

Every line must say PASS. It runs the lock tests with the door on and reports the live door state.

## 3. Take the door off

Start the service with `ASE_DOOR=off`. Then:

- the old `X-Demo-User` header works, so scripts and agents need no sign-in;
- acceptance and sign-offs go through without a person and are labelled `door-off` in history;
- the intake screen still records a verdict on every post and take but never blocks;
- `/health` reports `"door": "off"` and the page shows an orange construction banner.

Rule texts still need two approvals to change: the door does not cover changing the rules.

## 4. Put the door back

Restart without `ASE_DOOR` (or with `ASE_DOOR=on`), then run the door check again. The door also goes back
on by itself at the hard cutoff, 2026-11-01 00:00 UTC, or as soon as a `RELEASED` file exists at the
repository root. No setting can extend that; moving the cutoff is a code change.
