import { useEffect, useRef, useState } from 'react';
import { W, H, L, R, T, B, MIN_SCALE, MAX_SCALE, clamp, screenToPlotPoint, constrainView, type RrgView } from './rrgGeometry';

export function useRrgInteraction() {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ pointerId: number; x: number; y: number; panX: number; panY: number; moved: boolean } | null>(null);
  const suppressClickRef = useRef(false);
  const [view, setView] = useState<RrgView>({ scale: 1, panX: 0, panY: 0 });
  const [pixelScale, setPixelScale] = useState(1);
  const [touchPan, setTouchPan] = useState(false);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const measure = () => setPixelScale(Math.max(svg.getBoundingClientRect().width / W, 0.01));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(svg);
    return () => observer.disconnect();
  }, []);

  const setZoom = (nextScale: number, anchor?: { x: number; y: number }) => {
    setView((current) => {
      const scale = clamp(nextScale, MIN_SCALE, MAX_SCALE);
      const target = anchor || { x: L + (W - L - R) / 2, y: T + (H - T - B) / 2 };
      const ratio = current.scale / scale;
      return constrainView({
        scale,
        panX: L + (target.x + current.panX - L) * ratio - target.x,
        panY: T + (target.y + current.panY - T) * ratio - target.y,
      });
    });
  };

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;

    const handleNativeWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      event.stopPropagation();
      const anchor = screenToPlotPoint(event.clientX, event.clientY, svg, view);
      const factor = event.deltaY < 0 ? 1.14 : 0.88;
      setZoom(view.scale * factor, anchor);
    };

    svg.addEventListener('wheel', handleNativeWheel, { passive: false });
    return () => svg.removeEventListener('wheel', handleNativeWheel);
  }, [view]);

  const handlePointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0 || (event.pointerType !== 'mouse' && !touchPan)) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, panX: view.panX, panY: view.panY, moved: false };
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    const svg = svgRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !svg || view.scale <= 1) return;
    const rect = svg.getBoundingClientRect();
    if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 3) drag.moved = true;
    setView(constrainView({
      scale: view.scale,
      panX: drag.panX + ((event.clientX - drag.x) / rect.width) * W / view.scale,
      panY: drag.panY + ((event.clientY - drag.y) / rect.height) * H / view.scale,
    }));
  };

  const endDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      suppressClickRef.current = dragRef.current.moved;
      dragRef.current = null;
    }
  };

  return { svgRef, view, setView, setZoom, pixelScale, touchPan, setTouchPan, suppressClickRef, handlePointerDown, handlePointerMove, endDrag };
}
