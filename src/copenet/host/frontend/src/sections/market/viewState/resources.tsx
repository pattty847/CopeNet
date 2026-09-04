import { createContext, useContext, useLayoutEffect, type ReactNode } from 'react';
import type { ViewResource } from '../chartAgent/types';

export class ViewResources {
  private entries = new Map<string, { symbol: string; resource: ViewResource }>();
  revision = 0;
  set(symbol: string, resource: ViewResource) {
    this.entries.set(resource.key, { symbol, resource });
    this.revision += 1;
    return () => {
      if (this.entries.get(resource.key)?.resource === resource) {
        this.entries.delete(resource.key);
        this.revision += 1;
      }
    };
  }
  read(symbol: string): ViewResource[] {
    return [...this.entries.values()].filter((entry) => entry.symbol === symbol).map((entry) => entry.resource);
  }
}

const ViewResourceContext = createContext<ViewResources | null>(null);
export function ViewResourceProvider({ resources, children }: { resources: ViewResources; children: ReactNode }) {
  return <ViewResourceContext.Provider value={resources}>{children}</ViewResourceContext.Provider>;
}

/** Publish the committed render model without rerendering the chart on quote ticks. */
export function useViewResource(symbol: string, resource: ViewResource) {
  const resources = useContext(ViewResourceContext);
  useLayoutEffect(() => resources?.set(symbol, resource), [resources, symbol, resource]);
}
