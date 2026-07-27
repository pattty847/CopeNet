import type { EvidenceItem } from './types';

export function sortEvidenceNewestFirst(evidence: readonly EvidenceItem[]): EvidenceItem[] {
  return [...evidence].sort((left, right) => {
    const leftTime = left.t ?? Number.NEGATIVE_INFINITY;
    const rightTime = right.t ?? Number.NEGATIVE_INFINITY;
    return rightTime - leftTime;
  });
}
