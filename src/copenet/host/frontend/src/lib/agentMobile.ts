export function getConversationDebugHelperText(isMobile: boolean, isArchived: boolean): string | undefined {
  if (isMobile) return undefined;
  return isArchived ? 'Read-only debugging' : 'Conversation debugging';
}

export function getWorkingSetSectionLabel(
  section: 'entities' | 'constraints' | 'questions',
  isMobile: boolean,
): string {
  if (!isMobile) {
    return section === 'entities'
      ? 'Active Entities'
      : section === 'constraints'
        ? 'Constraints'
        : 'Open Questions';
  }

  return section === 'entities'
    ? 'Active'
    : section === 'constraints'
      ? 'Limits'
      : 'Questions';
}

export function getDebugActionLabel(action: 'copy' | 'export' | 'archive', isMobile: boolean): string {
  if (!isMobile) {
    return action === 'copy' ? 'Debug Copy' : action === 'export' ? 'Export' : 'Archive';
  }
  return action === 'copy' ? 'Copy' : action === 'export' ? 'Export' : 'Archive';
}

export function getConversationActionTriggerLabel(_isMobile: boolean): string {
  return 'Actions';
}

export function shouldUseWorkingSetCompactGrid(isMobile: boolean): boolean {
  return isMobile;
}

export function shouldCollapseWorkingSetByDefault(isMobile: boolean): boolean {
  return isMobile;
}
