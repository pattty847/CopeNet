import { Bot, CheckCircle2, Radio, ShieldCheck, UsersRound } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';

function label(participantId: string) {
  return participantId === 'chatgpt' ? 'ChatGPT' : participantId === 'claude' ? 'Claude' : participantId;
}

export function FleetInspector({ mobile = false }: { mobile?: boolean }) {
  const rooms = useAppStore((state) => state.fleetRooms);
  const activeRoomId = useAppStore((state) => state.activeFleetRoomId);
  const pendingByRoom = useAppStore((state) => state.fleetPendingCountsByRoom);
  const room = rooms.find((item) => item.roomId === activeRoomId && item.status === 'active')
    || rooms.find((item) => item.status === 'active')
    || null;
  const pending = room ? pendingByRoom[room.roomId] || {} : {};

  return (
    <aside className={`${mobile ? 'w-full' : 'h-full'} overflow-y-auto bg-operator-panel/35 p-3`}>
      <div className="flex items-center justify-between border-b border-operator-border pb-3">
        <div className="flex items-center gap-2">
          <UsersRound className="h-4 w-4 text-operator-accent" />
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-operator-text">Fleet inspector</h2>
        </div>
        <span className="inline-flex items-center gap-1 text-[9px] uppercase tracking-[0.12em] text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> live
        </span>
      </div>

      {!room ? (
        <div className="py-8 text-center text-[11px] text-operator-muted">Start a Fleet room to inspect its lanes.</div>
      ) : (
        <div className="space-y-4 pt-4">
          <section>
            <div className="mb-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-operator-muted">Room</div>
            <div className="rounded-xl border border-operator-border bg-operator-bg/45 p-3">
              <div className="truncate text-[12px] font-semibold text-operator-text">{room.title}</div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
                <div><span className="text-operator-muted">Mode</span><div className="mt-0.5 text-operator-text">Manual</div></div>
                <div><span className="text-operator-muted">Events</span><div className="mt-0.5 text-operator-text tabular-nums">{room.events.length}</div></div>
              </div>
            </div>
          </section>

          <section>
            <div className="mb-2 text-[9px] font-semibold uppercase tracking-[0.14em] text-operator-muted">Participant lanes</div>
            <div className="space-y-2">
              {Object.values(room.participants).map((participant) => {
                const queued = pending[participant.participantId] || 0;
                return (
                  <div key={participant.participantId} className="rounded-xl border border-operator-border bg-operator-bg/45 p-3">
                    <div className="flex items-center gap-2">
                      <Bot className={`h-3.5 w-3.5 ${participant.participantId === 'claude' ? 'text-amber-300' : 'text-sky-300'}`} />
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] font-semibold text-operator-text">{label(participant.participantId)}</div>
                        <div className="truncate text-[9px] text-operator-muted">{participant.provider} · {participant.model || 'default'}</div>
                      </div>
                      {queued > 0 ? (
                        <span className="inline-flex items-center gap-1 text-[9px] text-operator-accent"><Radio className="h-3 w-3 animate-pulse" />{queued} queued</span>
                      ) : (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400/70" />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-xl border border-operator-accent/15 bg-operator-accent/[0.035] p-3">
            <div className="flex items-center gap-2 text-[10px] font-semibold text-operator-text">
              <ShieldCheck className="h-3.5 w-3.5 text-operator-accent" /> Independent-first barrier
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-operator-muted">
              For @everyone, both lanes answer from the same room snapshot. Peer content is revealed only after both attempts finish.
            </p>
          </section>
        </div>
      )}
    </aside>
  );
}
