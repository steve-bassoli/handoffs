"""Prototype-only automation of human sign-off (task e3c65ba2).

ASE_PROTOTYPE_AUTO_SIGNOFF=on lets non-human principals record acceptance while we prototype.
It has a HARD cutoff: after HARD_CUTOFF, or once a RELEASED marker exists at the repository
root, the flag is ignored and cannot be re-enabled by any setting. Moving the cutoff is a code
change, never configuration. Every use is recorded on events as signoff: prototype-auto.
"""
from datetime import datetime, timezone
import os
from pathlib import Path

HARD_CUTOFF = datetime(2026, 11, 1, tzinfo=timezone.utc)
RELEASE_MARKER = Path(__file__).resolve().parents[1] / 'RELEASED'


def door_off(now=None):
    """ASE_DOOR=off is construction mode (task eabd11e7): the whole door comes off at once.

    Identity headers are accepted, acceptance and sign-offs need no person, and the intake screen never
    blocks. Same hard cutoff and release marker as below; ASE_DOOR=on (the default) puts every lock back.
    """
    if os.environ.get('ASE_DOOR') != 'off' or RELEASE_MARKER.exists():
        return False
    return (now or datetime.now(timezone.utc)) < HARD_CUTOFF


def auto_signoff_active(now=None):
    if door_off(now):
        return True
    if os.environ.get('ASE_PROTOTYPE_AUTO_SIGNOFF') != 'on' or RELEASE_MARKER.exists():
        return False
    return (now or datetime.now(timezone.utc)) < HARD_CUTOFF


def bypass_label():
    """How a bypassed sign-off is recorded in history."""
    return 'door-off' if door_off() else 'prototype-auto'
