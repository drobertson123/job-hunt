// Minimal API client. In dev, /api is proxied to FastAPI (:8000) via Next
// rewrites; in prod the app is served by FastAPI on the same origin.

export type AgentEvent = {
  run_id: string;
  seq: number;
  type: "status" | "token" | "tool_use" | "tool_result" | "result" | "error";
  content: string;
};

export type Note = {
  id: number;
  title: string;
  body: string;
  run_id: string | null;
  created_at: string;
};

export type Artifact = {
  id: number;
  title: string;
  body: string;
  kind: string;
  opportunity_id: string | null;
  provenance: string | null;
  version: number;
  review_status: "draft" | "needs_review" | "approved";
  created_at: string;
};

export type Application = {
  id: string;
  opportunity_id: string;
  company_id: string | null;
  status: string;
  portal_url: string | null;
  external_id: string | null;
  submitted_at: string | null;
  login_hint: string | null;
  notes: string;
  created_at: string;
};

export type Opportunity = {
  id: string;
  title: string;
  organization: string | null;
  stage: string;
};

export type Capability = {
  name: string;
  label: string;
  description: string;
  requires_opportunity: boolean;
  requires_input: boolean;
};

export type GoogleStatus = {
  credentials_configured: boolean;
  connected: boolean;
  email: string | null;
  scopes: string;
};

export type SettingsView = {
  anthropic_key_configured: boolean;
  openai_key_configured: boolean;
  agent_model: string;
  default_agent_model: string;
  deep_analysis_model: string;
  google: GoogleStatus;
};

