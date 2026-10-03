import { useEffect, useRef, type RefObject } from "react";
import { Platform, type View } from "react-native";

type Layer = { root: RefObject<View | null> };
const layers: Layer[] = [];
const background = new Map<HTMLElement, { inert: boolean; aria: string | null }>();
let originalOverflow = "";

function syncLayers() {
  const active = layers[layers.length - 1];
  if (!active) {
    background.forEach(({ inert, aria }, node) => {
      node.inert = inert;
      if (aria === null) node.removeAttribute("aria-hidden");
      else node.setAttribute("aria-hidden", aria);
    });
    background.clear();
    document.body.style.overflow = originalOverflow;
    return;
  }
  let portal = active.root.current as unknown as HTMLElement | null;
  if (!portal) return;
  while (portal.parentElement && portal.parentElement !== document.body) portal = portal.parentElement;
  document.body.style.overflow = "hidden";
  for (const child of Array.from(document.body.children)) {
    if (!(child instanceof HTMLElement)) continue;
    if (!background.has(child)) background.set(child, { inert: child.inert, aria: child.getAttribute("aria-hidden") });
    // An existing, previously inactive modal portal may already be inert.
    // Always enable the top portal rather than inheriting its hidden state.
    child.inert = child !== portal;
    if (child === portal) child.removeAttribute("aria-hidden");
    else child.setAttribute("aria-hidden", "true");
  }
}

// Native Modal provides containment/back handling. Web also needs its background
// hidden from assistive technology, including during the entrance transition.
export function useModalAccessibility(visible: boolean, root: RefObject<View | null>, onClose: () => void, busy = false) {
  const callback = useRef(onClose); callback.current = onClose;
  const blocked = useRef(busy); blocked.current = busy;
  useEffect(() => {
    if (!visible || Platform.OS !== "web") return;
    const previous = document.activeElement as HTMLElement | null;
    if (!layers.length) originalOverflow = document.body.style.overflow;
    const layer: Layer = { root };
    layers.push(layer);
    const focusables = () => Array.from((root.current as unknown as HTMLElement)?.querySelectorAll<HTMLElement>('button, input, textarea, [role="button"], [role="radio"], [role="switch"], [tabindex="0"]') ?? []).filter(e => e.getAttribute("aria-disabled") !== "true" && e.getBoundingClientRect().height > 0);
    const frame = requestAnimationFrame(() => {
      if (layers[layers.length - 1] !== layer) return;
      syncLayers();
      focusables()[0]?.focus();
    });
    const keydown = (event: KeyboardEvent) => {
      if (layers[layers.length - 1] !== layer) return;
      if (event.key === "Escape") { event.preventDefault(); if (!blocked.current) callback.current(); }
      else if (event.key === "Tab") {
        const targets = focusables(); if (!targets.length) return;
        const first = targets[0], last = targets[targets.length - 1];
        if (event.shiftKey && (document.activeElement === first || !targets.includes(document.activeElement as HTMLElement))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      cancelAnimationFrame(frame); document.removeEventListener("keydown", keydown);
      const wasTop = layers[layers.length - 1] === layer;
      const index = layers.indexOf(layer);
      if (index >= 0) layers.splice(index, 1);
      syncLayers();
      if (wasTop) requestAnimationFrame(() => {
        // Do not steal focus if another modal opened during this cleanup.
        const active = layers[layers.length - 1]?.root.current as unknown as HTMLElement | undefined;
        if (!active || (previous && active.contains(previous))) previous?.focus();
      });
    };
  }, [visible, root]);
}
