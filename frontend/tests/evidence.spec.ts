import { test, expect } from "@playwright/test";
import { demoDetails } from "../lib/demo-inbox";
import { filterLeads, groundedEvidence, signalDescription, textDirection } from "../lib/lead-presentation";

test("only exact source quotes from the same batch and conversation are grounded", () => {
  const detail = structuredClone(demoDetails["demo-lead-1"]);
  const foreign = { ...detail.message, id: "foreign", conversation_id: "other" };
  const otherBatch = { ...detail.message, id: "other-batch", batch_id: "other" };
  detail.context = [foreign, otherBatch];
  detail.analysis.evidence.push({ message_id: "foreign", quote: "دوره بک‌اند" }, { message_id: "other-batch", quote: "پروژه واقعی" }, { message_id: detail.message.id, quote: "invented phrase" });
  expect(groundedEvidence(detail).map(item => item.number)).toEqual([1, 2]);
});
test("nullable scores and unavailable signals never become invented metrics", () => {
  const detail = structuredClone(demoDetails["demo-lead-1"]);
  detail.analysis.lead_score = null;
  detail.analysis.signals = null;
  expect(filterLeads([detail.analysis], "", "0", "", { [detail.analysis.id]: detail })).toEqual([]);
  expect(signalDescription(detail.analysis)).toBe("No qualified signals");
  expect(textDirection("پروژه واقعی")).toBe("rtl");
  expect(textDirection("Signal analysis")).toBe("ltr");
});
