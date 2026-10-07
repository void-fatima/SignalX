"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, type ImportResult } from "@/lib/api";
import Icon from "@/components/Icon";
import Avatar from "@/components/leads/Avatar";
import { useWorkspaceProducts } from "@/components/useWorkspaceProducts";
import { DemoNotice, PageHeading, Panel, TableScroll } from "@/components/workflow/WorkflowUI";
import { fileIssue, requiredColumns, validateCsv, type CsvValidation, type CsvIssue } from "@/lib/csv-validation";
import { demoValidation } from "@/lib/demo-import";
import { saveRunContext } from "@/lib/run-context";
import "@/app/workflow.css";
import "./imports.css";

export default function Imports() {
  const router = useRouter(), workspace = useWorkspaceProducts();
  const { demo, products, selectedProductId, setSelectedProductId, setSelectionLocked, loading } = workspace;
  const input = useRef<HTMLInputElement>(null), version = useRef(0), key = useRef<string | null>(null);
  const [file, setFile] = useState<File | null>(null), [validation, setValidation] = useState<CsvValidation | null>(null);
  const [community, setCommunity] = useState("Developer community"), [busy, setBusy] = useState(false), [reading, setReading] = useState(false);
  const [error, setError] = useState(""), [serverIssues, setServerIssues] = useState<CsvIssue[]>([]);
  const [result, setResult] = useState<ImportResult | null>(null);
  useEffect(() => {
    ++version.current; setFile(null); setValidation(demo ? demoValidation : null); setResult(null); setError(""); setServerIssues([]); setBusy(false); setReading(false); key.current = null;
    if (input.current) input.current.value = "";
    return () => { ++version.current; };
  }, [demo]);
  useEffect(() => { key.current = null; }, [selectedProductId]);
  useEffect(() => { setSelectionLocked(busy); return () => setSelectionLocked(false); }, [busy, setSelectionLocked]);
  const issues = [...(validation?.issues || []), ...serverIssues];
  const attention = new Set(issues.filter(i => i.row && i.row > 1).map(i => i.row)).size;
  const canStart = !!file && !!validation?.totalCount && !issues.length && !!selectedProductId && !!community.trim() && community.trim().length <= 200 && !busy && !reading && !loading && !workspace.error;
  async function selectFile(chosen: File | undefined) {
    if (!chosen) return;
    const current = ++version.current;
    setFile(chosen); setValidation(null); setResult(null); setServerIssues([]); setError(""); key.current = null;
    const issue = fileIssue(chosen.name, chosen.size);
    if (issue) { setValidation({ messages: [], issues: [issue], validCount: 0, totalCount: 0 }); return; }
    setReading(true);
    try {
      const text = new TextDecoder("utf-8", { fatal: true }).decode(await chosen.arrayBuffer());
      if (version.current === current) setValidation(validateCsv(text));
    } catch { if (version.current === current) setValidation({ messages: [], issues: [{ row: null, column: "file", issue: "File is not valid UTF-8.", fix: "Export the CSV with UTF-8 encoding." }], validCount: 0, totalCount: 0 }); }
    finally { if (version.current === current) setReading(false); }
  }
  async function start() {
    if (!canStart || !file || !validation) return;
    setBusy(true); setError("");
    const context = { product: products.find(p => p.id === selectedProductId)?.name || "Selected product", community: community.trim(), filename: file.name, total: validation.totalCount };
    if (demo) { saveRunContext("demo-import", context); router.push("/runs/demo-import?demo=1"); return; }
    try {
      let imported = result;
      if (!imported) {
        const data = new FormData(); data.set("file", file); data.set("community_name", community.trim());
        imported = await api.importCSV(data); setResult(imported);
      }
      key.current ||= crypto.randomUUID();
      const run = await api.startRun(selectedProductId, imported.batch.id, key.current);
      saveRunContext(run.id, context); localStorage.setItem("run_id", run.id); router.push(`/runs/${run.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start analysis. Please try again.");
      if (reason instanceof ApiError) setServerIssues(reason.details.map(d => ({ row: d.row || null, column: d.field || "file", issue: d.message || "Server validation failed.", fix: "Correct this value in the CSV and replace the file." })));
      setBusy(false);
    }
  }
  const filename = file?.name || (demo ? "developer-community.csv" : "No file selected");
  return <div className="workflow-page import-page"><PageHeading title="Import conversations"><p>Bring community messages into your workspace.</p></PageHeading>
    {demo && <DemoNotice>Sample validation · no messages imported. A valid replacement opens a static analysis preview.</DemoNotice>}
    <ol className="import-steps" aria-label="Import progress"><li className={validation ? "complete" : "active"} aria-current={!validation ? "step" : undefined}><span>{validation ? <Icon name="check" size={17}/> : 1}</span>Choose file</li><li className={validation ? "active" : ""} aria-current={validation ? "step" : undefined}><span>2</span>Validate</li><li><span>3</span>Analyze</li></ol>
    {(error || workspace.error) && <div className="workflow-error" role="alert"><p>{error || workspace.error}</p>{workspace.error && <><button className="workflow-secondary" onClick={workspace.retry}>Retry products</button> <Link href="/login">Sign in</Link></>}</div>}
    <div className="import-grid"><Panel title="Import source"><fieldset disabled={busy || reading} className="import-fields"><label htmlFor="import-product">Product</label><select id="import-product" value={selectedProductId} disabled={loading || busy || reading} onChange={e => setSelectedProductId(e.target.value)}><option value="">Select a product</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>{!loading && !products.length && !workspace.error && <p className="panel-description">Create a <Link href={demo ? "/products?demo=1" : "/products"}>product profile</Link> first.</p>}
    <label htmlFor="import-community">Community</label><input id="import-community" list="import-communities" value={community} maxLength={200} onChange={e => { setCommunity(e.target.value); setResult(null); setServerIssues([]); key.current = null; }} required/><datalist id="import-communities"><option value="Developer community"/><option value="DevTalk"/><option value="Backend club"/></datalist>
    <label htmlFor="import-file">CSV file</label><input className="csv-file-input" ref={input} id="import-file" type="file" accept=".csv,text/csv" onChange={e => void selectFile(e.target.files?.[0])}/><div className="csv-file-card"><span className="csv-file-icon"><Icon name="file" size={30}/></span><div><strong>{filename}</strong><small>{file ? `${validation?.totalCount ?? "—"} rows · ${(file.size / 1024).toFixed(1)} KB` : demo ? "22 rows · UTF-8 · sample" : "Choose a UTF-8 CSV to validate"}</small></div><button type="button" className="text-action" onClick={() => input.current?.click()}>{file || demo ? "Replace file" : "Choose file"}</button></div>
    <p className="import-hint"><Icon name="info" size={16}/>UTF-8 CSV · Up to 5 MB · Up to 500 messages</p><div className="csv-guidance"><h3>Required columns</h3><code>{requiredColumns.join(", ")}.</code><p className="import-hint"><Icon name="info" size={16}/>Timestamps must include a timezone, such as +03:30 or Z.</p></div></fieldset></Panel>
    <Panel title="Validation results" className="validation-panel" extra={validation && <div className="validation-counts"><span><Icon name="check" size={21}/>{validation.validCount} valid rows</span><span><Icon name="review" size={22}/>{attention || issues.length} need attention</span></div>}>
    {reading ? <p role="status" className="workflow-empty">Reading and validating CSV…</p> : !validation ? <p className="workflow-empty">Choose a file to inspect its rows before importing.</p> : <>
      {issues.length ? <div className="workflow-warning" role="alert"><Icon name="info" size={27}/><div><strong>{attention ? `Fix ${attention} ${attention === 1 ? "row" : "rows"} to continue.` : "Fix the CSV file to continue."}</strong><p>No messages have been imported yet.</p></div></div> : <div className="validation-success" role="status"><Icon name="check" size={23}/><div><strong>All {validation.totalCount} rows passed local validation.</strong><p>{demo ? "Demo preview only. No messages will be imported." : "The server will validate the complete file before importing."}</p></div></div>}
      {!!issues.length && <TableScroll label="CSV validation issues"><table className="validation-table"><thead><tr>{["Row", "Column", "Issue", "How to fix"].map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{issues.map((issue, i) => <tr key={i}><td>{issue.row ? `Row ${issue.row}` : "File"}</td><td>{issue.column}</td><td>{issue.issue}</td><td>{issue.fix}</td></tr>)}</tbody></table></TableScroll>}
      <section className="message-preview" aria-labelledby="preview-heading"><h3 id="preview-heading">Message preview</h3><TableScroll label="Imported message preview"><table><thead><tr>{["Row", "Author", "Message", "Timestamp"].map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{validation.messages.slice(0, 3).map((message, i) => <tr key={message.row}><td>{message.row - 1}</td><td><div className="workflow-person"><Avatar name={message.author} index={i} small/>{message.author || "Missing author"}</div></td><td className="preview-message" dir="auto">{message.content || "Empty message"}</td><td className="preview-timestamp">{message.timestamp || "Missing timestamp"}</td></tr>)}</tbody></table></TableScroll><p className="preview-note">First {Math.min(validation.messages.length, 3)} of {validation.totalCount} rows · preview only.</p></section>
    </>}
    {result && <p role="status" className="import-hint">{result.duplicate ? "Existing import reused" : "Server import complete"}: {result.count} messages. {result.warnings.length ? `${result.warnings.length} context warning(s).` : ""}</p>}{result?.warnings.map((warning, i) => <p className="import-hint" key={i}>Row {String(warning.row || "—")}: {String(warning.message || "Context warning")}</p>)}
    <div className="import-actions"><button type="button" onClick={() => input.current?.click()} disabled={busy || reading}><Icon name="file" size={19}/>Replace CSV</button><button type="button" className="workflow-secondary" disabled={!canStart} aria-describedby="analysis-block-reason" onClick={() => void start()}><Icon name="lock" size={18}/>{busy ? "Starting…" : demo && canStart ? "Preview analysis" : "Start analysis"}</button><p id="analysis-block-reason">{issues.length ? "Resolve the validation issues to continue." : !file ? "Choose a CSV file to continue." : !selectedProductId ? "Select a product to continue." : !community.trim() ? "Enter a community to continue." : demo ? "Static demo · no AI job starts." : "Imports all rows and creates a run using the server's configured provider."}</p></div>
    </Panel></div></div>;
}
