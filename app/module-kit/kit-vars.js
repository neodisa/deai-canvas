/* Custom properties the panel kit (kit.css) reads. The shell imports this list and sends their current values to the panel
   (events `init` and `theme` of the bridge). Every name must be defined in app/styles.css (guarded by a test). */
export const KIT_VARS = [
  "--s1", "--s2", "--s3", "--line", "--line2", "--hi", "--mid", "--dim",
  "--sel", "--sel-hover", "--on-sel", "--bad", "--r", "--r-sm", "--h-ctl",
];
