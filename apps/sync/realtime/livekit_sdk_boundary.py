"""Typed reads for LiveKit SDK objects at the sync realtime boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LiveKitEgressInfo(Protocol):
    egress_id: str


@runtime_checkable
class LiveKitParticipant(Protocol):
    identity: str


@runtime_checkable
class LiveKitTrack(Protocol):
    sid: str


def read_livekit_egress_id(egress_info: object) -> str:
    if not isinstance(egress_info, LiveKitEgressInfo):
        raise RuntimeError("LiveKit egress_info missing egress_id")
    egress_id = egress_info.egress_id
    if egress_id == "":
        raise RuntimeError("LiveKit не вернул egress_id после старта записи.")
    return egress_id


def read_livekit_participant_identity(participant: object) -> str | None:
    if not isinstance(participant, LiveKitParticipant):
        raise RuntimeError("LiveKit participant missing identity")
    identity = participant.identity
    if identity == "":
        return None
    return identity


def read_livekit_track_sid(track: object) -> str | None:
    if not isinstance(track, LiveKitTrack):
        raise RuntimeError("LiveKit track missing sid")
    track_sid = track.sid
    if track_sid == "":
        return None
    return track_sid
