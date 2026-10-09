/* Deai Canvas — design-system tokens for the inspector's «is this a token?» check.

   Empty by default: the inspector works without a design system and simply
   doesn't classify values as on/off-system. To enable the check, export your
   tokens per «profile» (any string you put into a task's `profile`):

     export const DS_PROFILES = { mybrand: { tokens: { '--color-primary': '#0055ff', ... } } };

   The shape mirrors what `app/vendor/inspector-dom.js` reads (`dsIndex`).
*/
export const DS_SOURCE = { commit: null, digest: null, figma: null, files: {}, proto: null };
export const DS_PROFILES = {};
