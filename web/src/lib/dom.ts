// Tiny DOM helper: build elements without innerHTML (ride/segment names are data, not markup).

type Child = Node | string | null | undefined | false;

export function h(
  tag: string,
  attrs: Record<string, string> = {},
  ...children: Child[]
): HTMLElement {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  for (const c of children) if (c) el.append(c);
  return el;
}
