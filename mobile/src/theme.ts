import { Platform } from "react-native";

// Restrained saffron, vermilion, and deep maroon. Native-friendly sRGB tokens.
export const colors = {
  background: "#FFFFFF",
  surface: "#FAF6F4",
  ink: "#302025",
  body: "#59484D",
  primary: "#792F42",
  accent: "#AA4D16",
  border: "#E4DADB",
  river: "#F7EDE5",
  leaf: "#F7EDE5",
  white: "#FFFFFF",
  danger: "#A12C31",
  dangerWash: "#FFF0F0",
  success: "#34654D",
  quiet: "#79636A",
  gold: "#B36B22",
  goldWash: "#FFF5E8",
};
export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, section: 40 };
export const radii = { control: 12, panel: 16, pill: 999 };

export const fonts = { heading: Platform.OS === "ios" ? "Georgia" : "serif", body: Platform.OS === "web" ? "system-ui" : undefined };
