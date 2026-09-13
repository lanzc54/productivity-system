import React, { useState, useEffect, useMemo, useCallback } from "react";

const MD_PER_SLOT = 0.125;
const DEFAULT_ADMIN_USERNAME = "admin";

const TIME_SLOTS = Array.from({ length: 18 }, (_, i) => {
  const start = i + 6;
  const end = start + 1;
  return { id: `${start}-${end}`, label: `${start}:00–${end}:00` };
});

const DEFAULT_ENGAGEMENTS = [
  ["ITRA-NAPP-H001", "Mobile/Telco Management"],
  ["ITRA-NAPP-H002", "Risk Management and Information Security"],
  ["ITRA-NAPP-H003", "Audit of IT Services"],
  ["ITRA-NAPP-H004", "IT Business Continuity Planning and Management"],
  ["ITRA-NAPP-M001", "IT Outsourcing Process and Third Party Risk Management"],
  ["ITRA-NAPP-M002", "Network Security, Availability, Reliability & Integrity"],
  ["ITRA-NAPP-M003", "User Accounts Management"],
  ["ITRA-NAPP-M004", "Incident Report Creation, Assignment and Resolution"],
  ["ITRA-NAPP-M005", "Database Security and Management"],
  ["ITRA-NAPP-M006", "Applications Control Review - Financial Applications"],
  ["ITRA-NAPP-M007", "IT Asset Inventory & Management"],
  ["ITPP-NAPP-H001", "U Mobile App Revamp (Sprint 3)"],
  ["ITPP-NAPP-H002", "Manila Express - Project Payout"],
  ["ITPP-NAPP-H003", "UBS Payroll"],
  ["ITPP-NAPP-H004", "UBS - Terrapay Integration"],
  ["ITPP-NAPP-H005", "VISA Integration"],
  ["ITPP-NAPP-H006", "UnionPay Card"],
  ["ITPP-NAPP-H007", "Ria Mobile App Integration"],
  ["ITPP-NAPP-H008", "Eccobank savings products (direct to bank API)"],
  ["ITPP-NAPP-H009", "Xpress Money Integration - Branch Access"],
  ["ITPP-NAPP-H010", "WU IMT Outbound Payments via QRPH"],
  ["ITPP-NAPP-H011", "Express Pay Bills Payment"],
  ["ITPP-NAPP-M001", "DSWD Food Stamp"],
  ["ITPP-NAPP-M002", "Jobfix Payroll Project"],
  ["ITPP-NAPP-M003", "Bypro Payroll Disbursement - Onboarding & Enrollment"],
  ["ITPP-NAPP-M004", "CIS API v3"],
  ["ITPP-NAPP-M005", "DA Fertilizer"],
  ["ITPP-NAPP-M006", "DA Seeds/NRP"],
  ["ITPP-NAPP-M007", "USSC x CLSC - IMT Peralink"],
  ["ITPP-NAPP-M008", "Calaca Batangas Card"],
  ["ITPP-NAPP-M009", "U Visa Card Enrollment in MNLX"],
  ["ITPP-NAPP-M010", "USSC x GSIS - Pay1st Enhancement"],
  ["ITPP-NAPP-M011", "SSS Integration"],
].map(([code, description]) => ({ code, description, year: new Date().getFullYear(), annualBudgetMD: "", auditorBudgetMD: "" }));

const DEFAULT_ADMIN_CODES = [
  ["RDAY-NAPP-0000", "Restday"],
  ["HDAY-NAPP-0000", "Holiday"],
  ["LBRK-NAPP-0000", "Lunch break"],
  ["CSCY-NAPP-0000", "Consultancy / facilitation"],
  ["TRNG-NAPP-0000", "Training / seminars"],
  ["BMNG-NAPP-0000", "Business meeting"],
  ["ADMN-NAPP-0000", "Administrative"],
  ["VLVE-NAPP-0000", "Vacation leave"],
  ["SLVE-NAPP-0000", "Sick leave"],
  ["OLVE-NAPP-0000", "Other leaves"],
  ["SDAY-NAPP-0000", "Suspension day"],
  ["ITTL-NAPP-0000", "IT audit issue monitoring / scheduling"],
  ["ITSP-NAPP-0000", "IT special audit"],
].map(([code, description]) => ({ code, description }));

const DEFAULT_AUDITORS = [
  { initials: "CLL", name: "" },
  { initials: "LAC", name: "" },
  { initials: "JSL", name: "" },
  { initials: "LGA", name: "" },
];

