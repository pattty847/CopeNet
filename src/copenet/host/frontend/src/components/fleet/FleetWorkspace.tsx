import { useEffect, useMemo, useRef, useState } from 'react';
import { Archive, ArrowUp, Bot, CircleDot, Plus, Sparkles, UsersRound, Wrench } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { wsClient } from '../../lib/wsClient';
import { ChatMarkdown } from '../ChatMarkdown';
import { ToolPromptPalette } from '../ToolPromptPalette';
import type { FleetRoomEvent } from '../../types/backend';

const TARGETS = [
  { id: '@everyone', label: 'Everyone' },
  { id: '@chatgpt', label: 'ChatGPT' },
  { id: '@claude', label: 'Claude' },
] as const;

function participantLabel(participantId: string) {
  if (participantId === 'chatgpt') return 'ChatGPT';
  if (participantId === 'claude') return 'Claude';
  return participantId;
}

function EventCard({ event }: { event: FleetRoomEvent }) {
  const isOperator = event.author === 'operator';
  const isError = event.kind === 'error';
  const receipts = event.metadata.toolReceipts || [];
  if (isOperator) {
    return (
      <div className="ml-auto max-w-[82%] rounded-2xl rounded-br-md border border-operator-accent/20 bg-operator-accent/10 px-4 py-3">
        <div className="mb-1.5 flex items-center justify-end gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-operator-accent">
          <span>{event.metadata.target || '@everyone'}</span>
          <span className="text-operator-muted/60">You</span>
        </div>
        <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-operator-text">{event.content}</div>
      </div>
    );
  }
  return (
    <article className={`max-w-[94%] rounded-2xl border px-4 py-3 ${
      isError
        ? 'border-red-400/25 bg-red-500/5'
        : event.author === 'claude'
          ? 'border-amber-400/20 bg-amber-400/[0.035]'
          : 'border-sky-400/20 bg-sky-400/[0.035]'
    }`}>
      <div className="mb-2.5 flex items-center gap-2">
        <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${
          event.author === 'claude' ? 'bg-amber-400/10 text-amber-300' : 'bg-sky-400/10 text-sky-300'
        }`}>
          <Bot className="h-3.5 w-3.5" />
        </div>
        <div>
          <div className="text-[12px] font-semibold text-operator-text">{participantLabel(event.author)}</div>
          <div className="text-[9px] uppercase tracking-[0.14em] text-operator-muted/60">
            {isError ? 'Lane error' : 'Independent lane'} · event {event.seq}
          </div>
        </div>
      </div>
      <div className={isError ? 'text-[12px] text-red-300' : 'text-[13px] text-operator-text'}>
        {isError ? event.content : <ChatMarkdown content={event.content} density="compact" />}
      </div>
      {receipts.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-operator-border/60 pt-2.5">
          {receipts.map((receipt, index) => (
            <span
              key={`${receipt.toolId || 'tool'}-${index}`}
              className="inline-flex items-center gap-1 rounded-full border border-operator-border bg-operator-bg/60 px-2 py-1 text-[9px] text-operator-muted"
              title={receipt.summary || undefined}
            >
              <Wrench className="h-2.5 w-2.5" />
              {receipt.toolId || 'tool'} · {receipt.ok ? 'shared' : 'failed'}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}

function FleetCreate({ currentRoom, onCancel }: { currentRoom?: { roomId: string; title: string } | null; onCancel?: () => void }) {
  const runtimeContext = useAppStore((state) => state.runtimeContext);
  const setAppError = useAppStore((state) => state.setAppError);
  const setFleetCreateOpen = useAppStore((state) => state.setFleetCreateOpen);
  const [title, setTitle] = useState('Market Research Room');
  const [creating, setCreating] = useState(false);

  const createRoom = async () => {
    setCreating(true);
    try {
      // The server allows one active room: starting a new one archives the
      // current room first. The warning above the button makes this explicit.
      if (currentRoom) {
        await wsClient.archiveFleetRoom(currentRoom.roomId);
      }
      await wsClient.createFleetRoom(title.trim() || 'Fleet Room', runtimeContext?.workspaceRoot);
      setFleetCreateOpen(false);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to create Fleet room.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center overflow-y-auto p-6">
      <div className="w-full max-w-xl rounded-3xl border border-operator-border bg-operator-panel/55 p-6 shadow-2xl shadow-black/10">
        <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-operator-accent/10 text-operator-accent">
          <UsersRound className="h-5 w-5" />
        </div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-operator-accent">Fleet collaboration</div>
        <h2 className="mt-2 text-xl font-semibold tracking-tight text-operator-text">Two independent minds, one durable room.</h2>
        <p className="mt-2 max-w-lg text-[13px] leading-relaxed text-operator-muted">
          ChatGPT and Claude receive the same prompt independently before either sees the other answer. Address a lane directly after reveal to challenge, verify, or extend the work.
        </p>
        <div className="mt-5 grid grid-cols-2 gap-2">
          {['ChatGPT · OpenAI Codex', 'Claude · CLI harness'].map((label) => (
            <div key={label} className="rounded-xl border border-operator-border bg-operator-bg/45 px-3 py-2.5 text-[11px] text-operator-muted">
              <CircleDot className="mr-1.5 inline h-3 w-3 text-emerald-400" />{label}
            </div>
          ))}
        </div>
        <label className="mt-5 block text-[10px] font-semibold uppercase tracking-[0.14em] text-operator-muted">Room title</label>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter') void createRoom(); }}
          className="mt-2 h-11 w-full rounded-xl border border-operator-border bg-operator-bg px-3 text-[13px] text-operator-text outline-none transition focus:border-operator-accent/50"
        />
        {currentRoom && (
          <p className="mt-3 rounded-xl border border-amber-400/25 bg-amber-400/5 px-3 py-2 text-[11px] leading-relaxed text-amber-200/90">
            Starting a new room will archive “{currentRoom.title}”. Its transcript stays readable in archived rooms.
          </p>
        )}
        <button
          type="button"
          onClick={() => void createRoom()}
          disabled={creating}
          className="glow-accent mt-3 inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-operator-accent text-[12px] font-semibold text-operator-bg disabled:opacity-50"
        >
          {creating ? <Sparkles className="h-4 w-4 animate-pulse" /> : <Plus className="h-4 w-4" />}
          {creating ? 'Starting Fleet…' : currentRoom ? 'Archive current & start new room' : 'Start Fleet room'}
        </button>
        {currentRoom && onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={creating}
            className="mt-2 inline-flex h-10 w-full items-center justify-center rounded-xl border border-operator-border text-[12px] font-medium text-operator-muted transition hover:text-operator-text disabled:opacity-50"
          >
            Keep “{currentRoom.title}”
          </button>
        )}
      </div>
    </div>
  );
}

export function FleetWorkspace() {
  const rooms = useAppStore((state) => state.fleetRooms);
  const activeRoomId = useAppStore((state) => state.activeFleetRoomId);
  const pendingByRoom = useAppStore((state) => state.fleetPendingCountsByRoom);
  const setAppError = useAppStore((state) => state.setAppError);
  const room = rooms.find((item) => item.roomId === activeRoomId && item.status === 'active')
    || rooms.find((item) => item.status === 'active')
    || null;
  const [target, setTarget] = useState<(typeof TARGETS)[number]['id']>('@everyone');
  const [draft, setDraft] = useState('');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const pending = room ? pendingByRoom[room.roomId] || {} : {};
  const pendingNames = useMemo(
    () => Object.entries(pending).filter(([, count]) => count > 0).map(([id]) => participantLabel(id)),
    [pending],
  );

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [room?.events.length]);
  useEffect(() => { void wsClient.refreshFleetRooms(); }, []);

  const fleetCreateOpen = useAppStore((state) => state.fleetCreateOpen);
  const setFleetCreateOpen = useAppStore((state) => state.setFleetCreateOpen);
  if (!room) return <FleetCreate />;
  if (fleetCreateOpen) {
    return <FleetCreate currentRoom={{ roomId: room.roomId, title: room.title }} onCancel={() => setFleetCreateOpen(false)} />;
  }

  const send = async () => {
    const message = draft.trim();
    if (!message) return;
    setDraft('');
    try {
      await wsClient.sendFleetMessage(room.roomId, target, message);
    } catch (error) {
      setDraft(message);
      setAppError(error instanceof Error ? error.message : 'Unable to send Fleet message.');
    }
  };

  const archive = async () => {
    try {
      await wsClient.archiveFleetRoom(room.roomId);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to archive Fleet room.');
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-operator-bg">
      <header className="border-b border-operator-border bg-operator-panel/35 px-4 py-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.55)]" />
              <h2 className="truncate text-[14px] font-semibold text-operator-text">{room.title}</h2>
              <span className="rounded-full border border-operator-border px-2 py-0.5 text-[9px] uppercase tracking-[0.12em] text-operator-muted">Manual</span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-2 text-[10px] text-operator-muted">
              {Object.values(room.participants).map((participant) => (
                <span key={participant.participantId}>{participantLabel(participant.participantId)} · {participant.model || 'default'}</span>
              ))}
            </div>
          </div>
          <button type="button" onClick={() => void archive()} className="rounded-lg border border-operator-border p-2 text-operator-muted transition hover:text-operator-text" title="Archive Fleet room">
            <Archive className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-3">
          {room.events.length === 0 && (
            <div className="rounded-2xl border border-dashed border-operator-border p-6 text-center">
              <UsersRound className="mx-auto h-5 w-5 text-operator-accent" />
              <div className="mt-2 text-[12px] font-semibold text-operator-text">Start with an independent question</div>
              <div className="mt-1 text-[11px] text-operator-muted">Both lanes answer behind the reveal barrier. Their evidence receipts are shared with the room.</div>
            </div>
          )}
          {room.events.map((event) => <EventCard key={event.eventId} event={event} />)}
          {pendingNames.length > 0 && (
            <div className="flex items-center gap-2 px-1 text-[10px] text-operator-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-operator-accent" />
              {pendingNames.join(' + ')} working independently… you can leave this room or queue another prompt.
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <footer className="border-t border-operator-border bg-operator-panel/35 p-3">
        <div className="mx-auto max-w-3xl">
          {paletteOpen && (
            <div className="mb-2 max-h-56 overflow-y-auto rounded-2xl border border-operator-border bg-operator-panel/80 p-2">
              <ToolPromptPalette
                onInsert={(text) => {
                  setDraft((current) => current && !current.endsWith(' ') && !current.endsWith('\n') ? `${current} ${text}` : `${current}${text}`);
                  setPaletteOpen(false);
                }}
              />
            </div>
          )}
          <div className="mb-2 flex items-center gap-1.5">
            {TARGETS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTarget(item.id)}
                className={`rounded-full border px-2.5 py-1 text-[10px] font-medium transition ${target === item.id ? 'border-operator-accent/35 bg-operator-accent/10 text-operator-accent' : 'border-operator-border text-operator-muted hover:text-operator-text'}`}
              >
                {item.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setPaletteOpen((open) => !open)}
              className={`ml-auto flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-medium transition ${paletteOpen ? 'border-operator-accent/35 bg-operator-accent/10 text-operator-accent' : 'border-operator-border text-operator-muted hover:text-operator-text'}`}
              title="Insert a tool directive into the prompt"
            >
              <Wrench className="h-3 w-3" /> Tools
            </button>
          </div>
          <div className="flex items-end gap-2 rounded-2xl border border-operator-border bg-operator-bg p-2 focus-within:border-operator-accent/40">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              rows={2}
              placeholder={`Message ${target}…`}
              className="min-h-11 flex-1 resize-none bg-transparent px-2 py-1.5 text-[13px] leading-relaxed text-operator-text outline-none placeholder:text-operator-muted/50"
            />
            <button type="button" onClick={() => void send()} disabled={!draft.trim()} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-operator-accent text-operator-bg disabled:opacity-30" title={pendingNames.length ? 'Queue prompt' : 'Send prompt'}>
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
