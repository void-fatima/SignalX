import { validateCsv } from "./csv-validation";
import { demoDetails } from "./demo-inbox";
/** Deliberately invalid synthetic CSV, mirroring the reference's two blocking rows. */
const people = ["Mina", "Alex", "Leila"];
export const demoCsv = "external_id,conversation_id,author,content,timestamp\n" + Array.from({ length: 22 }, (_, i) => {
  const content = i === 6 ? "" : i === 0 ? demoDetails["demo-lead-1"].message.content.replace(/\n/g, " ") : i === 1 ? "Looking for a practical backend course" : i === 2 ? "I want to learn by building an API" : "Looking for project-based backend learning";
  return `${i + 1},conversation-${i},${people[i] || `Member ${i + 1}`},"${content.replace(/"/g, '""')}",2026-10-07T09:${String(10 + i).padStart(2, "0")}:00${i === 15 ? "" : "+03:30"}`;
}).join("\n");
export const demoValidation = validateCsv(demoCsv);
