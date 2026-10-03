"""Typed reads for LiveKit SDK objects at the sync realtime boundary.

LiveKit SDK отдаёт protobuf-объекты (ParticipantInfo/TrackInfo/EgressInfo). Поле читается
через Protocol; нет атрибута — raise, пустая строка для egress — ошибка, для identity и sid — None.
"""

from __future__ import annotations

from typing import Protocol


class LiveKitEgressInfo(Protocol):
    egress_id: str


class LiveKitParticipant(Protocol):
    identity: str


class LiveKitTrack(Protocol):
    sid: str


def read_livekit_egress_id(egress_info: LiveKitEgressInfo) -> str:
    if not hasattr(egress_info, "egress_id"):
        raise RuntimeError("LiveKit egress_info missing egress_id")
    if egress_info.egress_id == "":
        raise RuntimeError("LiveKit did not return egress_id after recording start.")
    return egress_info.egress_id


def read_livekit_participant_identity(participant: LiveKitParticipant) -> str | None:
    if not hasattr(participant, "identity"):
        raise RuntimeError("LiveKit participant missing identity")
    if participant.identity == "":
        return None
    return participant.identity


def read_livekit_track_sid(track: LiveKitTrack) -> str | None:
    if not hasattr(track, "sid"):
        raise RuntimeError("LiveKit track missing sid")
    if track.sid == "":
        return None
    return track.sid
