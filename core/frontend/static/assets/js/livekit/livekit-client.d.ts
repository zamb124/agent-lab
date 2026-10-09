/** Vendored LiveKit client (livekit-client.esm.mjs) — importmap-алиас '@livekit/client'. */
declare module '@livekit/client' {
    /** Медиатрек LiveKit (LocalTrack/RemoteTrack). */
    export interface LkTrack {
        kind: string;
        sid?: string;
        mediaStreamTrack: MediaStreamTrack;
        attach(el?: HTMLMediaElement): HTMLMediaElement;
        detach(el?: HTMLMediaElement): void;
        /** Пометка вызывающего кода «аудио уже подключено», не API LiveKit. */
        _lkAttached?: boolean;
    }

    export interface LkTrackPublication {
        track: LkTrack | null;
        source: string;
        isSubscribed: boolean;
    }

    export interface LkParticipant {
        identity: string;
        videoTrackPublications: Map<string, LkTrackPublication>;
        audioTrackPublications: Map<string, LkTrackPublication>;
    }

    export interface LkLocalParticipant extends LkParticipant {
        isCameraEnabled: boolean;
        isMicrophoneEnabled: boolean;
        isScreenShareEnabled: boolean;
        enableCameraAndMicrophone(): Promise<void>;
        setCameraEnabled(enabled: boolean): Promise<unknown>;
        setMicrophoneEnabled(enabled: boolean, options?: Record<string, unknown>): Promise<unknown>;
        setScreenShareEnabled(enabled: boolean, options?: Record<string, unknown>): Promise<unknown>;
    }

    export class Room {
        constructor(options?: Record<string, unknown>);
        readonly localParticipant: LkLocalParticipant;
        readonly remoteParticipants: Map<string, LkParticipant>;
        on(event: string, listener: () => void): this;
        removeAllListeners(): void;
        connect(url: string, token: string): Promise<void>;
        disconnect(): Promise<void>;
        switchActiveDevice(kind: string, deviceId: string): Promise<void>;
        getActiveDevice(kind: string): string | undefined;
    }

    export const RoomEvent: {
        ParticipantConnected: string;
        ParticipantDisconnected: string;
        TrackSubscribed: string;
        TrackUnsubscribed: string;
        LocalTrackPublished: string;
        LocalTrackUnpublished: string;
        Disconnected: string;
        [key: string]: string;
    };

    export const Track: {
        Source: { Camera: string; ScreenShare: string; [key: string]: string };
        Kind: Record<string, string>;
    };

    export const ScreenSharePresets: Record<string, { encoding: unknown }>;
}
