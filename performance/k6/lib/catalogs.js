// Registry of test catalogs. Lines between the markers are added by /k6-recording-to-lib.
// Keep both marker comments.
import * as sample from "./pages/requests-sample.js";
// <k6-recording-to-lib:imports>

export const catalogs = {
  sample: sample.requests,
  // <k6-recording-to-lib:entries>
};
