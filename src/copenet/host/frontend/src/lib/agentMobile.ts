export function getDebugActionLabel(action: 'copy' | 'export' | 'archive', isMobile: boolean): string {
  if (!isMobile) {
    return action === 'copy' ? 'Debug Copy' : action === 'export' ? 'Export' : 'Archive';
  }
  return action === 'copy' ? 'Copy' : action === 'export' ? 'Export' : 'Archive';
}

export function getConversationActionTriggerLabel(_isMobile: boolean): string {
  return 'Actions';
}
