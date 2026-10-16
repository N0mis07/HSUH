# HSUH interface guide

## Direction

HSUH is a friendly place to talk to Hermes and get work done from a computer or
phone. Chat is the default and the visual focus. The current direction is light,
rounded and spacious, with the original Mote buddy present in the conversation.
Keep detailed telemetry and native controls in their own views.

The main chat shows at most three small measured stats: RAM use, the first Codex
quota window, and active Hermes agents. The Stats view holds detailed readings,
sources and reset times. Work & tools holds tasks, schedules, tools and sessions.
Do not turn the default screen back into a dense dashboard.

## Palette and depth

Use the semantic variables in `hsuh/static/style.css` as the source of truth.

| Role | Token | Value |
| --- | --- | --- |
| Sage canvas | `--console` | `#f3f6f0` |
| Main panel | `--panel` | `#ffffff` |
| Inset surface | `--inset` | `#f0f3ed` |
| Selected surface | `--raised` | `#e6eddf` |
| Main text | `--ink` | `#29382e` |
| Supporting text | `--secondary` | `#506152` |
| Muted text | `--muted` | `#697768` |
| Primary action | `--signal` | `#355b42` |
| User bubble | `--bubble` | `#e6efdf` |
| Success | `--success` | `#59805b` |
| Attention | `--warning` | `#886325` |
| Failure | `--danger` | `#a45248` |

Use tonal surfaces and space to group content. Borders are quiet green tints,
using `--edge` and `--edge-strong`; avoid framing every label or metric. The
composer has a very light shadow and a clear focus border. Keep shadows subtle.

## Layout and typography

- Desktop: 76px top bar, 244px sidebar, one conversation panel. The sidebar
  becomes 216px below 1000px. Only the chat list scrolls inside the sidebar;
  navigation and New chat remain reachable. Long titles truncate within the list.
- At 720px and below: 64px top bar and four 44px panel navigation buttons in a
  56px row. Show one panel at a time. Respect the bottom safe area.
- Chat content is about 780px wide; the dock is capped at 844px including padding.
  Let the conversation scroll independently of the composer.
- Use a 4px spacing base with 8/12/16px inside groups and 20/24/28/32px between
  larger groups. Preserve breathing room around the welcome buddy.
- Use the existing rounded/system sans-serif stack. Base text is 15px, supporting
  text 12–14px, and major headings 28–32px. Weights and color establish hierarchy.
  Keep monospace for code or technical detail, rather than general navigation.
- Mobile message input stays at 16px. Short desktop windows use the compact
  welcome treatment so suggestions and the composer fit without scrolling.

## Reusable patterns

| Pattern | Established treatment |
| --- | --- |
| Main conversation panel | 28px radius, 24px on phone |
| Primary button | 42px minimum desktop height, 44px on phone, 14px radius |
| New chat | 46px minimum height, 16px radius |
| Composer | White, 24px radius, 22px on phone, 18/20px padding on desktop |
| User message | Sage bubble, 22/22/6/22px radii, aligned right |
| Hermes reply | Open text with Mote avatar, readable line spacing |
| Chat buddy | 52px in the header, 44px on phone, 32px beside assistant replies |
| Task activity | Native disclosure, collapsed by default outside attention cards |
| Permission request | Warm attention surface, exact operation and clear decision buttons |
| Work tabs | One quiet inset track with a white selected tab |
| Detailed stats | Separate view, rounded panels, source and unavailable states retained |

## Buddy and interaction states

Mote is the original local SVG in `hsuh/static/mascot.svg`. Use it in the favicon,
chat header, empty conversation and assistant reply metadata. Keep it small enough
that it supports the conversation instead of competing with messages.

The buddy status follows the selected task: ready, working, waiting for an answer
or permission, stopping, reconnecting, interrupted or failed. Its gentle working
motion is limited to active work and disabled for reduced motion. Do not invent
progress, emotions, tool use or resource numbers.

Suggested messages fill an editable draft; they never send automatically. Preserve
drafts when switching conversations and preserve chat buttons across unchanged
polls. Native steering, stop and approvals must still target the exact owned run.
Questions and approval requests remain directly visible, outside collapsed logs.

## Accessibility and acceptance

Use native buttons, inputs and disclosures. Retain the 2px focus outline, disabled
states, descriptive labels, 44px phone targets and reduced-motion behavior. Keep
model content untrusted and separate generated UI from authoritative host stats.

Verify meaningful UI changes in an actual desktop and 390px phone viewport.
Check short windows, long titles, a real reply, active work, permission cards,
composer visibility and horizontal overflow. Restore the normal viewport afterward.
Use fictional data for screenshots committed or shared publicly. Keep private
conversations, live quota balances and host telemetry out of the repository.
