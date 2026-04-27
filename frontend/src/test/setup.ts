import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});

class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  configurable: true,
  value: ResizeObserverMock,
});

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  configurable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

HTMLElement.prototype.scrollIntoView = function scrollIntoView(): void {};
window.PointerEvent = window.PointerEvent || MouseEvent;
HTMLElement.prototype.hasPointerCapture = function hasPointerCapture(): boolean {
  return false;
};
HTMLElement.prototype.setPointerCapture = function setPointerCapture(): void {};
HTMLElement.prototype.releasePointerCapture = function releasePointerCapture(): void {};
