export type HomeCardId =
  | 'hero'
  | 'recent_activity'
  | 'system_health'
  | 'memory_profile';

export type HomeCardHeight = 'compact' | 'regular' | 'tall';

export interface HomeCardLayoutItem {
  id: HomeCardId;
  span: 4 | 5 | 6 | 7 | 8 | 12;
  height: HomeCardHeight;
}

export interface HomeCardDescriptor {
  id: HomeCardId;
  title: string;
  defaultSpan: HomeCardLayoutItem['span'];
  defaultHeight: HomeCardHeight;
  allowedSpans: HomeCardLayoutItem['span'][];
  allowedHeights: HomeCardHeight[];
}

export const HOME_CARD_DESCRIPTORS: Record<HomeCardId, HomeCardDescriptor> = {
  hero: {
    id: 'hero',
    title: 'Hero',
    defaultSpan: 12,
    defaultHeight: 'tall',
    allowedSpans: [8, 12],
    allowedHeights: ['regular', 'tall'],
  },
  recent_activity: {
    id: 'recent_activity',
    title: 'Recent activity',
    defaultSpan: 7,
    defaultHeight: 'regular',
    allowedSpans: [4, 6, 7, 8, 12],
    allowedHeights: ['regular', 'tall'],
  },
  system_health: {
    id: 'system_health',
    title: 'System health',
    defaultSpan: 5,
    defaultHeight: 'regular',
    allowedSpans: [4, 5, 6],
    allowedHeights: ['regular', 'tall'],
  },
  memory_profile: {
    id: 'memory_profile',
    title: 'Identity & memory',
    defaultSpan: 12,
    defaultHeight: 'regular',
    allowedSpans: [8, 12],
    allowedHeights: ['regular', 'tall'],
  },
};

export const DEFAULT_HOME_LAYOUT: HomeCardLayoutItem[] = Object.values(HOME_CARD_DESCRIPTORS).map((descriptor) => ({
  id: descriptor.id,
  span: descriptor.defaultSpan,
  height: descriptor.defaultHeight,
}));

function isHeight(value: unknown): value is HomeCardHeight {
  return value === 'compact' || value === 'regular' || value === 'tall';
}

export function normalizeHomeLayout(raw: unknown): HomeCardLayoutItem[] {
  const source = Array.isArray(raw) ? raw : [];
  const seen = new Set<HomeCardId>();
  const normalized: HomeCardLayoutItem[] = [];

  for (const entry of source) {
    if (!entry || typeof entry !== 'object') continue;
    const payload = entry as Record<string, unknown>;
    const id = String(payload.id || '') as HomeCardId;
    const descriptor = HOME_CARD_DESCRIPTORS[id];
    if (!descriptor || seen.has(id)) continue;
    const requestedSpan = Number(payload.span);
    const span = descriptor.allowedSpans.includes(requestedSpan as HomeCardLayoutItem['span'])
      ? requestedSpan as HomeCardLayoutItem['span']
      : descriptor.defaultSpan;
    const requestedHeight = payload.height;
    normalized.push({
      id,
      span,
      height: isHeight(requestedHeight) && descriptor.allowedHeights.includes(requestedHeight)
        ? requestedHeight
        : descriptor.defaultHeight,
    });
    seen.add(id);
  }

  for (const fallback of DEFAULT_HOME_LAYOUT) {
    if (!seen.has(fallback.id)) {
      normalized.push(fallback);
    }
  }

  return normalized;
}

export function reorderHomeLayout(layout: HomeCardLayoutItem[], activeId: HomeCardId, overId: HomeCardId): HomeCardLayoutItem[] {
  const fromIndex = layout.findIndex((item) => item.id === activeId);
  const toIndex = layout.findIndex((item) => item.id === overId);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return layout;
  const next = [...layout];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

export function cycleHomeCardSize(
  layout: HomeCardLayoutItem[],
  cardId: HomeCardId,
  direction: 'grow' | 'shrink',
  axis: 'span' | 'height',
): HomeCardLayoutItem[] {
  return layout.map((item) => {
    if (item.id !== cardId) return item;
    const descriptor = HOME_CARD_DESCRIPTORS[cardId];
    if (axis === 'span') {
      const values = descriptor.allowedSpans;
      const currentIndex = values.indexOf(item.span);
      const nextIndex = direction === 'grow'
        ? Math.min(values.length - 1, currentIndex + 1)
        : Math.max(0, currentIndex - 1);
      return { ...item, span: values[nextIndex] };
    }
    const values = descriptor.allowedHeights;
    const currentIndex = values.indexOf(item.height);
    const nextIndex = direction === 'grow'
      ? Math.min(values.length - 1, currentIndex + 1)
      : Math.max(0, currentIndex - 1);
    return { ...item, height: values[nextIndex] };
  });
}

export function heightClassForHomeCard(height: HomeCardHeight): string {
  if (height === 'compact') return 'min-h-[210px]';
  if (height === 'tall') return 'min-h-[420px]';
  return 'min-h-[300px]';
}
