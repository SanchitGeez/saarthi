import Svg, { Circle, Ellipse, Path, Rect } from "react-native-svg";
import type { ReactNode } from "react";
import { colors } from "../theme";

type Name = "menu" | "plus" | "send" | "mic" | "volume" | "close" | "settings" | "lock" | "more" | "leaf" | "back" | "check" | "trash" | "logout" | "retry" | "edit" | "book" | "search" | "down" | "stop";

export function Icon({ name, size = 22, color = colors.ink }: { name: Name; size?: number; color?: string }) {
  const common = { stroke: color, strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, fill: "none" };
  const paths: Record<Name, ReactNode> = {
    menu: <><Path {...common} d="M4 7h16M4 12h16M4 17h16" /></>,
    plus: <Path {...common} d="M12 5v14M5 12h14" />,
    send: <Path {...common} d="m4 5 16 7-16 7 3-7-3-7Zm3 7h13" />,
    mic: <><Rect {...common} x="9" y="3" width="6" height="12" rx="3" /><Path {...common} d="M5 11v1a7 7 0 0 0 14 0v-1M12 19v3m-4 0h8" /></>,
    volume: <><Path {...common} d="M4 10v4h4l5 4V6l-5 4H4Z" /><Path {...common} d="M17 9a5 5 0 0 1 0 6m2-9a9 9 0 0 1 0 12" /></>,
    close: <Path {...common} d="m6 6 12 12M18 6 6 18" />,
    settings: <><Circle {...common} cx="12" cy="12" r="3" /><Path {...common} d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.6a8 8 0 0 1-1.6.9l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.6-.9l-1.7.6-1.4-2.4 1.4-1.1a8 8 0 0 1 0-1.9l-1.4-1.1 1.4-2.4 1.7.6a8 8 0 0 1 1.6-.9l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.6.9l1.7-.6 1.4 2.4-1.4 1.1a8 8 0 0 1 0 1.8Z" /></>,
    lock: <><Rect {...common} x="5" y="10" width="14" height="11" rx="2" /><Path {...common} d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3" /></>,
    more: <><Circle cx="5" cy="12" r="1.2" fill={color} /><Circle cx="12" cy="12" r="1.2" fill={color} /><Circle cx="19" cy="12" r="1.2" fill={color} /></>,
    leaf: <><Path {...common} d="M20 4C9 4 4 9 4 15a5 5 0 0 0 5 5c6 0 11-5 11-16Z" /><Path {...common} d="M5 19c3-4 7-7 12-10" /></>,
    back: <><Path {...common} d="m15 18-6-6 6-6" /><Path {...common} d="M9 12h11" /></>,
    check: <Path {...common} d="m5 12 4 4L19 6" />,
    trash: <><Path {...common} d="M4 7h16M10 11v6m4-6v6M6 7l1 14h10l1-14M9 7V4h6v3" /></>,
    logout: <><Path {...common} d="M10 4H5v16h5M10 12h11m-4-4 4 4-4 4" /></>,
    retry: <><Path {...common} d="M3 11a9 9 0 1 1 2 7M3 4v7h7" /></>,
    edit: <><Path {...common} d="m15 4 5 5M4 20l5-1L20 8a3.5 3.5 0 0 0-5-5L4 14v6Z" /></>,
    book: <><Path {...common} d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15" /></>,
    search: <><Circle {...common} cx="10" cy="10" r="6" /><Path {...common} d="m15 15 5 5" /></>,
    down: <Path {...common} d="m6 9 6 6 6-6" />,
    stop: <Rect x="6" y="6" width="12" height="12" rx="2" fill={color} />,
  };
  return <Svg width={size} height={size} viewBox="0 0 24 24" accessible={false}>{paths[name]}</Svg>;
}

// A diya held by an open lotus: clear at avatar size, meaningful without a portrait.
export function SaarthiMark({ size = 38 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 64 64" accessible={false}>
      <Circle cx="32" cy="32" r="31" fill={colors.goldWash} />
      <Path d="M32 9c-5 7-8 10-8 15a8 8 0 0 0 16 0c0-5-4-9-8-15Z" fill={colors.accent} />
      <Path d="M32 19c-2 3-3 4-3 6a3 3 0 0 0 6 0c0-2-1-3-3-6Z" fill={colors.goldWash} />
      <Path d="M13 34c2 14 12 20 19 20s17-6 19-20c-8 1-14 5-19 12-5-7-11-11-19-12Z" fill={colors.primary} />
      <Path d="M32 35c-3 4-6 8-6 12a6 6 0 0 0 12 0c0-4-3-8-6-12Z" fill={colors.gold} />
      <Path d="M20 57h24" stroke={colors.primary} strokeWidth="2" strokeLinecap="round" />
    </Svg>
  );
}
