// Print the combined QA report to an A4 PDF with page numbers (Chrome via Playwright).
import { chromium } from "../../../frontend/node_modules/@playwright/test/index.mjs";
import path from "node:path";
const dir = path.resolve(process.argv[2] ?? "..");
const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage();
await page.goto("file://" + path.join(dir, "CampusHub_QA_Report.html"), { waitUntil: "load" });
await page.pdf({
  path: path.join(dir, "CampusHub_QA_Report.pdf"), format: "A4", printBackground: true,
  margin: { top: "18mm", bottom: "18mm", left: "15mm", right: "15mm" },
  displayHeaderFooter: true,
  headerTemplate: `<div style="font-size:7pt;color:#64748b;width:100%;padding:0 15mm;display:flex;justify-content:space-between">
    <span>CampusHub · QA, Production Readiness &amp; Stress Testing</span><span>19 October 2026</span></div>`,
  footerTemplate: `<div style="font-size:7pt;color:#64748b;width:100%;text-align:center">
    Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>`,
});
await browser.close();
console.log("pdf written");
