/** Local preflight only. The backend importer remains authoritative and atomic. */
export const requiredColumns = ["external_id", "conversation_id", "author", "content", "timestamp"] as const;
export type CsvIssue = { row: number | null; column: string; issue: string; fix: string };
export type CsvMessage = { row: number; external_id: string; conversation_id: string; author: string; content: string; timestamp: string };
export type CsvValidation = { messages: CsvMessage[]; issues: CsvIssue[]; validCount: number; totalCount: number };
const empty = (issues: CsvIssue[]): CsvValidation => ({ messages: [], issues, validCount: 0, totalCount: 0 });
export function fileIssue(name: string, size: number): CsvIssue | null {
  if (!/\.csv$/i.test(name)) return { row: null, column: "file", issue: "Invalid file type.", fix: "Choose a UTF-8 .csv file." };
  if (size > 5 * 1024 * 1024) return { row: null, column: "file", issue: "File exceeds 5 MB.", fix: "Split the file into smaller imports." };
  if (!size) return { row: null, column: "file", issue: "The file is empty.", fix: "Add the required headers and at least one message." };
  return null;
}
/** Quoted commas, escaped quotes and multiline cells; rows retain CSV line numbers. */
function parse(text: string): { cells: string[]; line: number }[] {
  const rows: { cells: string[]; line: number }[] = [];
  let cells: string[] = [], cell = "", quoted = false, closed = false, line = 1, start = 1;
  function finish() { cells.push(cell); if (cells.some(x => x.length) || cells.length > 1) rows.push({ cells, line: start }); cells = []; cell = ""; closed = false; start = line + 1; }
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') { quoted = false; closed = true; }
      else { cell += c; if (c === "\n") line++; }
    } else if (c === '"') {
      if (cell || closed) throw new Error("Unexpected quote in an unquoted cell.");
      quoted = true;
    } else if (c === ",") { cells.push(cell); cell = ""; closed = false; }
    else if (c === "\n" || c === "\r") { finish(); if (c === "\r" && text[i + 1] === "\n") i++; line++; }
    else { if (closed) throw new Error("Unexpected text after a closing quote."); cell += c; }
  }
  if (quoted) throw new Error("An opening quote has no closing quote.");
  if (cell || cells.length || closed) finish();
  return rows;
}
export function validateCsv(text: string): CsvValidation {
  let parsed: ReturnType<typeof parse>;
  try { parsed = parse(text.replace(/^\uFEFF/, "")); }
  catch (reason) { return empty([{ row: null, column: "file", issue: reason instanceof Error ? reason.message : "Malformed CSV.", fix: "Check CSV quoting and delimiters." }]); }
  const [header, ...rows] = parsed;
  if (!header) return empty([{ row: null, column: "file", issue: "The file is empty.", fix: "Add the required headers and at least one message." }]);
  const missing = requiredColumns.filter(column => !header.cells.includes(column));
  if (missing.length || new Set(header.cells).size !== header.cells.length) return empty([{ row: 1, column: "headers", issue: missing.length ? `Missing columns: ${missing.join(", ")}.` : "Duplicate column names.", fix: `Use unique headers: ${requiredColumns.join(", ")}.` }]);
  if (!rows.length) return empty([{ row: null, column: "file", issue: "No messages found.", fix: "Add at least one message below the header." }]);
  if (rows.length > 500) return { ...empty([{ row: null, column: "file", issue: "CSV exceeds 500 messages.", fix: "Split the file into batches of 500 messages or fewer." }]), totalCount: rows.length };
  const issues: CsvIssue[] = [], messages: CsvMessage[] = [], seen = new Set<string>();
  let validCount = 0;
  for (const row of rows) {
    const before = issues.length;
    const value = Object.fromEntries(header.cells.map((column, i) => [column, (row.cells[i] || "").trim()]));
    const add = (column: string, issue: string, fix: string) => issues.push({ row: row.line, column, issue, fix });
    if (row.cells.length !== header.cells.length) add("row", "Column count does not match the header.", "Check delimiters and quote messages containing commas.");
    for (const column of requiredColumns) {
      if (!value[column]) add(column, column === "content" ? "Message text is empty." : `${column} is empty.`, column === "content" ? "Add message text." : `Provide ${column}.`);
      else if (column !== "timestamp" && Array.from(value[column]).length > (column === "content" ? 4000 : 200)) add(column, "Value is too long.", `Use at most ${column === "content" ? 4000 : 200} characters.`);
    }
    if (value.external_id && seen.has(value.external_id)) add("external_id", "Duplicate external_id.", "Use a unique message identifier.");
    seen.add(value.external_id);
    if (value.reply_to_external_id && Array.from(value.reply_to_external_id).length > 200) add("reply_to_external_id", "Value is too long.", "Use at most 200 characters.");
    if (value.timestamp) {
      if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(value.timestamp)) add("timestamp", "Timezone is missing.", "Include a timezone, such as +03:30 or Z.");
      else if (!/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(value.timestamp) || !Number.isFinite(Date.parse(value.timestamp))) add("timestamp", "Timestamp is invalid.", "Use an ISO timestamp, such as 2026-10-07T09:10:00+03:30.");
    }
    messages.push({ row: row.line, external_id: value.external_id, conversation_id: value.conversation_id, author: value.author, content: value.content, timestamp: value.timestamp });
    if (before === issues.length) validCount++;
  }
  return { messages, issues, validCount, totalCount: rows.length };
}