/** POST JSON to an SSE endpoint and dispatch each agent event. */
async function streamSSE(
  url: string,
  body: unknown,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`${url} failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    // SSE frames are separated by a blank line.
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of frame.split("\n")) {
        if (line.startsWith("data:")) {
          const json = line.slice(5).trim();
          if (json) onEvent(JSON.parse(json) as AgentEvent);
        }
      }
    }
  }
}

/** POST a prompt and stream agent events. */
export async function streamChat(
  prompt: string,
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE("/api/chat", { prompt }, onEvent, signal);
}

/** Invoke a named capability (templated skill run) and stream its events. */
export async function invokeCapability(
  name: string,
  body: { opportunity_id?: string; input?: string },
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE(
    `/api/capabilities/${encodeURIComponent(name)}`,
    body,
    onEvent,
    signal,
  );
}

export async function fetchCapabilities(): Promise<Capability[]> {
  const res = await fetch("/api/capabilities");
  if (!res.ok) throw new Error(`capabilities failed: ${res.status}`);
  return res.json();
}

export async function fetchOpportunities(): Promise<Opportunity[]> {
  const res = await fetch("/api/opportunities");
  if (!res.ok) throw new Error(`opportunities failed: ${res.status}`);
  return res.json();
}

export async function fetchArtifacts(): Promise<Artifact[]> {
  const res = await fetch("/api/artifacts");
  if (!res.ok) throw new Error(`artifacts failed: ${res.status}`);
  return res.json();
}

export async function fetchApplications(): Promise<Application[]> {
  const res = await fetch("/api/applications");
  if (!res.ok) throw new Error(`applications failed: ${res.status}`);
  return res.json();
}

export type ExportResult = {
  artifact_id: number;
  format: string;
  file_path: string;
  download_url: string;
};

/** Render + persist an export; throws with the server's detail on failure. */
export async function exportArtifact(
  id: number,
  format: "docx" | "pdf",
): Promise<ExportResult> {
  const res = await fetch(`/api/artifacts/${id}/export?format=${format}`, {
    method: "POST",
  });
  if (!res.ok) await throwDetail(res, `export failed: ${res.status}`);
  return res.json();
}

export async function fetchNotes(runId?: string): Promise<Note[]> {
  const url = runId ? `/api/notes?run_id=${encodeURIComponent(runId)}` : "/api/notes";
  const res = await fetch(url);
  if (!res.ok) throw new Error(`notes failed: ${res.status}`);
  return res.json();
}

export async function getSettings(): Promise<SettingsView> {
  const res = await fetch("/api/settings");
  if (!res.ok) throw new Error(`settings failed: ${res.status}`);
  return res.json();
}

export async function updateSettings(
  body: Partial<{
    anthropic_api_key: string;
    openai_api_key: string;
    agent_model: string;
    google_client_id: string;
    google_client_secret: string;
  }>,
): Promise<SettingsView> {
  const res = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`settings update failed: ${res.status}`);
  return res.json();
}

export async function syncGmail(): Promise<{ fetched: number; created: number; skipped: number }> {
  const res = await fetch("/api/google/gmail/sync", { method: "POST" });
  if (!res.ok) await throwDetail(res, `gmail sync failed: ${res.status}`);
  return res.json();
}

export async function syncGoogleCalendar(): Promise<{ pushed: number; updated: number }> {
  const res = await fetch("/api/google/calendar/sync", { method: "POST" });
  if (!res.ok) await throwDetail(res, `calendar sync failed: ${res.status}`);
  return res.json();
}

export async function importGoogleContacts(): Promise<{ imported: number; skipped: number }> {
  const res = await fetch("/api/google/contacts/import", { method: "POST" });
  if (!res.ok) await throwDetail(res, `contacts import failed: ${res.status}`);
  return res.json();
}

// ----- corpus & profile (spec: 2026-06-12-corpus-profile-ui-design.md) -----

export type CorpusDocument = {
  id: number;
  title: string;
  source_kind: "upload" | "paste";
  media_type: "pdf" | "docx" | "txt" | "md";
  char_count: number;
};

export type Profile = {
  id: number;
  headline: string | null;
  summary: string | null;
  skills: string[];
  pinned_skills: string[];
  dealbreakers: string[];
  must_haves: string[];
  nice_to_haves: string[];
  experience: Record<string, unknown>[];
  achievements: string[];
  target_titles: string[];
  locations: string[];
  source_doc_count: number;
  synthesized_at: string;
};

/** Throw an Error carrying the server's `detail` when present. */
async function throwDetail(res: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    detail = (await res.json()).detail ?? detail;
  } catch {
    /* keep fallback */
  }
  throw new Error(detail);
}

export async function fetchDocuments(): Promise<CorpusDocument[]> {
  const res = await fetch("/api/corpus/documents");
  if (!res.ok) throw new Error(`documents failed: ${res.status}`);
  return res.json();
}

/** Multipart upload — no Content-Type header; the browser sets the boundary. */
export async function uploadDocument(
  file: File,
  title?: string,
): Promise<CorpusDocument> {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  const res = await fetch("/api/corpus/documents/upload", {
    method: "POST",
    body: form,
  });
  if (!res.ok) await throwDetail(res, `upload failed: ${res.status}`);
  return res.json();
}

export async function pasteDocument(
  title: string,
  text: string,
): Promise<CorpusDocument> {
  const res = await fetch("/api/corpus/documents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, text }),
  });
  if (!res.ok) await throwDetail(res, `paste failed: ${res.status}`);
  return res.json();
}

export async function deleteDocument(id: number): Promise<void> {
  const res = await fetch(`/api/corpus/documents/${id}`, { method: "DELETE" });
  if (!res.ok) await throwDetail(res, `delete failed: ${res.status}`);
}

/** LLM call — can take tens of seconds; callers should show a busy state. */
export async function synthesizeProfile(): Promise<Profile> {
  const res = await fetch("/api/corpus/profile/synthesize", { method: "POST" });
  if (!res.ok) await throwDetail(res, `synthesize failed: ${res.status}`);
  return res.json();
}

export async function getProfile(): Promise<Profile | null> {
  const res = await fetch("/api/corpus/profile");
  if (!res.ok) throw new Error(`profile failed: ${res.status}`);
  return res.json(); // server returns JSON null when no profile exists
}

export async function updatePinnedSkills(skills: string[]): Promise<Profile> {
  const res = await fetch("/api/corpus/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pinned_skills: skills }),
  });
  if (!res.ok) throw new Error(`update skills failed: ${res.status}`);
  return res.json();
}

export async function updatePreferences(body: {
  dealbreakers?: string[];
  must_haves?: string[];
  nice_to_haves?: string[];
}): Promise<Profile> {
  const res = await fetch("/api/corpus/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`update preferences failed: ${res.status}`);
  return res.json();
}

// ----- artifact grounding & approval (spec: 2026-06-12-artifact-review-export-ui) -----

export type GroundingFinding = {
  text: string;
  start: number;
  end: number;
  score: number;
  chunk_id: number | null;
  document_title: string | null;
  supported: boolean;
};

export type GroundingReport = {
  artifact_id: number;
  threshold: number;
  embedding_model: string;
  checked_count: number;
  unsupported_count: number;
  findings: GroundingFinding[];
  annotated_body: string;
  stale: boolean;
  created_at: string;
};

/** Run the embedding-similarity grounding check; also flips status to needs_review. */
export async function runGrounding(id: number): Promise<GroundingReport> {
  const res = await fetch(`/api/artifacts/${id}/grounding`, { method: "POST" });
  if (!res.ok) await throwDetail(res, `grounding failed: ${res.status}`);
  return res.json();
}

/** Cached grounding report, or null when none exists yet (the server's 404). */
export async function getGrounding(id: number): Promise<GroundingReport | null> {
  const res = await fetch(`/api/artifacts/${id}/grounding`);
  if (res.status === 404) return null;
  if (!res.ok) await throwDetail(res, `grounding fetch failed: ${res.status}`);
  return res.json();
}

/** Transition needs_review -> approved; 409 from any other status (surfaced via detail). */
export async function approveArtifact(id: number): Promise<Artifact> {
  const res = await fetch(`/api/artifacts/${id}/approve`, { method: "POST" });
  if (!res.ok) await throwDetail(res, `approve failed: ${res.status}`);
  return res.json();
}

// ----- briefing synthesis (spec: briefing-synthesis) -----

export type BriefingFact = {
  key: string;
  question: string;
  answer: string;
  confidence: number | null;
  source: string | null;
};

export type Briefing = {
  id: number;
  opportunity_id: string | null;
  company_id: string | null;
  summary: string;
  facts: BriefingFact[];
  source_hash: string | null;
  generated_run_id: string | null;
  refreshed_at: string;
  created_at: string;
};

export async function fetchBriefing(oppId: string): Promise<Briefing | null> {
  const res = await fetch(`/api/opportunities/${oppId}/briefing`);
  if (!res.ok) throw new Error(`briefing failed: ${res.status}`);
  return res.json();
}

export async function synthesizeBriefing(oppId: string): Promise<Briefing> {
  const res = await fetch(`/api/opportunities/${oppId}/briefing/synthesize`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`synthesize briefing failed: ${res.status}`);
  return res.json();
}

// ----- opportunity detail (spec: opportunity-detail) -----

export type OpportunityFull = {
  id: string;
  type: string;
  title: string;
  organization: string | null;
  source: string | null;
  url: string | null;
  location: string | null;
  stage: string;
  fit_score: number | null;
  summary: string | null;
  details: Record<string, unknown>;
  archived: boolean;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
};

export type Action = {
  id: number;
  title: string;
  detail: string;
  kind: string;
  status: string;
  due_at: string | null;
  opportunity_id: string | null;
};

export type Decision = {
  id: number;
  kind: string;
  summary: string;
  rationale: string;
  created_at: string;
};

export type OpportunityDetail = {
  opportunity: OpportunityFull;
  actions: Action[];
  artifacts: Artifact[];
  decisions: Decision[];
  applications: Application[];
  communications: Communication[];
  contacts: Contact[];
  briefing: Briefing | null;
  company: Company | null;
  source: JobSource | null;
};

export async function fetchOpportunityDetail(oppId: string): Promise<OpportunityDetail> {
  const res = await fetch(`/api/opportunities/${oppId}`);
  if (!res.ok) throw new Error(`opportunity detail failed: ${res.status}`);
  return res.json();
}

// ----- pipeline board (spec: pipeline-board) -----

export type PipelineBoard = {
  columns: string[];
  by_stage: Record<string, OpportunityFull[]>;
};

export async function fetchPipeline(type?: "job" | "business"): Promise<PipelineBoard> {
  const qs = type ? `?type=${type}` : "";
  const res = await fetch(`/api/pipeline${qs}`);
  if (!res.ok) throw new Error(`pipeline failed: ${res.status}`);
  return res.json();
}

export async function updateStage(
  oppId: string,
  stage: string,
  rationale: string,
): Promise<OpportunityFull> {
  const res = await fetch(`/api/opportunities/${oppId}/stage`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage, rationale }),
  });
  if (!res.ok) throw new Error(`update stage failed: ${res.status}`);
  return res.json();
}

// ----- attention dashboard (spec: attention-dashboard) -----

export type AttentionItem = {
  kind: string; // "overdue_action" | "stale_opportunity" | "untriaged_opportunity"
  severity: string; // "high" | "medium" | ...
  opportunity_id: string | null;
  title: string;
  reason: string;
  action_id?: number;
  due_at?: string | null;
  stage?: string;
  last_activity_at?: string;
};

export type Attention = {
  items: AttentionItem[];
  counts: {
    overdue_actions: number;
    stale_opportunities: number;
    untriaged_opportunities: number;
    overdue_followups: number;
    total: number;
  };
};

export async function fetchAttention(): Promise<Attention> {
  const res = await fetch("/api/attention");
  if (!res.ok) throw new Error(`attention failed: ${res.status}`);
  return res.json();
}

// ----- communications (spec: comms-log) -----

export type Communication = {
  id: number;
  opportunity_id: string | null;
  contact_id: number | null;
  company_id: string | null;
  direction: string;
  channel: string;
  subject: string;
  body: string;
  occurred_at: string;
  thread_key: string | null;
  follow_up_due_at: string | null;
  created_at: string;
};

export async function fetchCommunications(oppId?: string): Promise<Communication[]> {
  const qs = oppId ? `?opportunity_id=${oppId}` : "";
  const res = await fetch(`/api/communications${qs}`);
  if (!res.ok) throw new Error(`communications failed: ${res.status}`);
  return res.json();
}

// ----- company normalization (spec: company-normalization) -----

export type Company = {
  id: string;
  name: string;
  domain: string | null;
  industry: string | null;
  size: string;
  hq_location: string | null;
  careers_url: string | null;
  linkedin_url: string | null;
  ats_vendor: string | null;
  summary: string | null;
  notes: string;
  created_at: string;
};

export async function fetchCompanies(): Promise<Company[]> {
  const res = await fetch("/api/companies");
  if (!res.ok) throw new Error(`companies failed: ${res.status}`);
  return res.json();
}

export async function backfillCompanies(): Promise<{
  opportunities_linked: number;
  contacts_linked: number;
  companies: number;
}> {
  const res = await fetch("/api/companies/backfill", { method: "POST" });
  if (!res.ok) throw new Error(`backfill failed: ${res.status}`);
  return res.json();
}

export async function fetchActions(status?: string, opportunityId?: string): Promise<Action[]> {
  const p = new URLSearchParams();
  if (status) p.set("status", status);
  if (opportunityId) p.set("opportunity_id", opportunityId);
  const qs = p.toString();
  const res = await fetch(`/api/actions${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`actions failed: ${res.status}`);
  return res.json();
}

