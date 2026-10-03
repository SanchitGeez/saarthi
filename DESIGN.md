# Saarthi design system

## Direction

An adult opens Saarthi after a demanding day, in ordinary indoor light, wanting a calm spiritual conversation. Type and settings use white as their primary surface, deep maroon for identity and actions, and restrained saffron for scripture and sacred accents. It feels devotional through a diya-and-lotus mark, Devanagari, and thoughtful typography, while chat controls stay familiar. The call home uses a dark photographic temple scene, described below.

## Palette

Native sRGB tokens live in `mobile/src/theme.ts`. Use semantic tokens, not per-screen colours.

| Role | Colour | Use |
| --- | --- | --- |
| Background | #FFFFFF | Main conversation |
| Surface | #FAF6F4 | Drawer, user messages |
| Ink | #302025 | Main reading text |
| Body | #59484D | Supporting text |
| Quiet | #79636A | Placeholders and helper copy |
| Primary | #792F42 | Actions and brand |
| Accent | #AA4D16 | Scripture and devotional labels |
| Gold wash | #FFF5E8 | Scripture cards and brand mark |
| Border | #E4DADB | Dividers and control boundaries |
| Danger | #A12C31 | Failure and destructive actions |
| Success | #34654D | Settings success feedback |

All reading text and placeholders must meet 4.5:1 on their actual surfaces. Filled primary actions use white text. Disabled actions stay visibly disabled and expose their state to assistive technology.

## Typography and imagery

Use the system sans for conversation, controls, and settings. Platform serif is reserved for the brand and introductory reflection. Body text is 16–17 px with 25–28 px line height. Sanskrit verses use the system Devanagari fallback at 18 px and 32 px line height. Respect system text scaling; avoid fixed-height text containers.

The mark is an original geometric diya held by a lotus. Its SVG source and rendered launcher/favicon assets live in `mobile/assets`. The call scene uses the user-supplied portrait in `mobile/assets/temple.png`, cropped to hide the reference image’s baked-in mock controls. Do not infer priestly credentials from the portrait or add more poses in this iteration.

## Interaction

Minimum touch target is 44 px. The composer is keyboard-aware on both native platforms. Type creates a conversation on first Send; a call creates one on start. The app opens on the dim temple scene, with history in a searchable drawer. Sign out is present in the drawer and account settings.

A failed user message remains visibly unfinished with Retry and Remove. Retry preserves the original message ID. Pending messages reconcile with the server after lost responses and app foregrounding. Scrolling a conversation should not drag the user to the bottom while they are reading earlier messages; the Latest control provides a return path.

The main assistant response is readable prose, with a source-backed shlok inserted where relevant. Verse cards offer English/Hindi translation switches and a source link. Memory settings offer editing/deletion, not individual approval.

## Accessibility and motion

Label every icon control. Use radio semantics for language/translation choice, busy/disabled states for actions, and live announcements for useful status changes. Native back returns from settings. Dialogs use platform modal focus containment, Escape/back dismissal, and focus restoration. Reduced-motion settings disable animated scrolling/drawer transitions. Default content is always visible; no reveal animations gate rendering.

## Parth call scene

The call home uses the supplied temple portrait as one cropped background. Before a call it is dark and at 20% opacity; after connection it fades into the full image. Respect reduced motion. Use the existing icon family, a broad microphone action labeled Baat karein, and a small TYPE action with a keyboard icon. During a call show captions, actual agent state, mute and End. History and memory stay in the drawer. The name is Parth, visibly identified as AI. No random activities or additional generated poses in this iteration. The existing text theme remains for Type and settings.
