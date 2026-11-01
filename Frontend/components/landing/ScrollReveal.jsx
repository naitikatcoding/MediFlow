'use client';
import React, { useEffect, useRef, useState } from 'react';

export function ScrollReveal({
  as: Element = 'div',
  children,
  className = '',
  delay = 0,
}) {
  const elementRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return undefined;

    setReady(true);
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reducedMotion || !('IntersectionObserver' in window)) {
      setVisible(true);
      return undefined;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.unobserve(entry.target);
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -32px 0px' },
    );
    observer.observe(element);

    return () => observer.disconnect();
  }, []);

  return (
    <Element
      ref={elementRef}
      className={`${ready ? 'scroll-reveal' : ''} ${className}`.trim()}
      data-visible={visible ? 'true' : 'false'}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </Element>
  );
}
