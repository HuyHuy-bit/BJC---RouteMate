/**
 * Literal mirrors of the brand tokens, for canvas-rendered contexts.
 *
 * Goong draws markers into a WebGL canvas, which cannot resolve CSS
 * custom properties — so these two values are the one sanctioned
 * exception to "no hex in components". They deliberately do NOT
 * flip with the theme: a pin's meaning (blue = pickup, red = dropoff)
 * has to stay stable against map tiles that are always light.
 *
 * They live here rather than in MapView.tsx so that callers can read
 * a colour without importing the component — which would drag the
 * whole goong-js bundle into the initial chunk and defeat the lazy
 * import in BookingForm.
 */
export const MAP_COLORS = {
  pickup: "#1f4380",
  dropoff: "#c7400a",
} as const;
