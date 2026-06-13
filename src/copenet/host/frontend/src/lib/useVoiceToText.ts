// Voice-to-text for the composer mic button: capture mic audio with
// MediaRecorder, POST the clip to /api/v1/media/transcribe (local Whisper), and
// hand the transcribed text back via onText. No media asset is persisted.

import { useCallback, useRef, useState } from 'react';

const DEFAULT_DEV_TOKEN = 'dev-token';

function getHttpBaseUrl(): string {
  const envUrl = import.meta.env.VITE_COPNET_API_URL?.trim();
  if (envUrl) return envUrl.replace(/\/$/, '');
  return window.location.origin;
}

function getAuthToken(): string {
  const envToken = import.meta.env.VITE_COPNET_TOKEN?.trim() || '';
  const fromWindow = typeof window.COPNET_TOKEN === 'string' ? window.COPNET_TOKEN.trim() : '';
  const fromStorage = window.localStorage.getItem('copnet.token') || '';
  const fromMeta = document.querySelector('meta[name="copnet-token"]')?.getAttribute('content')?.trim() || '';
  return envToken || fromWindow || fromStorage || fromMeta || DEFAULT_DEV_TOKEN;
}

export type VoiceState = 'idle' | 'recording' | 'transcribing';

export function useVoiceToText(onText: (text: string) => void) {
  const [state, setState] = useState<VoiceState>('idle');
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const transcribe = useCallback(async (blob: Blob, ext: string) => {
    setState('transcribing');
    setError(null);
    try {
      const form = new FormData();
      form.append('file', blob, `voice-clip.${ext}`);
      const resp = await fetch(`${getHttpBaseUrl()}/api/v1/media/transcribe`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${getAuthToken()}` },
        body: form,
      });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(`transcription failed (${resp.status}): ${detail.slice(0, 200)}`);
      }
      const data = (await resp.json()) as { text?: unknown };
      const text = typeof data.text === 'string' ? data.text.trim() : '';
      if (text) onTextRef.current(text);
      else setError('No speech detected.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Transcription failed.');
    } finally {
      setState('idle');
    }
  }, []);

  const start = useCallback(async () => {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('Microphone capture is not supported in this browser.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : MediaRecorder.isTypeSupported('audio/mp4')
          ? 'audio/mp4'
          : '';
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stopTracks();
        const type = recorder.mimeType || 'audio/webm';
        const ext = type.includes('mp4') ? 'mp4' : type.includes('ogg') ? 'ogg' : 'webm';
        const blob = new Blob(chunksRef.current, { type });
        chunksRef.current = [];
        if (blob.size > 0) void transcribe(blob, ext);
        else setState('idle');
      };
      recorderRef.current = recorder;
      recorder.start();
      setState('recording');
    } catch (err) {
      stopTracks();
      setError(err instanceof Error ? err.message : 'Could not access the microphone.');
      setState('idle');
    }
  }, [transcribe]);

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    recorderRef.current = null;
  }, []);

  const toggle = useCallback(() => {
    if (state === 'recording') stop();
    else if (state === 'idle') void start();
    // ignore clicks while transcribing
  }, [state, start, stop]);

  return { state, error, toggle };
}