export async function createAction(body: {
  title: string;
  kind?: string;
  detail?: string;
  due_at?: string | null;
  opportunity_id?: string | null;
}): Promise<Action> {
  const res = await fetch("/api/actions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`create action failed: ${res.status}`);
  return res.json();
}

export async function completeAction(id: number): Promise<Action> {
  const res = await fetch(`/api/actions/${id}/complete`, { method: "POST" });
  if (!res.ok) throw new Error(`complete action failed: ${res.status}`);
  return res.json();
}

export async function snoozeAction(id: number): Promise<Action> {
  const res = await fetch(`/api/actions/${id}/snooze`, { method: "POST" });
  if (!res.ok) throw new Error(`snooze action failed: ${res.status}`);
  return res.json();
}

export async function reopenAction(id: number): Promise<Action> {
  const res = await fetch(`/api/actions/${id}/reopen`, { method: "POST" });
  if (!res.ok) throw new Error(`reopen action failed: ${res.status}`);
  return res.json();
}

// ----- contacts (spec: contacts) -----

export type Contact = {
  id: number;
  opportunity_id: string | null;
  name: string;
  role: string | null;
  organization: string | null;
  company_id: string | null;
  link: string | null;
  email?: string | null;
  notes: string;
  created_at: string;
};

export async function fetchContacts(oppId?: string): Promise<Contact[]> {
  const qs = oppId ? `?opportunity_id=${oppId}` : "";
  const res = await fetch(`/api/contacts${qs}`);
  if (!res.ok) throw new Error(`contacts failed: ${res.status}`);
  return res.json();
}

export async function createContact(body: {
  name: string;
  opportunity_id?: string | null;
  role?: string | null;
  organization?: string | null;
  link?: string | null;
  email?: string | null;
  notes?: string;
}): Promise<Contact> {
  const res = await fetch("/api/contacts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`create contact failed: ${res.status}`);
  return res.json();
}

// ----- interviews (spec: interview-calendar) -----

export type Interview = {
  id: number;
  opportunity_id: string | null;
  title: string;
  kind: string;
  starts_at: string;
  ends_at: string | null;
  location: string;
  notes: string;
  created_at: string;
};

export async function fetchInterviews(upcoming = true): Promise<Interview[]> {
  const res = await fetch(`/api/interviews${upcoming ? "?upcoming=true" : ""}`);
  if (!res.ok) throw new Error(`interviews failed: ${res.status}`);
  return res.json();
}

export async function createInterview(body: {
  title: string;
  starts_at: string;
  opportunity_id?: string | null;
  kind?: string;
  location?: string;
  notes?: string;
}): Promise<Interview> {
  const res = await fetch("/api/interviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`create interview failed: ${res.status}`);
  return res.json();
}

export async function deleteInterview(id: number): Promise<void> {
  const res = await fetch(`/api/interviews/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`delete interview failed: ${res.status}`);
}

// ----- weekly review (spec: 2026-06-21-weekly-process) -----

export type WeeklyOpp = {
  id: string;
  title: string;
  organization: string | null;
  stage: string;
  type: string;
};

export type WeeklyInterview = {
  id: number;
  title: string;
  starts_at: string;
  opportunity_id: string | null;
};

export type WeeklyReview = {
  to_identify: WeeklyOpp[];
  to_apply: WeeklyOpp[];
  to_follow_up: WeeklyOpp[];
  interviews_this_week: WeeklyInterview[];
  counts: Record<string, number>;
};

export async function fetchWeeklyReview(): Promise<WeeklyReview> {
  const res = await fetch("/api/weekly-review");
  if (!res.ok) throw new Error(`weekly review failed: ${res.status}`);
  return res.json();
}

export async function createWeeklyActions(): Promise<{ created: number }> {
  const res = await fetch("/api/weekly-review/actions", { method: "POST" });
  if (!res.ok) throw new Error(`create weekly actions failed: ${res.status}`);
  return res.json();
}

// ----- content library (spec: 2026-06-21-content-library) -----

export type ContentBlock = {
  id: number;
  kind: string;
  audience: string;
  text: string;
  tags: string[];
  created_at: string;
};

export async function fetchContentBlocks(): Promise<ContentBlock[]> {
  const res = await fetch("/api/content-blocks");
  if (!res.ok) throw new Error(`content blocks failed: ${res.status}`);
  return res.json();
}

export async function deleteContentBlock(id: number): Promise<void> {
  const res = await fetch(`/api/content-blocks/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`delete content block failed: ${res.status}`);
}

// ----- agent runs (spec: board-rail) -----

export type RunSummary = {
  id: string;
  prompt: string;
  model: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export async function fetchRuns(limit = 30): Promise<RunSummary[]> {
  const res = await fetch(`/api/runs?limit=${limit}`);
  if (!res.ok) throw new Error(`runs failed: ${res.status}`);
  return res.json();
}

// ----- pipeline metrics (spec: 2026-06-21-metrics) -----

export type Metrics = {
  kpis: { total_applications: number; this_month: number; response_rate: number; interview_rate: number; active: number };
  funnel: { label: string; count: number; rate: number | null }[];
  volume: { week: string; count: number }[];
  sources: { source: string; count: number }[];
};

export async function fetchMetrics(): Promise<Metrics> {
  const res = await fetch("/api/metrics");
  if (!res.ok) throw new Error(`metrics failed: ${res.status}`);
  return res.json();
}

// ----- job sources (spec: jobsource-attribution) -----

export type JobSource = {
  id: string;
  name: string;
  kind: string;
  url: string | null;
  saved_query: string | null;
  auto_search: boolean;
  last_checked_at: string | null;
  referrer_contact_id: number | null;
  notes: string;
  created_at: string;
};

export async function fetchJobSources(): Promise<JobSource[]> {
  const res = await fetch("/api/job-sources");
  if (!res.ok) throw new Error(`job sources failed: ${res.status}`);
  return res.json();
}

export async function createJobSource(body: {
  name: string;
  kind?: string;
  saved_query?: string | null;
  auto_search?: boolean;
}): Promise<JobSource> {
  const res = await fetch("/api/job-sources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`create job source failed: ${res.status}`);
  return res.json();
}

export async function updateJobSource(
  id: string,
  body: { saved_query?: string | null; auto_search?: boolean; name?: string }
): Promise<JobSource> {
  const res = await fetch(`/api/job-sources/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`update job source failed: ${res.status}`);
  return res.json();
}

export async function runJobSourceSearch(id: string): Promise<{ status: string }> {
  const res = await fetch(`/api/job-sources/${id}/search`, { method: "POST" });
  if (!res.ok) throw new Error(`run search failed: ${res.status}`);
  return res.json();
}