const MAIN_CODES = [
  ["RDAY", "Restday"], ["HDAY", "Holiday"], ["LBRK", "Lunch break"],
  ["CSCY", "Consultancy: facilitation, documentation, review of procedures/contracts, other client tasks"],
  ["TRNG", "Training: probationary training, seminars, ITOP training"],
  ["BMNG", "Business meeting: quarterly, team, regional, cluster, annual meeting"],
  ["ADMN", "Administrative: filing, liquidation, documentation, TKS application/approval, other tasks"],
  ["NAPP", "Not applicable"], ["VLVE", "Vacation leave"], ["SLVE", "Sick leave"], ["OLVE", "Other leaves"],
  ["SDAY", "Suspension days"], ["ITRA", "IT audit: regular IT process audit"],
  ["ITPP", "IT audit: pre and post implementation audit"],
  ["ITTL", "IT audit: audit issue monitoring / scheduling"], ["ITSP", "IT special audit: IT related"],
];
const SUB_CODES = [
  ["OTRD", "Approved overtime restday (regardless if holiday)"],
  ["OTHD", "Approved overtime holiday with regular schedule"],
  ["OTEH", "Approved overtime extended hours"],
  ["TYRD", "Unapplied/unapproved overtime restday"],
  ["TYHD", "Unapplied/unapproved overtime holiday"],
  ["TYEH", "Unapplied/unapproved overtime extended hours"],
  ["NAPP", "Not applicable / regular day"],
];
const SERIES_CODES = [
  ["0000", "Not applicable"],
  ["H001–H999", "Chronological series by IT audit team leader for high-risk rating engagements"],
  ["M001–M999", "Chronological series by IT audit team leader for medium-risk rating engagements"],
  ["L001–L999", "Chronological series by IT audit team leader for low-risk rating engagements"],
];

function toDateStr(d) {
  return d.toISOString().slice(0, 10);
}
function startOfWeek(d) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  date.setDate(date.getDate() + diff);
  return date;
}
function formatDisplayDate(d) {
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
function round2(n) {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}
async function hashPassword(pw) {
  const enc = new TextEncoder().encode(pw);
  const buf = await crypto.subtle.digest("SHA-256", enc);
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

const STORAGE_PREFIX = "productivity-system:";

async function loadKey(key, fallback) {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + key);
    if (raw) return JSON.parse(raw);
    return fallback;
  } catch {
    return fallback;
  }
}
async function saveKey(key, value) {
  try {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
  } catch {
    // best effort
  }
}

async function serverSync(key, value) {
  try {
    const res = await fetch("/api/sync", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value }),
    });
    if (!res.ok) {
      throw new Error(`sync failed: ${res.status}`);
    }
  } catch (e) {
    // keep the app usable without silently losing local state
    console.warn("Server sync failed", e);
  }
}

async function loadServerData() {
  try {
    const res = await fetch("/api/data", { credentials: "same-origin" });
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    return null;
  }
}

const TABS = [
  { id: "entry", label: "Time entry" },
  { id: "engagements", label: "Engagements" },
  { id: "admin", label: "Non-engagement codes" },
  { id: "auditors", label: "Auditors" },
  { id: "monitoring", label: "Monitoring" },
  { id: "reference", label: "Code reference" },
];

