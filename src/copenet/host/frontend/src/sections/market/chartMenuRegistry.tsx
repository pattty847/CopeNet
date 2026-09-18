// One owner of "which chart menu is open".
//
// Every menu around the chart used to own its own boolean, and exclusivity was an accident
// of FloatingPopover's outside-click dismissal: opening menu B fired an outside event that
// closed menu A. That fell apart in two ways.
//
// 1. The price-alert popover is deliberately `dismissOnOutside={false}`, because it holds a
//    half-typed threshold that a stray tap must not discard. So it never closed, and
//    Alert → Plots genuinely left two menus open over the chart.
// 2. The drawing-tool groups are native `<details>`, which know nothing about each other,
//    so all four could be open at once.
//
// Exclusivity is a property of the toolbar, not of any one menu's dismissal policy, so the
// toolbar holds it. Each menu declares an id and asks whether it is the open one. Outside
// dismissal still belongs to the individual menu — this only decides which single menu is
// allowed to be open at a time.

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

type ChartMenuRegistry = {
  openId: string | null;
  setOpenId: (id: string | null) => void;
};

const ChartMenuContext = createContext<ChartMenuRegistry | null>(null);

/** Wrap every surface whose menus should be mutually exclusive — in practice both chart
 *  toolbars, so picking a drawing tool also puts away an open Plots or Compare popover. */
export function ChartMenuProvider({ children }: { children: ReactNode }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const value = useMemo(() => ({ openId, setOpenId }), [openId]);
  return <ChartMenuContext.Provider value={value}>{children}</ChartMenuContext.Provider>;
}

/** Whether this menu is the open one, plus the setter that closes whatever else was.
 *
 *  Falls back to private state when no provider is above it, so a menu component stays
 *  usable on its own — `PriceAlertControl` and the metric pickers are rendered outside the
 *  ticker toolbar in other places. */
export function useChartMenu(id: string): { open: boolean; setOpen: (open: boolean) => void } {
  const registry = useContext(ChartMenuContext);
  const [localOpen, setLocalOpen] = useState(false);

  const setOpen = useCallback(
    (next: boolean) => {
      if (registry) registry.setOpenId(next ? id : null);
      else setLocalOpen(next);
    },
    [id, registry],
  );

  return { open: registry ? registry.openId === id : localOpen, setOpen };
}

/** The registry itself, for a bar that owns SEVERAL menus and cannot call `useChartMenu`
 *  once per menu without calling a hook in a loop. Ids are namespaced by the caller. */
export function useChartMenuRegistry(): ChartMenuRegistry {
  const registry = useContext(ChartMenuContext);
  const [localOpenId, setLocalOpenId] = useState<string | null>(null);
  const localSetter = useCallback((id: string | null) => setLocalOpenId(id), []);
  const fallback = useMemo(
    () => ({ openId: localOpenId, setOpenId: localSetter }),
    [localOpenId, localSetter],
  );
  return registry ?? fallback;
}
