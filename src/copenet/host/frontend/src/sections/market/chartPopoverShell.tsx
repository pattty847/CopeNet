// The frame every chart-toolbar popover uses.
//
// Extracted from chartMenus.tsx when the Plots menu moved to its own file: two popovers
// re-declaring the same header and padding is how two popovers start looking different.

import type { ReactNode, RefObject } from 'react';
import { X } from 'lucide-react';
import { MarketFloatingPopover } from './MarketFloatingPopover';

export function ChartPopoverShell({
  anchor,
  open,
  onClose,
  title,
  width = 320,
  children,
}: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  title: string;
  width?: number;
  children: ReactNode;
}) {
  return (
    <MarketFloatingPopover anchorRef={anchor} open={open} onClose={onClose} width={width}>
      <div className="tw-pop">
        <div className="tw-pop__head">
          <div className="tw-pop__title">{title}</div>
          <button type="button" className="tw-iconbtn" onClick={onClose} aria-label={`Close ${title}`}><X size={13} /></button>
        </div>
        <div className="tw-pop__body">{children}</div>
      </div>
    </MarketFloatingPopover>
  );
}