export default function App() {
  const [tab, setTab] = useState("entry");
  const [loading, setLoading] = useState(true);
  const [engagements, setEngagements] = useState([]);
  const [adminCodes, setAdminCodes] = useState([]);
  const [auditors, setAuditors] = useState([]);
  const [engagementAssignments, setEngagementAssignments] = useState([]);
  const [entries, setEntries] = useState({});
  const [selectedAuditor, setSelectedAuditor] = useState("");
  const [weekStart, setWeekStart] = useState(startOfWeek(new Date()));
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [accounts, setAccounts] = useState([]);
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    (async () => {
      const serverData = await loadServerData();
      const [eng, adm, aud, assn, ent, acc] = await Promise.all([
        serverData?.["engagement-codes"] ?? loadKey("engagement-codes", DEFAULT_ENGAGEMENTS),
        serverData?.["admin-codes"] ?? loadKey("admin-codes", DEFAULT_ADMIN_CODES),
        serverData?.["auditors"] ?? loadKey("auditors", DEFAULT_AUDITORS),
        serverData?.["engagement-assignments"] ?? loadKey("engagement-assignments", []),
        serverData?.["time-entries"] ?? loadKey("time-entries", {}),
        serverData?.["accounts"] ?? loadKey("accounts", []),
      ]);
      setEngagements(eng);
      setAdminCodes(adm);
      setAuditors(aud);
      setEngagementAssignments(assn);
      setEntries(ent);
      if (aud.length) setSelectedAuditor(aud[0].initials);
      setAccounts(acc);
      setLoading(false);
    })();
  }, []);

  const codeLookup = useMemo(() => {
    const m = {};
    engagements.forEach((e) => (m[e.code] = { ...e, type: "engagement" }));
    adminCodes.forEach((c) => (m[c.code] = { ...c, type: "admin" }));
    return m;
  }, [engagements, adminCodes]);

  const persistEngagements = useCallback((next) => {
    setEngagements(next);
    saveKey("engagement-codes", next);
    serverSync("engagement-codes", next);
  }, []);
  const persistAdmin = useCallback((next) => {
    setAdminCodes(next);
    saveKey("admin-codes", next);
    serverSync("admin-codes", next);
  }, []);
  const persistAuditors = useCallback((next) => {
    setAuditors(next);
    saveKey("auditors", next);
    serverSync("auditors", next);
  }, []);
  const persistEntries = useCallback((next) => {
    setEntries(next);
    saveKey("time-entries", next);
    serverSync("time-entries", next);
  }, []);
  const persistAccounts = useCallback((next) => {
    setAccounts(next);
    saveKey("accounts", next);
    serverSync("accounts", next);
  }, []);

  async function handleLogin(username, password) {
    try {
      const res = await fetch("/api/login_json", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) return false;
      const payload = await res.json();
      setCurrentUser({ username: payload.username, role: payload.role, auditorInitials: payload.auditor || "" });
      if (payload.role === "auditor" && payload.auditor) setSelectedAuditor(payload.auditor);
      const serverData = await loadServerData();
      if (serverData) {
        if (serverData["engagement-codes"]) setEngagements(serverData["engagement-codes"]);
        if (serverData["admin-codes"]) setAdminCodes(serverData["admin-codes"]);
        if (serverData["auditors"]) setAuditors(serverData["auditors"]);
        if (serverData["engagement-assignments"]) setEngagementAssignments(serverData["engagement-assignments"]);
        if (serverData["time-entries"]) setEntries(serverData["time-entries"]);
        if (serverData["accounts"]) setAccounts(serverData["accounts"]);
      }
      return true;
    } catch (e) {
      return false;
    }
  }
  function handleLogout() {
    setCurrentUser(null);
  }

  const weekDates = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [weekStart]);

  useEffect(() => {
    if (loading || !selectedAuditor) return;
    const next = { ...entries };
    let changed = false;
    weekDates.forEach((d) => {
      const day = d.getDay();
      const dateStr = toDateStr(d);
      const key = entryKey(selectedAuditor, dateStr);
      const updated = { ...(next[key] || {}) };
      if (!updated["12-13"]) {
        updated["12-13"] = "LBRK-NAPP-0000";
        changed = true;
      }
      if (day === 0 || day === 6) {
        TIME_SLOTS.forEach((s) => {
          if (!updated[s.id]) {
            updated[s.id] = "RDAY-NAPP-0000";
            changed = true;
          }
        });
      }
      next[key] = updated;
    });
    if (changed) persistEntries(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, selectedAuditor, weekStart]);

  function entryKey(auditor, dateStr) {
    return `${auditor}__${dateStr}`;
  }
  function getSlotCode(auditor, dateStr, slotId) {
    const key = entryKey(auditor, dateStr);
    return (entries[key] && entries[key][slotId]) || "";
  }
  function setSlotCode(auditor, dateStr, slotId, code) {
    const key = entryKey(auditor, dateStr);
    const next = { ...entries };
    next[key] = { ...(next[key] || {}) };
    if (code) next[key][slotId] = code;
    else delete next[key][slotId];
    persistEntries(next);
  }

  const availableYears = useMemo(() => {
    const years = new Set(engagements.map((e) => String(e.year || new Date().getFullYear())));
    years.add(String(selectedYear));
    return Array.from(years).sort();
  }, [engagements, selectedYear]);

  const monitoring = useMemo(() => {
    const totals = {};
    engagements
      .filter((e) => String(e.year || "") === String(selectedYear))
      .forEach((e) => {
        totals[e.code] = { code: e.code, description: e.description, annualBudgetMD: e.annualBudgetMD, auditorBudgetMD: e.auditorBudgetMD, byAuditor: {} };
        auditors.forEach((a) => (totals[e.code].byAuditor[a.initials] = 0));
      });
    Object.entries(entries).forEach(([key, slots]) => {
      const [auditorInitials, dateStr] = key.split("__");
      if (!dateStr || dateStr.slice(0, 4) !== String(selectedYear)) return;
      Object.values(slots).forEach((code) => {
        if (totals[code]) {
          if (totals[code].byAuditor[auditorInitials] === undefined) totals[code].byAuditor[auditorInitials] = 0;
          totals[code].byAuditor[auditorInitials] += MD_PER_SLOT;
        }
      });
    });
    return Object.values(totals).map((row) => {
      const totalActual = Object.values(row.byAuditor).reduce((a, b) => a + b, 0);
      const budget = parseFloat(row.annualBudgetMD);
      const variance = isNaN(budget) ? null : round2(budget - totalActual);
      return { ...row, totalActual: round2(totalActual), variance };
    });
  }, [engagements, auditors, entries, selectedYear]);

  const adminUsage = useMemo(() => {
    const totals = {};
    adminCodes.forEach((c) => {
      totals[c.code] = { code: c.code, description: c.description, byAuditor: {} };
      auditors.forEach((a) => (totals[c.code].byAuditor[a.initials] = 0));
    });
    Object.entries(entries).forEach(([key, slots]) => {
      const [auditorInitials] = key.split("__");
      Object.values(slots).forEach((code) => {
        if (totals[code]) {
          if (totals[code].byAuditor[auditorInitials] === undefined) totals[code].byAuditor[auditorInitials] = 0;
          totals[code].byAuditor[auditorInitials] += MD_PER_SLOT;
        }
      });
    });
    return Object.values(totals).map((row) => {
      const totalUsed = Object.values(row.byAuditor).reduce((a, b) => a + b, 0);
      return { ...row, totalUsed: round2(totalUsed) };
    });
  }, [adminCodes, auditors, entries]);

  if (loading) {
    return <div style={{ padding: "2rem", color: "var(--text-secondary)", fontSize: 14 }}>Loading…</div>;
  }

  if (!currentUser) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  const canEdit = currentUser.role === "admin";
  const effectiveTabs = canEdit ? [...TABS, { id: "accounts", label: "Accounts" }] : TABS;

  return (
    <div style={{ fontFamily: "var(--font-sans, sans-serif)", color: "var(--text-primary, #1a1a1a)", maxWidth: 1100, margin: "0 auto" }}>
      <style>{`
        .pt-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .pt-table th, .pt-table td { border: 1px solid #E2E2DE; padding: 6px 8px; text-align: left; }
        .pt-table th { background: #17303D; color: #fff; font-weight: 500; font-size: 12px; }
        .pt-table select, .pt-table input { width: 100%; border: 1px solid #D8D8D2; border-radius: 4px; padding: 4px 6px; font-size: 12px; background: #fff; }
        .pt-table input:disabled { background: #F4F4F1; color: #5A5A54; }
        .pt-tab { padding: 8px 14px; border: none; background: transparent; cursor: pointer; font-size: 14px; color: #5A5A54; border-bottom: 2px solid transparent; }
        .pt-tab.active { color: #17303D; border-bottom: 2px solid #0F6E56; font-weight: 500; }
        .pt-btn { padding: 6px 12px; border-radius: 4px; border: 1px solid #17303D; background: #17303D; color: #fff; font-size: 13px; cursor: pointer; }
        .pt-btn.secondary { background: #fff; color: #17303D; }
        .pt-card { border: 1px solid #E2E2DE; border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #fff; }
        .pt-neg { color: #A32D2D; font-weight: 500; }
      `}</style>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontSize: 13, color: "#5A5A54" }}>
          Signed in as <strong>{currentUser.username}</strong> ({currentUser.role === "admin" ? "Admin" : "Auditor"})
        </span>
        <button className="pt-btn secondary" onClick={handleLogout}>Log out</button>
      </div>

      <div style={{ borderBottom: "1px solid #E2E2DE", marginBottom: 20, display: "flex", gap: 4, flexWrap: "wrap" }}>
        {effectiveTabs.map((t) => (
          <button key={t.id} className={`pt-tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "entry" && (
        <TimeEntryTab
          auditors={auditors}
          selectedAuditor={selectedAuditor}
          setSelectedAuditor={setSelectedAuditor}
          weekStart={weekStart}
          setWeekStart={setWeekStart}
          weekDates={weekDates}
          getSlotCode={getSlotCode}
          setSlotCode={setSlotCode}
          engagements={engagements}
          adminCodes={adminCodes}
          engagementAssignments={engagementAssignments}
          canChooseAuditor={canEdit}
        />
      )}
      {tab === "engagements" && <EngagementsTab engagements={engagements} onChange={persistEngagements} readOnly={!canEdit} />}
      {tab === "admin" && <AdminCodesTab adminCodes={adminCodes} onChange={persistAdmin} readOnly={!canEdit} />}
      {tab === "auditors" && <AuditorsTab auditors={auditors} onChange={persistAuditors} readOnly={!canEdit} />}
      {tab === "monitoring" && (
        <MonitoringTab
          rows={monitoring}
          adminRows={adminUsage}
          auditors={auditors}
          availableYears={availableYears}
          selectedYear={selectedYear}
          setSelectedYear={setSelectedYear}
        />
      )}
      {tab === "reference" && <ReferenceTab />}
      {tab === "accounts" && canEdit && (
        <AccountsTab accounts={accounts} auditors={auditors} onChange={persistAccounts} currentUsername={currentUser.username} />
      )}
    </div>
  );
}

function TimeEntryTab({ auditors, selectedAuditor, setSelectedAuditor, weekStart, setWeekStart, weekDates, getSlotCode, setSlotCode, engagements, adminCodes, engagementAssignments, canChooseAuditor }) {
  function shiftWeek(days) {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + days);
    setWeekStart(startOfWeek(d));
  }
  function assignedEngagementsForYear(year) {
    if (!selectedAuditor) return [];
    const match = new Set(
      engagementAssignments
        .filter((row) => row.auditor === selectedAuditor && String(row.year) === String(year))
        .map((row) => row.code)
    );
    return engagements.filter((e) => match.has(e.code) && String(e.year || "") === String(year));
  }
  return (
    <div>
      <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
        <div>
          <label style={{ fontSize: 12, color: "#5A5A54", display: "block", marginBottom: 4 }}>Auditor</label>
          {canChooseAuditor ? (
            <select value={selectedAuditor} onChange={(e) => setSelectedAuditor(e.target.value)} style={{ padding: "6px 8px", borderRadius: 4, border: "1px solid #D8D8D2" }}>
              {auditors.map((a) => (
                <option key={a.initials} value={a.initials}>
                  {a.initials}{a.name ? ` — ${a.name}` : ""}
                </option>
              ))}
            </select>
          ) : (
            <span style={{ fontSize: 13, fontWeight: 500, padding: "6px 0", display: "inline-block" }}>{selectedAuditor || "—"}</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "flex-end" }}>
          <button className="pt-btn secondary" onClick={() => shiftWeek(-7)}>&larr; Prev week</button>
          <span style={{ fontSize: 13, color: "#5A5A54", padding: "0 4px" }}>
            {formatDisplayDate(weekDates[0])} – {formatDisplayDate(weekDates[6])}
          </span>
          <button className="pt-btn secondary" onClick={() => shiftWeek(7)}>Next week &rarr;</button>
        </div>
      </div>

      {!auditors.length ? (
        <p style={{ color: "#5A5A54" }}>Add an auditor first, on the Auditors tab.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="pt-table">
            <thead>
              <tr>
                <th style={{ minWidth: 130 }}>Date</th>
                {TIME_SLOTS.map((s) => (
                  <th key={s.id} style={{ minWidth: 110 }}>{s.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {weekDates.map((d) => {
                const dateStr = toDateStr(d);
                const yearEngagements = assignedEngagementsForYear(d.getFullYear());
                return (
                  <tr key={dateStr}>
                    <td style={{ fontWeight: 500 }}>{formatDisplayDate(d)}</td>
                    {TIME_SLOTS.map((s) => (
                      <td key={s.id}>
                        <select
                          value={getSlotCode(selectedAuditor, dateStr, s.id)}
                          onChange={(e) => setSlotCode(selectedAuditor, dateStr, s.id, e.target.value)}
                        >
                          <option value="">—</option>
                          <optgroup label={`Assigned engagements (${d.getFullYear()})`}>
                            {yearEngagements.length ? (
                              yearEngagements.map((e) => (
                                <option key={e.code} value={e.code}>{e.code}</option>
                              ))
                            ) : (
                              <option value="" disabled>None assigned</option>
                            )}
                          </optgroup>
                          <optgroup label="Admin / non-engagement">
                            {adminCodes.map((c) => (
                              <option key={c.code} value={c.code}>{c.code}</option>
                            ))}
                          </optgroup>
                        </select>
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p style={{ fontSize: 12, color: "#888780", marginTop: 10 }}>Each logged hour counts as {MD_PER_SLOT} MD toward that code.</p>
    </div>
  );
}

function EngagementsTab({ engagements, onChange, readOnly }) {
  function update(idx, field, value) {
    const next = engagements.map((row, i) => (i === idx ? { ...row, [field]: value } : row));
    onChange(next);
  }
  function addRow() {
    onChange([{ code: "", description: "", year: new Date().getFullYear(), annualBudgetMD: "", auditorBudgetMD: "" }, ...engagements]);
  }
  function removeRow(idx) {
    onChange(engagements.filter((_, i) => i !== idx));
  }
  return (
    <div className="pt-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 500 }}>Engagement codes</h3>
        {!readOnly && <button className="pt-btn" onClick={addRow}>Add engagement</button>}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="pt-table">
          <thead>
            <tr>
              <th style={{ width: 150 }}>Code</th>
              <th>Description</th>
              <th style={{ width: 80 }}>Year</th>
              <th style={{ width: 130 }}>Annual budget MD</th>
              <th style={{ width: 150 }}>Budgeted MD / auditor</th>
              {!readOnly && <th style={{ width: 40 }}></th>}
            </tr>
          </thead>
          <tbody>
            {engagements.map((row, idx) => (
              <tr key={idx}>
                <td><input value={row.code} disabled={readOnly} onChange={(e) => update(idx, "code", e.target.value)} /></td>
                <td><input value={row.description} disabled={readOnly} onChange={(e) => update(idx, "description", e.target.value)} /></td>
                <td><input value={row.year} disabled={readOnly} onChange={(e) => update(idx, "year", e.target.value)} /></td>
                <td><input value={row.annualBudgetMD} disabled={readOnly} onChange={(e) => update(idx, "annualBudgetMD", e.target.value)} /></td>
                <td><input value={row.auditorBudgetMD} disabled={readOnly} onChange={(e) => update(idx, "auditorBudgetMD", e.target.value)} /></td>
                {!readOnly && <td><button className="pt-btn secondary" onClick={() => removeRow(idx)}>✕</button></td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AdminCodesTab({ adminCodes, onChange, readOnly }) {
  const [selectedIdx, setSelectedIdx] = useState(null);

  function update(idx, field, value) {
    const next = adminCodes.map((row, i) => (i === idx ? { ...row, [field]: value } : row));
    onChange(next);
  }
  function addRow() {
    setSelectedIdx(adminCodes.length);
    onChange([...adminCodes, { code: "", description: "" }]);
  }
  function removeRow(idx) {
    const next = adminCodes.filter((_, i) => i !== idx);
    onChange(next);
    if (selectedIdx === idx || selectedIdx === null) setSelectedIdx(null);
  }
  function removeSelectedRow() {
    if (selectedIdx === null || selectedIdx >= adminCodes.length) return;
    removeRow(selectedIdx);
  }
  return (
    <div className="pt-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 500 }}>Engagement codes</h3>
        {!readOnly && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button className="pt-btn secondary" disabled={selectedIdx === null} onClick={removeSelectedRow}>Delete code</button>
            <button className="pt-btn" onClick={addRow}>Add code</button>
          </div>
        )}
      </div>
      <p style={{ fontSize: 12, color: "#888780", marginTop: -6, marginBottom: 12 }}>These codes aren't budgeted and don't appear on the Monitoring tab.</p>
      <div style={{ overflowX: "auto" }}>
        <table className="pt-table">
          <thead>
            <tr>
              <th style={{ width: 180 }}>Code</th>
              <th>Description</th>
              {!readOnly && <th style={{ width: 40 }}></th>}
            </tr>
          </thead>
          <tbody>
            {adminCodes.map((row, idx) => (
              <tr key={idx} style={selectedIdx === idx ? { background: "#F3F6F1" } : undefined} onClick={() => setSelectedIdx(idx)}>
                <td><input value={row.code} disabled={readOnly} onChange={(e) => update(idx, "code", e.target.value)} onFocus={() => setSelectedIdx(idx)} /></td>
                <td><input value={row.description} disabled={readOnly} onChange={(e) => update(idx, "description", e.target.value)} onFocus={() => setSelectedIdx(idx)} /></td>
                {!readOnly && <td><button className="pt-btn secondary" style={{ display: "block", margin: "0 auto" }} onClick={(e) => { e.stopPropagation(); removeRow(idx); }}>✕</button></td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AuditorsTab({ auditors, onChange, readOnly }) {
  function update(idx, field, value) {
    const next = auditors.map((row, i) => (i === idx ? { ...row, [field]: value } : row));
    onChange(next);
  }
  function addRow() {
    onChange([...auditors, { initials: "", name: "" }]);
  }
  function removeRow(idx) {
    onChange(auditors.filter((_, i) => i !== idx));
  }
  return (
    <div className="pt-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 500 }}>Auditors</h3>
        {!readOnly && <button className="pt-btn" onClick={addRow}>Add auditor</button>}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="pt-table">
          <thead>
            <tr>
              <th style={{ width: 120 }}>Initials</th>
              <th>Name</th>
              {!readOnly && <th style={{ width: 40, textAlign: "center" }}></th>}
            </tr>
          </thead>
          <tbody>
            {auditors.map((row, idx) => (
              <tr key={idx}>
                <td><input value={row.initials} disabled={readOnly} onChange={(e) => update(idx, "initials", e.target.value.toUpperCase())} /></td>
                <td><input value={row.name} disabled={readOnly} onChange={(e) => update(idx, "name", e.target.value)} /></td>
                {!readOnly && (
                  <td style={{ width: 40, textAlign: "center" }}>
                    <button className="pt-btn secondary" style={{ display: "block", margin: "0 auto" }} onClick={() => removeRow(idx)}>✕</button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MonitoringTab({ rows, adminRows, auditors, availableYears, selectedYear, setSelectedYear }) {
  return (
    <div>
      <div className="pt-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 500 }}>Monitoring</h3>
          <div>
            <label style={{ fontSize: 12, color: "#5A5A54", marginRight: 6 }}>Year</label>
            <select value={selectedYear} onChange={(e) => setSelectedYear(e.target.value)} style={{ padding: "4px 8px", borderRadius: 4, border: "1px solid #D8D8D2" }}>
              {availableYears.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
        </div>
        <p style={{ fontSize: 12, color: "#888780", marginTop: 0, marginBottom: 12 }}>
          Actual MD is calculated automatically from Time entry, scoped to engagements and dates in {selectedYear}. Variance = annual budget MD − total actual MD.
        </p>
        <div style={{ overflowX: "auto" }}>
          <table className="pt-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Description</th>
                <th style={{ width: 100 }}>Annual budget MD</th>
                <th style={{ width: 110 }}>Budgeted MD / auditor</th>
                {auditors.map((a) => (
                  <th key={a.initials} style={{ width: 90 }}>Actual MD ({a.initials})</th>
                ))}
                <th style={{ width: 90 }}>Total actual</th>
                <th style={{ width: 90 }}>Variance</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.code}>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>{row.code}</td>
                  <td>{row.description}</td>
                  <td>{row.annualBudgetMD || "—"}</td>
                  <td>{row.auditorBudgetMD || "—"}</td>
                  {auditors.map((a) => (
                    <td key={a.initials}>{round2(row.byAuditor[a.initials] || 0)}</td>
                  ))}
                  <td>{row.totalActual}</td>
                  <td className={row.variance !== null && row.variance < 0 ? "pt-neg" : ""}>
                    {row.variance === null ? "—" : row.variance}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="pt-card">
        <h3 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 500 }}>Admin / non-engagement usage</h3>
        <p style={{ fontSize: 12, color: "#888780", marginTop: 0, marginBottom: 12 }}>
          How much time each auditor has logged against non-budgeted codes (restday, leave, lunch, etc.). No budget or variance — usage only.
        </p>
        <div style={{ overflowX: "auto" }}>
          <table className="pt-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Description</th>
                {auditors.map((a) => (
                  <th key={a.initials} style={{ width: 90 }}>MD used ({a.initials})</th>
                ))}
                <th style={{ width: 90 }}>Total used</th>
              </tr>
            </thead>
            <tbody>
              {adminRows.map((row) => (
                <tr key={row.code}>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>{row.code}</td>
                  <td>{row.description}</td>
                  {auditors.map((a) => (
                    <td key={a.initials}>{round2(row.byAuditor[a.initials] || 0)}</td>
                  ))}
                  <td>{row.totalUsed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ReferenceTab() {
  return (
    <div>
      <div className="pt-card">
        <h3 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 500 }}>How a code is built</h3>
        <p style={{ fontSize: 13, color: "#5A5A54", marginTop: 0 }}>MAINCODE-SUBCODE-SERIESCODE, e.g. ITRA-NAPP-M008</p>
      </div>
      <div className="pt-card">
        <h3 style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 500 }}>Main code</h3>
        <table className="pt-table">
          <tbody>
            {MAIN_CODES.map(([code, desc]) => (
              <tr key={code}><td style={{ width: 100, fontFamily: "monospace" }}>{code}</td><td>{desc}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pt-card">
        <h3 style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 500 }}>Sub code</h3>
        <table className="pt-table">
          <tbody>
            {SUB_CODES.map(([code, desc]) => (
              <tr key={code}><td style={{ width: 100, fontFamily: "monospace" }}>{code}</td><td>{desc}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pt-card">
        <h3 style={{ margin: "0 0 10px", fontSize: 14, fontWeight: 500 }}>Series code</h3>
        <table className="pt-table">
          <tbody>
            {SERIES_CODES.map(([code, desc]) => (
              <tr key={code}><td style={{ width: 120, fontFamily: "monospace" }}>{code}</td><td>{desc}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleLoginSubmit(e) {
    e.preventDefault();
    setError("");
    if (!username.trim() || !password) {
      setError("Enter a username and password.");
      return;
    }
    setBusy(true);
    const ok = await onLogin(username, password);
    setBusy(false);
    if (!ok) setError("Incorrect username or password.");
  }

  const boxStyle = { maxWidth: 360, margin: "80px auto", padding: 24, border: "1px solid #E2E2DE", borderRadius: 8, fontFamily: "var(--font-sans, sans-serif)" };
  const inputStyle = { width: "100%", boxSizing: "border-box", border: "1px solid #D8D8D2", borderRadius: 4, padding: "8px 10px", fontSize: 14, marginBottom: 10 };
  const labelStyle = { fontSize: 12, color: "#5A5A54", display: "block", marginBottom: 4 };
  const btnStyle = { width: "100%", padding: "8px 12px", borderRadius: 4, border: "1px solid #17303D", background: "#17303D", color: "#fff", fontSize: 14, cursor: "pointer" };

  return (
    <div style={boxStyle}>
      <h2 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 500 }}>Log in</h2>
      <form onSubmit={handleLoginSubmit}>
        <label style={labelStyle}>Username</label>
        <input style={inputStyle} value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        <label style={labelStyle}>Password</label>
        <div style={{ position: "relative" }}>
          <input style={{ ...inputStyle, paddingRight: 36 }} type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="button" onClick={() => setShowPassword((s) => !s)} aria-label={showPassword ? "Hide password" : "Show password"} style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", border: "1px solid #D8D8D2", background: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 14, lineHeight: 1, width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center", padding: 0 }}>
            {showPassword ? "🙈" : "👁"}
          </button>
        </div>
        {error && <p style={{ color: "#A32D2D", fontSize: 13, marginTop: -4 }}>{error}</p>}
        <button style={btnStyle} type="submit" disabled={busy}>{busy ? "Signing in…" : "Log in"}</button>
      </form>
      <p style={{ fontSize: 12, color: "#888780", marginTop: 14 }}>Don't have an account? Ask an admin to add one on the Accounts tab.</p>
    </div>
  );
}

function AccountsTab({ accounts, auditors, onChange, currentUsername }) {
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [newRole, setNewRole] = useState("auditor");
  const [newAuditorInitials, setNewAuditorInitials] = useState(auditors[0]?.initials || "");
  const [error, setError] = useState("");
  const [resetPw, setResetPw] = useState({});
  const [showResetPw, setShowResetPw] = useState({});
  const [showPlainTextPw, setShowPlainTextPw] = useState({});

  async function addAccount() {
    setError("");
    const uname = newUsername.trim();
    if (!uname || !newPassword) {
      setError("Username and password are required.");
      return;
    }
    if (accounts.some((a) => a.username.toLowerCase() === uname.toLowerCase())) {
      setError("That username already exists.");
      return;
    }
    if (newRole === "auditor" && !newAuditorInitials) {
      setError("Pick which auditor this account logs time for.");
      return;
    }
    if (newRole === "auditor" && accounts.some((a) => a.role === "auditor" && a.auditorInitials === newAuditorInitials)) {
      setError(`${newAuditorInitials} is already linked to another auditor account.`);
      return;
    }
    const passwordHash = await hashPassword(newPassword);
    const account = { username: uname, passwordHash, role: newRole, auditorInitials: newRole === "auditor" ? newAuditorInitials : "" };
    onChange([...accounts, account]);
    setNewUsername("");
    setNewPassword("");
  }

  function removeAccount(username) {
    onChange(accounts.filter((a) => a.username !== username));
  }

  async function submitReset(username) {
    const pw = resetPw[username];
    if (!pw) return;
    const passwordHash = await hashPassword(pw);
    onChange(accounts.map((a) => (a.username === username ? { ...a, passwordHash } : a)));
    setResetPw((prev) => ({ ...prev, [username]: "" }));
  }

  return (
    <div>
      <div className="pt-card">
        <h3 style={{ margin: "0 0 12px", fontSize: 16, fontWeight: 500 }}>Add account</h3>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div>
            <label style={{ fontSize: 12, color: "#5A5A54", display: "block", marginBottom: 4 }}>Username</label>
            <input value={newUsername} onChange={(e) => setNewUsername(e.target.value)} style={{ border: "1px solid #D8D8D2", borderRadius: 4, padding: "6px 8px" }} />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "#5A5A54", display: "block", marginBottom: 4 }}>Password</label>
            <div style={{ position: "relative" }}>
              <input type={showNewPassword ? "text" : "password"} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} style={{ border: "1px solid #D8D8D2", borderRadius: 4, padding: "6px 8px", paddingRight: 36 }} />
              <button type="button" onClick={() => setShowNewPassword((s) => !s)} aria-label={showNewPassword ? "Hide password" : "Show password"} style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", border: "1px solid #D8D8D2", background: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 14, lineHeight: 1, width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center", padding: 0 }}>
                {showNewPassword ? "🙈" : "👁"}
              </button>
            </div>
          </div>
          <div>
            <label style={{ fontSize: 12, color: "#5A5A54", display: "block", marginBottom: 4 }}>Role</label>
            <select value={newRole} onChange={(e) => setNewRole(e.target.value)} style={{ border: "1px solid #D8D8D2", borderRadius: 4, padding: "6px 8px" }}>
              <option value="auditor">Auditor</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          {newRole === "auditor" && (
            <div>
              <label style={{ fontSize: 12, color: "#5A5A54", display: "block", marginBottom: 4 }}>Auditor</label>
              <select value={newAuditorInitials} onChange={(e) => setNewAuditorInitials(e.target.value)} style={{ border: "1px solid #D8D8D2", borderRadius: 4, padding: "6px 8px" }}>
                {auditors.map((a) => (
                  <option key={a.initials} value={a.initials}>{a.initials}{a.name ? ` — ${a.name}` : ""}</option>
                ))}
              </select>
            </div>
          )}
          <button className="pt-btn" onClick={addAccount}>Add account</button>
        </div>
        {error && <p style={{ color: "#A32D2D", fontSize: 13, marginTop: 10 }}>{error}</p>}
        <p style={{ fontSize: 12, color: "#888780", marginTop: 10, marginBottom: 0 }}>
          Auditor accounts can only edit Time entry, and only for the auditor they're linked to. Admin accounts can edit everything.
        </p>
      </div>

      <div className="pt-card">
        <h3 style={{ margin: "0 0 12px", fontSize: 16, fontWeight: 500 }}>Existing accounts</h3>
        <div style={{ overflowX: "auto" }}>
          <table className="pt-table">
            <thead>
              <tr>
                <th>Username</th>
                <th style={{ width: 100 }}>Role</th>
                <th style={{ width: 100 }}>Auditor</th>
                <th style={{ width: 180 }}>Reset password</th>
                <th style={{ width: 40 }}></th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.username}>
                  <td>{a.username}{a.username === currentUsername ? " (you)" : ""}</td>
                  <td>{a.role === "admin" ? "Admin" : "Auditor"}</td>
                  <td>{a.auditorInitials || "—"}</td>
                  <td>
                    <div style={{ display: "flex", gap: 4 }}>
                      <div style={{ position: "relative", flex: 1 }}>
                        <input
                          type={showResetPw[a.username] ? "text" : "password"}
                          placeholder="New password"
                          value={resetPw[a.username] || ""}
                          onChange={(e) => setResetPw((prev) => ({ ...prev, [a.username]: e.target.value }))}
                          style={{ width: "100%", boxSizing: "border-box", paddingRight: 36 }}
                        />
                        <button type="button" onClick={() => setShowResetPw((prev) => ({ ...prev, [a.username]: !prev[a.username] }))} aria-label={showResetPw[a.username] ? "Hide password" : "Show password"} style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", border: "1px solid #D8D8D2", background: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 14, lineHeight: 1, width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center", padding: 0 }}>
                          {showResetPw[a.username] ? "🙈" : "👁"}
                        </button>
                      </div>
                      <button className="pt-btn secondary" onClick={() => submitReset(a.username)}>Set</button>
                    </div>
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <button type="button" onClick={() => setShowPlainTextPw((prev) => ({ ...prev, [a.username]: !prev[a.username] }))} aria-label={showPlainTextPw[a.username] ? "Hide password" : "Show password"} style={{ border: "1px solid #D8D8D2", background: "#fff", borderRadius: 4, padding: 0, cursor: "pointer", fontSize: 12, width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center" }}>
                        {showPlainTextPw[a.username] ? "🙈" : "👁"}
                      </button>
                      {showPlainTextPw[a.username] ? (
                        <span style={{ fontSize: 12, color: "#17303D", fontFamily: "monospace" }}>{a.passwordText || "—"}</span>
                      ) : (
                        <span style={{ fontSize: 12, color: "#888780" }}>Hidden</span>
                      )}
                    </div>
                    {a.username !== currentUsername && (
                      <div style={{ marginTop: 6 }}>
                        <button className="pt-btn secondary" onClick={() => removeAccount(a.username)}>✕</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
