/* Deai Canvas — design-system tokens for the inspector's «is this a token?» check.

   Empty by default: the inspector works without a design system and simply
   doesn't classify values as on/off-system. To enable the check, export your
   tokens per «profile» (any string you put into a task's `profile`) as a map
   `{ tokenName: [values…] }` — one token may carry several values (@media):

     export const DS_PROFILES = { mybrand: { '--color-primary': ['#0055ff'], ... } };

   The shape is exactly what `dsIndex` (`app/vendor/inspector-core.js`) takes:
   a bare `{ name: [values] }` map per profile — NOT wrapped in `{ tokens: … }`
   (a wrapper would make `tokens` itself the only token). A bare string value
   is accepted and read as a one-element list.

   A SPACE's own tokens (module role `tokens`, e.g. the built-in `css-tokens`)
   do not go here: the inspector fetches them at runtime from
   `GET /api/ds-tokens?space=<id>` and uses the same `{ name: [values] }` shape
   under the profile `space:<id>`. This file stays the static fallback.
*/
export const DS_SOURCE = { commit: null, digest: null, figma: null, files: {}, proto: null };
export const DS_PROFILES = {};
