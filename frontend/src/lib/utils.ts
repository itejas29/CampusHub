import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  const parts = name.replace(/^(Dr|Prof|Mr|Ms|Mrs)\.?\s+/i, "").trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : ""))
    .toUpperCase();
}

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
export function roman(n?: number | null): string {
  return n && n > 0 && n < ROMAN.length ? ROMAN[n] : String(n ?? "");
}

/**
 * "PROGRAM_CORE_ELECTIVE" -> "Program core elective", while leaving domain
 * acronyms intact ("CSSI" stays "CSSI", not "Cssi").
 */
const ACRONYMS = new Set([
  "CSSI", "SI", "NGO", "MOOC", "NPTEL", "SWAYAM", "CPI", "SPI", "ICT", "VLSI",
  "FOET", "AI", "IOT", "HR", "OE", "PCE", "UG", "PG",
]);

export function humanise(value?: string | null): string {
  if (!value) return "";
  const words = value.split("_").filter(Boolean);
  const parts = words.map((word, index) => {
    if (ACRONYMS.has(word.toUpperCase()) && word === word.toUpperCase()) {
      return word === "FOET" ? "FoET" : word;
    }
    const lower = word.toLowerCase();
    return index === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
  });
  return parts.join(" ");
}

export function pluralise(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
