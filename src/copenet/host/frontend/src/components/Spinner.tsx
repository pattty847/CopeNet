import React from 'react';
import { cn } from '../lib/utils';

export interface SpinnerProps {
  variant?: 'dot-grid' | 'bars' | 'breathe' | 'bounce' | 'flip';
  className?: string;
}

export function Spinner({ variant = 'bars', className }: SpinnerProps) {
  if (variant === 'dot-grid') {
    return (
      <div className={cn("loader-dot-grid", className)}>
        <span></span><span></span><span></span>
        <span></span><span></span><span></span>
        <span></span><span></span><span></span>
      </div>
    );
  }

  if (variant === 'bars') {
    return (
      <div className={cn("loader-bars", className)}>
        <span></span><span></span><span></span><span></span><span></span>
      </div>
    );
  }

  if (variant === 'breathe') {
    return <div className={cn("loader-breathe", className)}></div>;
  }

  if (variant === 'bounce') {
    return (
      <div className={cn("loader-bounce", className)}>
        <span></span><span></span><span></span>
      </div>
    );
  }

  if (variant === 'flip') {
    return <div className={cn("loader-flip", className)}></div>;
  }

  return null;
}
