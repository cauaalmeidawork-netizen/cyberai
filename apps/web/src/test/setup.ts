import "@testing-library/jest-dom/vitest";

if (typeof Element !== "undefined") {
  Element.prototype.scrollTo = function scrollTo(
    _options?: ScrollToOptions | number,
    _top?: number,
  ) {
    // jsdom does not implement scrolling; no-op for tests.
  };
  Object.defineProperty(Element.prototype, "scrollHeight", {
    configurable: true,
    get() {
      return 0;
    },
  });
  Object.defineProperty(Element.prototype, "scrollTop", {
    configurable: true,
    get() {
      return 0;
    },
    set(_value: number) {},
  });
  Object.defineProperty(Element.prototype, "clientHeight", {
    configurable: true,
    get() {
      return 0;
    },
  });
}

if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
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
}
