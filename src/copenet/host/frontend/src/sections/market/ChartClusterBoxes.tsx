import { Fragment } from 'react';

import { BOX_BG, BOX_BORDER, type RenderedBox } from './chartDecorations';
import { MM, mono, toneColor } from './marketUi';

export function ChartClusterBoxes({
  boxes,
  onOpen,
}: {
  boxes: RenderedBox[];
  onOpen: (box: RenderedBox) => void;
}) {
  return boxes.map((box) => {
    const hasAverage = box.avgY != null && box.avgPrice != null;
    const averageLabel = hasAverage ? `avg ${box.avgSide} $${box.avgPrice.toFixed(2)}` : null;

    return (
      <Fragment key={box.key}>
        <div
          style={{
            position: 'absolute',
            left: box.left,
            top: box.top,
            width: box.width,
            height: box.height,
            zIndex: 4,
            pointerEvents: 'none',
            border: `1px solid ${BOX_BORDER[box.tone]}`,
            background: BOX_BG[box.tone],
            borderRadius: 6,
          }}
        >
          {hasAverage && (
            <div
              data-cluster-average-line
              aria-hidden="true"
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: box.avgY! - box.top,
                borderTop: `1.5px dashed ${toneColor(box.tone)}`,
                opacity: 0.95,
                filter: 'drop-shadow(0 0 2px #0b0b0d)',
              }}
            />
          )}
        </div>
        <button
          aria-label={`Open SEC activity: ${box.chip}${averageLabel ? `, ${averageLabel}` : ''}`}
          onClick={() => onOpen(box)}
          style={{
            position: 'absolute',
            left: box.left + box.width / 2,
            top: Math.max(2, box.top - (hasAverage ? 35 : 21)),
            transform: 'translateX(-50%)',
            zIndex: 6,
            cursor: 'pointer',
            border: `1px solid ${BOX_BORDER[box.tone]}`,
            background: '#0b0b0d',
            color: box.tone === 'flat' ? MM.muted : toneColor(box.tone),
            borderRadius: 7,
            padding: hasAverage ? '3px 7px 2px' : '2px 7px',
            fontFamily: mono,
            fontSize: 9.5,
            whiteSpace: 'nowrap',
            lineHeight: 1.35,
          }}
        >
          <span style={{ display: 'block' }}>{box.chip}</span>
          {averageLabel && (
            <span
              data-cluster-average-label
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 4,
                marginTop: 1,
                fontSize: 8.5,
                color: toneColor(box.tone),
              }}
            >
              <span aria-hidden="true" style={{ width: 12, borderTop: `1.5px dashed ${toneColor(box.tone)}` }} />
              {averageLabel}
            </span>
          )}
        </button>
      </Fragment>
    );
  });
}
