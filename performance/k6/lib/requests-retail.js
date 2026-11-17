// Fills date placeholders in a request body or path with one CSV row.
// Placeholders: {{START_DATE}} {{END_DATE}}
export function templateBody(value, row) {
  if (value === null || value === undefined) return value;
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text
    .split("{{START_DATE}}").join(row.start_date)
    .split("{{END_DATE}}").join(row.end_date);
}
