import { useEffect, useState } from 'react';

export const MOBILE_BREAKPOINT_PX = 1024;

export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.innerWidth < MOBILE_BREAKPOINT_PX;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onResize = () => {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT_PX);
    };
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return isMobile;
}
