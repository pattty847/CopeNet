interface ComposerEnterOptions {
  key: string;
  shiftKey: boolean;
  isComposing: boolean;
  isMobile: boolean;
}

/** Desktop Enter sends. Mobile Return and IME composition keep editing the message. */
export function shouldSubmitComposerOnEnter(options: ComposerEnterOptions): boolean {
  return options.key === 'Enter'
    && !options.shiftKey
    && !options.isComposing
    && !options.isMobile;
}
