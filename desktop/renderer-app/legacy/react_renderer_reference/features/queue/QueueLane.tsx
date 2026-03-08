import { useRef, useState } from "react";
import { useQueueStore } from "@/stores/queueStore";
import { useUiStore } from "@/stores/uiStore";
import { usePlayerStore } from "@/stores/playerStore";
import { audioEngine } from "@/services/audio/audioEngine";
import { LyraPanel } from "@/ui/LyraPanel";
import { LyraButton } from "@/ui/LyraButton";
import { ContextMenu } from "@/ui/ContextMenu";
import { useContextMenu } from "@/ui/useContextMenu";
import { ExplanationChips } from "@/features/explanations/ExplanationChips";
import type { TrackListItem } from "@/types/domain";

function QueueRow({
  track,
  index,
  isCurrent,
  isDragOver,
  disableUp,
  disableDown,
  onJump,
  onDossier,
  onMoveUp,
  onMoveDown,
  onRemove,
  onDragStart,
  onDragOver,
  onDrop,
}: {
  track: TrackListItem;
  index: number;
  isCurrent: boolean;
  isDragOver: boolean;
  disableUp: boolean;
  disableDown: boolean;
  onJump: () => void;
  onDossier: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
  onDragStart: () => void;
  onDragOver: (e: React.DragEvent) => void;
  onDrop: () => void;
}) {
  const { menu, open, close } = useContextMenu();

  const menuItems = [
    { label: "Play now",   icon: "▶", action: onJump    },
    { label: "Track info", icon: "◉", action: onDossier },
    { label: "Move up",    icon: "↑", action: onMoveUp  },
    { label: "Move down",  icon: "↓", action: onMoveDown },
    { label: "Remove",     icon: "✕", action: onRemove, danger: true },
  ];

  return (
    <>
      <div
        className={`queue-row${isCurrent ? " is-current" : ""}${isDragOver ? " drag-over" : ""}`}
        draggable
        onDragStart={(e) => { e.dataTransfer.effectAllowed = "move"; onDragStart(); }}
        onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; onDragOver(e); }}
        onDrop={(e) => { e.preventDefault(); onDrop(); }}
        onContextMenu={open}
      >
        <span className="queue-drag-handle" title="Drag to reorder">⠿</span>
        <button className="queue-row-main" onClick={onJump}>
          <span className="queue-index">{String(index + 1).padStart(2, "0")}</span>
          <span className="queue-artist">{track.artist}</span>
          <strong className="queue-title">{track.title}</strong>
          <span className="queue-reason">{track.reasons[0]?.text ?? track.reason}</span>
        </button>
        <div className="queue-row-actions">
          <LyraButton onClick={onDossier}>Info</LyraButton>
          <LyraButton onClick={onMoveUp}   disabled={disableUp}>↑</LyraButton>
          <LyraButton onClick={onMoveDown} disabled={disableDown}>↓</LyraButton>
          <LyraButton onClick={onRemove}>✕</LyraButton>
        </div>
      </div>
      {menu && (
        <ContextMenu x={menu.x} y={menu.y} items={menuItems} onClose={close} />
      )}
    </>
  );
}

export function QueueLane() {
  const queue           = useQueueStore((state) => state.queue);
  const setCurrentIndex = useQueueStore((state) => state.setCurrentIndex);
  const moveItem        = useQueueStore((state) => state.moveItem);
  const removeItem      = useQueueStore((state) => state.removeItem);
  const openDossier     = useUiStore((state) => state.openDossier);
  const setTrack        = usePlayerStore((state) => state.setTrack);

  const current = queue.items[queue.currentIndex];
  const nextUp  = queue.items.slice(queue.currentIndex + 1, queue.currentIndex + 4);

  const dragSrcRef = useRef<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);

  const jumpToTrack = async (index: number) => {
    const track = queue.items[index];
    if (!track) return;
    setCurrentIndex(index);
    setTrack(track, "Queue", track.reasons[0]?.text ?? track.reason);
    await audioEngine.playTrack(track);
  };

  return (
    <LyraPanel className="queue-lane">
      <div className="section-heading">
        <h2>Playlist Queue</h2>
        <span>{queue.items.length} tracks</span>
      </div>
      <div className="queue-headline">
        <div>
          <span className="insight-kicker">Current row</span>
          <strong>{current?.title ?? "Queue empty"}</strong>
          <p>{current?.reasons[0]?.text ?? current?.reason ?? "Play a track or load a playlist to start."}</p>
          {current?.scoreChips && current.scoreChips.length > 0 && (
            <ExplanationChips
              chips={current.scoreChips.map((sc) => ({ label: sc.label, kind: "dimension" as const }))}
            />
          )}
        </div>
        <div className="queue-headline-meta">
          <span>{queue.origin}</span>
          <span>{queue.algorithm ?? "manual"}</span>
        </div>
      </div>
      {nextUp.length > 0 && (
        <div className="queue-preview-strip">
          {nextUp.map((track) => (
            <button
              key={`preview-${track.trackId}`}
              className="queue-preview-card"
              onClick={() => {
                const index = queue.items.findIndex((item) => item.trackId === track.trackId);
                void jumpToTrack(index);
              }}
            >
              <span>{track.artist}</span>
              <strong>{track.title}</strong>
            </button>
          ))}
        </div>
      )}
      <div
        className="queue-list"
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(null);
        }}
      >
        {queue.items.map((track, index) => (
          <QueueRow
            key={`${track.trackId}-${index}`}
            track={track}
            index={index}
            isCurrent={index === queue.currentIndex}
            isDragOver={dragOver === index}
            disableUp={index === 0}
            disableDown={index === queue.items.length - 1}
            onJump={() => void jumpToTrack(index)}
            onDossier={() => openDossier(track.trackId)}
            onMoveUp={() => moveItem(index, Math.max(0, index - 1))}
            onMoveDown={() => moveItem(index, Math.min(queue.items.length - 1, index + 1))}
            onRemove={() => removeItem(index)}
            onDragStart={() => { dragSrcRef.current = index; }}
            onDragOver={() => setDragOver(index)}
            onDrop={() => {
              const src = dragSrcRef.current;
              if (src !== null && src !== index) moveItem(src, index);
              dragSrcRef.current = null;
              setDragOver(null);
            }}
          />
        ))}
      </div>
    </LyraPanel>
  );
}
