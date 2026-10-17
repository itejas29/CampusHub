import { expect, test } from "@playwright/test";
import { ACCOUNTS, apiGet, signIn } from "./helpers";

/**
 * The CSSI cycle as the coordinator runs it. In the seed, the Semester II
 * registration window has already closed and every student has a mentor, so the
 * next step is to open posters, presentations and marks — which tells every
 * student who their mentor is.
 */
const SEM3_STUDENT = "riya.chauhan.031@campushub.example.com";

function local(daysFromNow: number, hour = 10): string {
  const d = new Date();
  d.setDate(d.getDate() + daysFromNow);
  d.setHours(hour, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

test("the coordinator opens presentations, and a student is told their mentor", async ({ page, browser }) => {
  await signIn(page, ACCOUNTS.cssiCoordinator);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Windows & Deadlines" }).click();
  await expect(page.getByRole("heading", { name: "Windows & deadlines" })).toBeVisible();

  const registration = page.getByRole("listitem").filter({ hasText: "Step 1" });
  await expect(registration).toContainText("Closed");
  const presentations = page.getByRole("listitem").filter({ hasText: "Step 3" });
  await presentations.getByRole("button", { name: "Open & notify" }).click();

  const dialog = page.getByRole("dialog");
  await dialog.locator("#w-message").fill(
    "Bring a printed A1 poster. Presentations are 5 minutes plus questions.");
  await dialog.locator("#w-open").fill(local(0, 0));
  await dialog.locator("#w-due").fill(local(3));
  await dialog.locator("#w-from").fill(local(5).slice(0, 10));
  await dialog.locator("#w-close").fill(local(10));
  await dialog.getByRole("button", { name: "Open and notify" }).click();

  await expect(dialog).toBeHidden();
  await expect(presentations).toContainText("Open");
  await expect(presentations).toContainText("Message sent to students");

  // A Semester III student now sees the open window and their own mentor.
  const studentContext = await browser.newContext();
  const student = await studentContext.newPage();
  await signIn(student, SEM3_STUDENT);
  const notes = await apiGet<{ items?: { title: string }[] } | { title: string }[]>(
    student, "/notifications");
  const titles = (Array.isArray(notes) ? notes : notes.items ?? []).map((n) => n.title);
  expect(titles.some((t) => /your mentor is/i.test(t))).toBeTruthy();

  await student.goto("/internships");
  const card = student.getByRole("region").or(student.locator("section")).filter({ hasText: "Posters, presentation & marks" }).first();
  await expect(card).toContainText("Open");
  await student.getByRole("button", { name: "Mentor list" }).first().click();
  await expect(student.getByRole("dialog").getByText("Your mentor")).toBeVisible();
  await studentContext.close();
});
