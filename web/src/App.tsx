import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  Activity, ArrowRight, ArrowUpRight, BriefcaseBusiness, Check, CheckCircle2,
  ChevronRight, Clock3, Database, Download, FileCheck2, FileText, Globe2,
  LayoutDashboard, ListFilter, LockKeyhole, MapPin, Menu, Plus, RefreshCw,
  Search, Settings2, ShieldCheck, Sparkles, Target, Trash2, UploadCloud,
  WandSparkles, X, ChartNoAxesColumn, AlertCircle, type LucideIcon
} from "lucide-react";
import {
  addManualJob, approveFact, createFact, deleteCV, deleteFact, deletePrivateSavedJob, getApplications,
  getCV, getDashboard, getHealth, getJobs, getPrivateSavedJobs, getProfileFacts, getSession,
  startApplicationWorkspace, uploadCV, saveCVEditor, restoreCVEditor, getJobAIConsents, getJobAIConsentEvents,
  grantJobAIConsent, revokeJobAIConsent,
  getSearchPreferences, updateSearchPreferences, getSearchResults, getLocalAIStatus,
  prepareMyMatchingDrafts, type AutoDraftResult
} from "./api";
import {
  filterBySector, formatState, queueLabel, relativeFreshness, safeExternalJobUrl, scoreBand,
  sectorLabel, type DisplayMode, type SectorFilter
} from "./lib";
import ApplicationStudio from "./ApplicationStudio";
import MasterCVEditor from "./MasterCVEditor";
import ApplicationJourney from "./ApplicationJourney";
import { describeAutoApplyBatchIssue } from "./autoapply_batch_errors";
import StartChoices from "./StartChoices";
import ReleaseStatus from "./ReleaseStatus";
import SearchSetup from "./SearchSetup";
import SearchResultsPanel from "./SearchResultsPanel";
import TrainingProgramsPanel from "./TrainingProgramsPanel";
import BrandMark from "./BrandMark";
import AIConsentSettings from "./AIConsentSettings";
import type {
  ApplicationRecord, CandidateFact, CVDocument, Dashboard, HealthResponse,
  ManualJobPayload, PrivateSavedJob, RankingCard, SavedJob, SessionInfo,
  SearchPreferences, SearchPreferencesUpdate, SearchResults, LocalAIStatus,
  JobAIProcessingConsent, JobAIProcessingConsentEvent,
  ApplicationFlowMode, AutoApplyBatchOutcome
} from "./types";

type Page = "dashboard" | "apply" | "jobs" | "training" | "applications" | "profile" | "tools" | "insights" | "sources" | "settings";
type MatchView = "top" | "possible";

const NAV: Array<{ id: Page; label: string; icon: LucideIcon }> = [
  { id: "dashboard", label: "Start here", icon: LayoutDashboard },
  { id: "apply", label: "Apply for jobs", icon: FileCheck2 },
  { id: "jobs", label: "Find jobs", icon: Search },
  { id: "applications", label: "My applications", icon: FileText },
  { id: "profile", label: "My CV & documents", icon: FileCheck2 },
  { id: "training", label: "Training & traineeships", icon: BriefcaseBusiness },
  { id: "tools", label: "CV & AI tools", icon: Sparkles },
  { id: "insights", label: "Career insights", icon: ChartNoAxesColumn },
  { id: "sources", label: "Job sources", icon: Database },
  { id: "settings", label: "Advanced settings", icon: Settings2 }
];

const FACT_TYPES: Array<{ value: string; label: string }> = [
  { value: "identity", label: "Full name" }, { value: "contact", label: "Contact" },
  { value: "email", label: "Email address" }, { value: "phone", label: "Phone number" },
  { value: "linkedin", label: "LinkedIn profile URL" }, { value: "github", label: "GitHub profile URL" },
  { value: "skill", label: "Skill" }, { value: "experience", label: "Experience" },
  { value: "education", label: "Education" }, { value: "language", label: "Language" },
  { value: "certification", label: "Certification" }, { value: "project", label: "Project" },
  { value: "location", label: "Location" }, { value: "work_authorization", label: "Work authorization" },
  { value: "domain", label: "Industry" }, { value: "preference", label: "Preference" }
];

function cx(...parts: Array<string | undefined | false>): string {
  return parts.filter(Boolean).join(" ");
}

/** Only actual case creations are counted; a draft is never an employer send. */
/** Only use a newly created private kit supplied by the same-account scan.
 * A legacy or inconsistent response never guesses an older draft from the
 * workspace listing. The original Application Studio rechecks ownership.
 */
function firstNewAutoDraftWorkspace(result: AutoDraftResult): string {
  const ids = result.created_workspace_ids;
  if (result.created < 1 || !Array.isArray(ids) ||
      ids.length !== result.created ||
      new Set(ids).size !== ids.length ||
      !ids.every((id) => typeof id === "string" && /^kit-[0-9a-f]{30}$/.test(id))) {
    return "";
  }
  return ids[0];
}

function agentTrackingNotice(result: AutoDraftResult): string {
  const started = result.agents_started || 0;
  const already = result.agents_already_present || 0;
  const unavailable = result.agents_unavailable || 0;
  if (!started && !already && !unavailable) return "";
  return " " + started + " new private application agent(s), " +
    already + " existing agent(s), " + unavailable +
    " agent(s) unavailable. In-app reminders need an independently enabled worker; no employer was contacted.";
}

function Empty(props: { title: string; description: string; action?: string; onAction?: () => void; icon?: LucideIcon }) {
  const Icon = props.icon ?? BriefcaseBusiness;
  return (
    <div className="empty-state">
      <span className="empty-art"><Icon size={27} strokeWidth={1.6} /></span>
      <h3>{props.title}</h3>
      <p>{props.description}</p>
      {props.action && props.onAction ? (
        <button className="secondary-btn" type="button" onClick={props.onAction}>{props.action} <ArrowRight size={15} /></button>
      ) : null}
    </div>
  );
}

function Stat(props: { label: string; value: number; note: string; icon: LucideIcon; tone: string; onClick: () => void }) {
  const Icon = props.icon;
  return (
    <button className="stat-card" type="button" onClick={props.onClick}>
      <span className={cx("stat-icon", props.tone)}><Icon size={20} /></span>
      <span className="stat-copy"><span className="stat-label">{props.label}</span><strong>{props.value}</strong><small>{props.note}</small></span>
      <ChevronRight className="stat-arrow" size={17} />
    </button>
  );
}

function Tool(props: { title: string; description: string; icon: LucideIcon; ready: boolean; onClick: () => void }) {
  const Icon = props.icon;
  return <button className="tool-tile" type="button" onClick={props.onClick}>
    <span className="tool-icon"><Icon size={20} /></span>
    <span className="tool-copy"><strong>{props.title}</strong><small>{props.description}</small></span>
    <span className={cx("tool-indicator", props.ready ? "ready" : "pending")}>{props.ready ? "Open" : "Setup"}</span>
    <ChevronRight size={15} className="muted-icon" />
  </button>;
}

/** Require a server-issued stable identity, never an email-only fallback. */
function sessionIdentity(who: SessionInfo): string {
  const subject = (who.user_id || who.profile_id || who.subject_fingerprint || "").trim();
  if (!who.authenticated || !subject) {
    throw new Error("Authenticated account identity is unavailable. Sign in again.");
  }
  return JSON.stringify([subject, who.auth_source || ""]);
}

/** User-facing API mutations must never publish another account's response. */
class PrivateActionIdentityChanged extends Error {}

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [flowMode, setFlowMode] = useState<ApplicationFlowMode | null>(null);
  const [flowSelectedJob, setFlowSelectedJob] = useState("");
  const [flowQueueBusy, setFlowQueueBusy] = useState(false);
  const [startSearchBusy, setStartSearchBusy] = useState(false);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [cv, setCV] = useState<CVDocument>({ present: false });
  const [facts, setFacts] = useState<CandidateFact[]>([]);
  const [jobs, setJobs] = useState<SavedJob[]>([]);
  const [privateSavedJobs, setPrivateSavedJobs] = useState<PrivateSavedJob[]>([]);
  const [aiConsents, setAIConsents] = useState<JobAIProcessingConsent[]>([]);
  const [aiConsentEvents, setAIConsentEvents] = useState<JobAIProcessingConsentEvent[]>([]);
  const [aiConsentStatus, setAIConsentStatus] = useState<"ready" | "unavailable">("unavailable");
  const [aiConsentBusy, setAIConsentBusy] = useState(false);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [preferences, setPreferences] = useState<SearchPreferences | null>(null);
  const [discovery, setDiscovery] = useState<SearchResults | null>(null);
  const [localAI, setLocalAI] = useState<LocalAIStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyCV, setBusyCV] = useState(false);
  const [busyFact, setBusyFact] = useState("");
  const [preparing, setPreparing] = useState("");
  const [autoDraftBusy, setAutoDraftBusy] = useState(false);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState<SectorFilter>("all");
  const [view, setView] = useState<MatchView>("top");
  const [mode, setMode] = useState<DisplayMode>("heatmap");
  const [expandedJob, setExpandedJob] = useState("");
  const [cvPreview, setCVPreview] = useState(false);
  const [jobDialog, setJobDialog] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [newFactType, setNewFactType] = useState("skill");
  const [newFactValue, setNewFactValue] = useState("");
  const [confirmFact, setConfirmFact] = useState(false);
  const [manualBusy, setManualBusy] = useState(false);
  const [removingPrivateJob, setRemovingPrivateJob] = useState("");
  const [jobForm, setJobForm] = useState<ManualJobPayload>({
    company: "", role_title: "", location: "", description: "", application_url: ""
  });
  const uploadRef = useRef<HTMLInputElement>(null);
  // A run token prevents an old account's finally block unlocking a new batch.
  const flowQueueInFlight = useRef<symbol | null>(null);
  const activeCVSelection = useRef("");
  activeCVSelection.current = JSON.stringify([cv.present, cv.sha256 || ""]);

  // Old in-flight requests must not repopulate another account's workspace.
  const loadGeneration = useRef(0);
  const lastSessionIdentity = useRef<string | null>(null);
  const savingSearchPreferences = useRef(false);
  const savingAIConsent = useRef(false);
  // A rerender cannot start two private AutoApply scans for the same account.
  // Different account identities must never inherit the old in-flight lock.
  const autoDraftInFlight = useRef<string | null>(null);
  const clearPrivateWorkspace = useCallback(() => {
    setDashboard(null); setPreferences(null); setDiscovery(null); setSession(null);
    setApplications([]); setCV({ present: false }); setFacts([]); setJobs([]);
    setPrivateSavedJobs([]);
    setAIConsents([]); setAIConsentEvents([]);
    setAIConsentStatus("unavailable"); setAIConsentBusy(false);
    setHealth(null); setLocalAI(null); setSelectedWorkspaceId("");
    // A different account must not inherit an unsaved draft, editor, form,
    // selected job or cached navigation state belonging to its predecessor.
    setPage("dashboard"); setSearch(""); setExpandedJob("");
    setFlowMode(null); setFlowSelectedJob(""); setFlowQueueBusy(false);
    setStartSearchBusy(false); flowQueueInFlight.current = null;
    setCVPreview(false); setJobDialog(false); setNewFactValue("");
    setConfirmFact(false); setNotice("");
    setBusyCV(false); setBusyFact(""); setPreparing(""); setManualBusy(false);
    setAutoDraftBusy(false);
    setRemovingPrivateJob("");
    if (uploadRef.current) uploadRef.current.value = "";
    setJobForm({
      company: "", role_title: "", location: "",
      description: "", application_url: ""
    });
  }, []);

  /** Check account identity on both sides of every private mutation.
   *
   * A mutation may have reached the server before an account change; this
   * protects the rendered workspace, it does NOT undo server-side effects.
   * Backend authorization remains mandatory for each operation.
   */
  const runPrivateMutation = useCallback(async <T,>(
    action: (expectedUserId: string) => Promise<T>
  ): Promise<T> => {
    // Capture the initiating account synchronously, *before* the preflight
    // await. The server must reject if a later browser cookie belongs to B.
    const expectedIdentity = lastSessionIdentity.current;
    const expectedUserId = session?.user_id?.trim() || "";
    const denyStaleAction = (): never => {
      ++loadGeneration.current; // invalidate private GET responses in flight
      lastSessionIdentity.current = null;
      clearPrivateWorkspace();
      setLoading(false);
      setRefreshing(false);
      setError(
        "The signed-in account changed or could not be verified during a private action. Reload this workspace."
      );
      throw new PrivateActionIdentityChanged();
    };
    const verifyIdentity = async () => {
      let currentIdentity: string | null = null;
      try {
        currentIdentity = sessionIdentity(await getSession());
      } catch {
        // A missing/expired session fails closed, even when email is unchanged.
      }
      if (!expectedIdentity || currentIdentity !== expectedIdentity ||
          lastSessionIdentity.current !== expectedIdentity) {
        denyStaleAction();
      }
    };

    // The identity loaded in this React view must be the verified account,
    // not an older session object left behind during a concurrent refresh.
    if (!session || !expectedUserId || sessionIdentity(session) !== expectedIdentity) {
      denyStaleAction();
    }
    await verifyIdentity(); // never dispatch an action for an unverified account
    try {
      const result = await action(expectedUserId);
      await verifyIdentity(); // discard stale successful mutation responses
      return result;
    } catch (exc) {
      if (exc instanceof PrivateActionIdentityChanged) throw exc;
      // A request failure can coincide with logout. Do not display errors
      // from account A inside B's workspace.
      await verifyIdentity();
      throw exc;
    }
  }, [clearPrivateWorkspace, session]);

  const load = useCallback(async (quiet = false) => {
    if (savingSearchPreferences.current || savingAIConsent.current) return;
    const generation = ++loadGeneration.current;
    if (quiet) setRefreshing(true); else setLoading(true);

    try {
      // Establish a server-issued account identity BEFORE requesting private
      // preferences, CVs, drafts or other tenant-scoped responses. Starting
      // them alongside the session request could mix two browser identities.
      const who = await getSession();
      if (generation !== loadGeneration.current) return;
      const identity = sessionIdentity(who);
      if (lastSessionIdentity.current !== null &&
          identity !== lastSessionIdentity.current) {
        clearPrivateWorkspace();
        setLoading(true);
        lastSessionIdentity.current = null;
      }

      // Optional requests still run alongside the essential job reads; they
      // must never block first-use navigation when Ollama or a CV is slow.
      // A slow Ollama availability endpoint cannot hold profile documents
      // and private saved jobs hostage. Attach a rejection handler now.
      const localAIRequest = Promise.allSettled([getLocalAIStatus()]);
      const secondaryRequest = Promise.allSettled([
        getApplications(), getHealth(), getCV(), getProfileFacts(),
        getJobs(), getPrivateSavedJobs(), getJobAIConsents(), getJobAIConsentEvents()
      ]);
      const [board, prefs, results] = await Promise.all([
        getDashboard(), getSearchPreferences(), getSearchResults()
      ]);
      if (generation !== loadGeneration.current) return;

      // Account switch during GETs: reject all mixed snapshots, rather than
      // showing A's job/CV data under B's currently signed-in browser.
      const verifiedWho = await getSession();
      if (generation !== loadGeneration.current) return;
      if (sessionIdentity(verifiedWho) !== identity) {
        throw new Error("Your signed-in account changed during refresh. Reload this workspace.");
      }
      lastSessionIdentity.current = identity;
      setDashboard(board); setPreferences(prefs); setDiscovery(results);
      setSession(verifiedWho);
      setLoading(false); setRefreshing(false); setError("");

      // Only global local-model readiness is returned by this endpoint:
      // never personal CV or draft content. This response is optional and
      // must not update a superseded account/load-generation view.
      void localAIRequest.then(([model]) => {
        if (generation !== loadGeneration.current ||
            lastSessionIdentity.current !== identity) return;
        setLocalAI(model.status === "fulfilled" ? model.value : null);
        if (model.status === "rejected") {
          setError((current) => current ||
            "Some optional profile or AI tools are temporarily unavailable. You can still browse and change job criteria.");
        }
      });

      const secondary = await secondaryRequest;
      if (generation !== loadGeneration.current) return;
      const finalWho = await getSession();
      if (generation !== loadGeneration.current) return;
      if (sessionIdentity(finalWho) !== identity) {
        throw new Error("Your signed-in account changed during profile loading. Reload this workspace.");
      }

      const [apps, ready, savedCV, profile, savedJobs, bookmarks, grants, grantEvents] = secondary;
      setApplications(apps.status === "fulfilled" ? apps.value.applications : []);
      setHealth(ready.status === "fulfilled" ? ready.value : null);
      setCV(savedCV.status === "fulfilled" ? savedCV.value : { present: false });
      setFacts(profile.status === "fulfilled" ? profile.value.facts : []);
      setJobs(savedJobs.status === "fulfilled" ? savedJobs.value.jobs : []);
      setPrivateSavedJobs(bookmarks.status === "fulfilled" ? bookmarks.value.jobs : []);
      setAIConsents(grants.status === "fulfilled" ? grants.value.consents : []);
      setAIConsentEvents(grantEvents.status === "fulfilled" ? grantEvents.value.events : []);
      setAIConsentStatus(grants.status === "fulfilled" ? "ready" : "unavailable");
      if (secondary.slice(0, 6).some((item) => item.status === "rejected")) {
        setError((current) => current ||
          "Some optional profile or AI tools are temporarily unavailable. You can still browse and change job criteria.");
      }
    } catch (exc) {
      if (generation === loadGeneration.current) {
        lastSessionIdentity.current = null;
        clearPrivateWorkspace();
        setError(exc instanceof Error ? exc.message : "Unable to reach SmartPloy.");
      }
    } finally {
      if (generation === loadGeneration.current) {
        setLoading(false); setRefreshing(false);
      }
    }
  }, [clearPrivateWorkspace]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => { void load(true); }, 60000);
    return () => window.clearInterval(timer);
  }, [load]);

  const navigate = (target: Page) => { setPage(target); setMobileNav(false); setNotice(""); };

  function startApplyFlow(chosen: ApplicationFlowMode, jobKey = "") {
    // A job-card shortcut never skips the CV-first gate. Creating a draft
    // without a CV is impossible and must not visually select a method.
    if (!cv.present) {
      setFlowMode(null); setFlowSelectedJob("");
      navigate("apply");
      setNotice("Step 1: upload or create your CV. Manual, Assisted and Automatic unlock after your CV is connected.");
      return;
    }
    setFlowMode(chosen);
    setFlowSelectedJob(jobKey);
    navigate("apply");
  }

  async function startGeneralBrowse() {
    if (!preferences) return;
    if (preferences.completed && preferences.mode === "general") {
      navigate("jobs"); return;
    }
    if (startSearchBusy) return;
    setStartSearchBusy(true);
    try {
      await saveSearchPreferences({
        mode: "general", roles: preferences.roles, locations: preferences.locations,
        languages: preferences.languages, work_modes: preferences.work_modes,
        keywords: preferences.keywords, skills: preferences.skills,
        seniority: preferences.seniority, auto_draft_enabled: false,
        expected_revision: preferences.revision,
      });
      navigate("jobs");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not open job search.");
    } finally { setStartSearchBusy(false); }
  }
  async function saveSearchPreferences(next: SearchPreferencesUpdate) {
    if (savingSearchPreferences.current) {
      throw new Error("A search preference save is already in progress.");
    }
    savingSearchPreferences.current = true;
    // A concurrent refresh cannot publish an old preference snapshot while
    // the PUT and its paired discovery GET are in progress.
    ++loadGeneration.current;
    setRefreshing(false);

    const expectedIdentity = lastSessionIdentity.current;
    const expectedUserId = session?.user_id?.trim() || "";
    let accountUnverified = false;
    const requireSameAccount = async () => {
      let observedIdentity: string | null = null;
      try {
        observedIdentity = sessionIdentity(await getSession());
      } catch {
        // Treat failed/unauthenticated session verification as a privacy
        // boundary failure, not permission to publish stale private results.
      }
      if (!expectedIdentity || !session || !expectedUserId ||
          sessionIdentity(session) !== expectedIdentity ||
          observedIdentity !== expectedIdentity ||
          lastSessionIdentity.current !== expectedIdentity) {
        accountUnverified = true;
        throw new Error(
          "The signed-in account changed or could not be verified while saving search preferences. Reload this workspace."
        );
      }
    };

    try {
      // Check before the mutation, after its response, and after fetching the
      // matching search results. Never render account A's preference response
      // under B merely because their visible email addresses are the same.
      await requireSameAccount();
      const result = await updateSearchPreferences(next, expectedUserId);
      await requireSameAccount();
      const fresh = await getSearchResults();
      await requireSameAccount();

      // Reuse the ORIGINAL signed-in private POST after *every* saved
      // opted-in personalized search, including changed target roles.
      // Previously this ran only on OFF->ON, delaying newly requested
      // applications until the background worker's next cadence.
      // This is private draft preparation, NEVER employer submission.
      const shouldScan = result.auto_draft_enabled === true &&
        result.mode === "personalized" && result.roles.length > 0;
      let firstScan: Awaited<ReturnType<typeof prepareMyMatchingDrafts>> | null = null;
      let scanUnavailable = false;
      if (shouldScan) {
        try {
          firstScan = await prepareMyMatchingDrafts(expectedUserId);
        } catch {
          // Do not roll back an already-saved preference or leak private
          // profile/database exceptions. The immediate button remains usable.
          scanUnavailable = true;
        }
        // In particular, reject an old-account success after a cookie switch.
        await requireSameAccount();
      }

      setPreferences(result);
      setDiscovery(fresh);
      setView("top");
      if (shouldScan && firstScan?.status === "needs_approved_profile") {
        setPage("profile");
        setNotice("Automatic IT search is enabled. Approve your career facts to prepare your first applications; nothing has been sent.");
      } else if (shouldScan && firstScan?.status === "needs_source_refresh") {
        setPage("jobs");
        setNotice("Automatic IT search is enabled, but some matching employer listings have not been checked recently. No drafts were created from stale postings. Check the job-feed status and retry after a source refresh.");
      } else if (shouldScan && firstScan?.status === "needs_trusted_source") {
        setPage("jobs");
        setNotice("Automatic IT search is enabled, but matching jobs came from manual or unverified sources. Set up a reviewed public employer feed for automatic drafts. You can still review those listings yourself.");
      } else if (shouldScan && firstScan && firstScan.created > 0 &&
                 ["prepared", "disabled_after_revocation"].includes(firstScan.status)) {
        const firstNewKit = firstNewAutoDraftWorkspace(firstScan);
        setSelectedWorkspaceId(firstNewKit);
        setPage("applications");
        setNotice(firstScan.created + " matched IT application draft(s) prepared privately. " +
          (firstNewKit ? "Opened the first new draft for review. " :
            "Find your new drafts in My applications. ") +
          (firstScan.stopped_on_opt_out ?
            "Automatic preparation stopped after you withdrew permission. " : "") +
          "Review each CV and letter before any employer submission." +
          agentTrackingNotice(firstScan));
      } else if (shouldScan && firstScan?.status === "prepared") {
        setPage(firstScan.agents_started ? "applications" : "jobs");
        setNotice("Automatic IT search is enabled. No new safe matches were ready; you can review current jobs and prepare drafts again." +
          agentTrackingNotice(firstScan));
      } else if (shouldScan && (scanUnavailable || firstScan?.status !== "prepared")) {
        setPage("jobs");
        setNotice("Your automatic IT search setting was saved, but the first draft scan could not finish. Use 'Find and prepare matching drafts now' to retry.");
      } else {
        setPage("dashboard");
        setNotice(result.mode === "general"
          ? "General search enabled: all current jobs, no personalization."
          : "Your search targets were saved. Recommendations now reflect your criteria.");
      }
    } catch (exc) {
      // A rejected PUT can coincide with logout/account switching. Check
      // again before keeping the previous account's editable workspace.
      if (!accountUnverified) await requireSameAccount();
      throw exc;
    } finally {
      savingSearchPreferences.current = false;
      if (accountUnverified) {
        ++loadGeneration.current;
        lastSessionIdentity.current = null;
        clearPrivateWorkspace();
        setError(
          "The signed-in account changed or could not be verified while saving search preferences. Reload this workspace."
        );
      }
    }
  }

  async function changeAIConsent(action: (userId: string) => Promise<unknown>, message: string) {
    if (savingAIConsent.current || aiConsentStatus !== "ready") return;
    const originatingIdentity = lastSessionIdentity.current;
    savingAIConsent.current = true;
    ++loadGeneration.current; // Invalidate older private GET responses.
    setRefreshing(false); // A cancelled refresh must not leave its spinner stuck.
    setAIConsentBusy(true);
    try {
      const data = await runPrivateMutation(async (userId) => {
        await action(userId);
        const [consents, events] = await Promise.all([
          getJobAIConsents(), getJobAIConsentEvents()
        ]);
        return { consents, events };
      });
      setAIConsents(data.consents.consents);
      setAIConsentEvents(data.events.events);
      setAIConsentStatus("ready");
      setNotice(message);
    } catch (exc) {
      if (!(exc instanceof PrivateActionIdentityChanged)) {
        setNotice(exc instanceof Error ? exc.message : "Could not change your AI permission.");
      }
    } finally {
      savingAIConsent.current = false;
      if (originatingIdentity === lastSessionIdentity.current) setAIConsentBusy(false);
    }
  }

  const grantConsent = (key: string) =>
    changeAIConsent(
      (userId) => grantJobAIConsent(key, userId),
      "Permission saved for this job and approved evidence only. No AI request was started."
    );
  const revokeConsent = (id: string) =>
    changeAIConsent(
      (userId) => revokeJobAIConsent(id, userId),
      "Permission withdrawn. Future unattended AI processing is not authorized."
    );

  async function changeSearchMode(target: "personalized" | "general") {
    if (!preferences || preferences.mode === target) return;
    if (target === "personalized" && !preferences.roles.length && !preferences.keywords.length) {
      navigate("settings");
      setNotice("Add a target job title or keyword before enabling personalized search.");
      return;
    }
    try {
      await saveSearchPreferences({
        mode: target, roles: preferences.roles, locations: preferences.locations,
        languages: preferences.languages, work_modes: preferences.work_modes,
        keywords: preferences.keywords, skills: preferences.skills,
        seniority: preferences.seniority,
        expected_revision: preferences.revision
      });
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not switch job search mode.");
    }
  }

  const onUploadClick = () => uploadRef.current?.click();

  async function onCVUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const actionIdentity = lastSessionIdentity.current;
    setBusyCV(true); setNotice("");
    try {
      const uploaded = await runPrivateMutation((userId) => uploadCV(file, userId));
      setCV(uploaded); setCVPreview(false);
      // A replacement CV invalidates any old method/job selection, even when
      // uploaded from Apply. Step 2 must be a fresh applicant choice.
      setFlowMode(null); setFlowSelectedJob("");
      navigate("apply");
      setNotice("CV connected. Step 2: choose Manual, Assisted or Automatic. Your CV has not been sent to any employer.");
      await load(true);
      // An uploaded CV is not automatically approved as career evidence.
      // CV upload never starts background employer work. It is now a clear
      // discovery step; approved facts and AutoDraft opt-in stay independent.
    } catch (exc) {
      if (exc instanceof PrivateActionIdentityChanged) return;
      navigate("profile");
      setNotice(exc instanceof Error ? exc.message : "CV upload failed.");
    } finally {
      if (lastSessionIdentity.current === actionIdentity) setBusyCV(false);
    }
  }

  async function onDeleteCV() {
    if (!window.confirm("Remove your uploaded CV? Approved profile facts will remain until you remove them separately.")) return;
    const actionIdentity = lastSessionIdentity.current;
    setBusyCV(true);
    try {
      await runPrivateMutation((userId) => deleteCV(userId));
      setCV({ present: false }); setCVPreview(false);
      setFlowMode(null); setFlowSelectedJob("");
      setNotice("Your CV was removed. Connect a new CV before selecting an application method.");
    } catch (exc) {
      if (!(exc instanceof PrivateActionIdentityChanged)) {
        setNotice(exc instanceof Error ? exc.message : "Unable to remove CV.");
      }
    } finally {
      if (lastSessionIdentity.current === actionIdentity) setBusyCV(false);
    }
  }

  async function onAddFact(event: FormEvent) {
    event.preventDefault();
    const factValue = newFactValue.trim();
    if (!factValue) return;
    const actionIdentity = lastSessionIdentity.current;
    const factType = newFactType;
    const approvedByUser = confirmFact;
    setBusyFact("new");
    try {
      await runPrivateMutation((userId) => createFact(factType, factValue, approvedByUser, userId));
      setNewFactValue(""); setConfirmFact(false);
      setNotice(approvedByUser ? "Approved profile evidence saved." : "Fact saved for review.");
      await load(true);
      // The first opt-in often correctly returns needs_approved_profile.
      // Don't make the user press another button after approving facts:
      // reuse the existing account-checked private AutoApply scan.
      if (approvedByUser) await onPrepareMyAutoDrafts();
    } catch (exc) {
      if (!(exc instanceof PrivateActionIdentityChanged)) {
        setNotice(exc instanceof Error ? exc.message : "Unable to save fact.");
      }
    } finally {
      if (lastSessionIdentity.current === actionIdentity) setBusyFact("");
    }
  }

  async function onFactApproval(fact: CandidateFact) {
    const actionIdentity = lastSessionIdentity.current;
    setBusyFact(fact.fact_id);
    try {
      await runPrivateMutation((userId) => approveFact(fact.fact_id, !fact.approved, userId));
      await load(true);
      if (!fact.approved) await onPrepareMyAutoDrafts();
    } catch (exc) {
      if (!(exc instanceof PrivateActionIdentityChanged)) {
        setNotice(exc instanceof Error ? exc.message : "Unable to update fact.");
      }
    } finally {
      if (lastSessionIdentity.current === actionIdentity) setBusyFact("");
    }
  }

  async function onFactDelete(fact: CandidateFact) {
    if (!window.confirm("Permanently remove this profile fact?")) return;
    const actionIdentity = lastSessionIdentity.current;
    setBusyFact(fact.fact_id);
    try {
      await runPrivateMutation((userId) => deleteFact(fact.fact_id, userId));
      await load(true);
    } catch (exc) {
      if (!(exc instanceof PrivateActionIdentityChanged)) {
        setNotice(exc instanceof Error ? exc.message : "Unable to delete fact.");
      }
    } finally {
      if (lastSessionIdentity.current === actionIdentity) setBusyFact("");
    }
  }

  async function onManualJob(event: FormEvent) {
    event.preventDefault();
    const payload = { ...jobForm };
    if (!payload.company.trim() || !payload.role_title.trim() || !payload.description.trim()) return;
    if (payload.application_url.trim()) {
      try {
        const url = new URL(payload.application_url);
        if (!["http:", "https:"].includes(url.protocol)) throw new Error("invalid protocol");
      } catch { setNotice("The job posting link must be a valid HTTP or HTTPS URL."); return; }
    }
    const actionIdentity = lastSessionIdentity.current;
    setManualBusy(true);
    try {
      const result = await runPrivateMutation((userId) => addManualJob(payload, userId));
      if (result.status !== "saved_private") throw new Error("The saved job was not accepted: " + result.status);
      setJobDialog(false);
      setJobForm({ company: "", role_title: "", location: "", description: "", application_url: "" });
      navigate("jobs");
      // Publish the notice before refreshing. If the account changes during
      // that refresh, clearPrivateWorkspace() can safely discard it.
      setNotice("Job saved privately to your account. Employer availability is unverified; it is not a ranked ATS listing.");
      await load(true);
    } catch (exc) {
      if (!(exc instanceof PrivateActionIdentityChanged)) {
        setNotice(exc instanceof Error ? exc.message : "Unable to add job.");
      }
    } finally {
      if (lastSessionIdentity.current === actionIdentity) setManualBusy(false);
    }
  }

  async function onRemovePrivateJob(item: PrivateSavedJob) {
    if (!window.confirm("Remove this job from your private saved list?")) return;
    const actionIdentity = lastSessionIdentity.current;
    setRemovingPrivateJob(item.saved_job_id);
    try {
      await runPrivateMutation((userId) => deletePrivateSavedJob(item.saved_job_id, userId));
      setPrivateSavedJobs((items) => items.filter((saved) => saved.saved_job_id !== item.saved_job_id));
      setNotice("The saved job was removed from your private account.");
    } catch (exc) {
      if (!(exc instanceof PrivateActionIdentityChanged)) {
        setNotice(exc instanceof Error ? exc.message : "Unable to remove the saved job.");
      }
    } finally {
      if (lastSessionIdentity.current === actionIdentity) setRemovingPrivateJob("");
    }
  }

  async function onPrepareMyAutoDrafts() {
    if (!preferences?.auto_draft_enabled || preferences.mode !== "personalized" ||
        !preferences.roles.length || autoDraftBusy) return;
    const actionIdentity = lastSessionIdentity.current;
    if (!actionIdentity || autoDraftInFlight.current === actionIdentity) return;
    // Set the lock synchronously before the first await, including uploads,
    // fact approvals and direct button clicks using this same action.
    autoDraftInFlight.current = actionIdentity;
    setAutoDraftBusy(true);
    try {
      const result = await runPrivateMutation((userId) => prepareMyMatchingDrafts(userId));
      // The existing account-verification helper checked the response
      // after the mutation. Never publish a cross-account success message.
      if (lastSessionIdentity.current !== actionIdentity) return;
      if (result.status === "needs_approved_profile") {
        navigate("profile");
        setNotice("Approve your career facts before SmartPloy prepares matched IT applications.");
      } else if (result.status === "needs_source_refresh") {
        navigate("jobs");
        setNotice("No new drafts: matching employer listings were not verified recently. The source worker must refresh those postings before safe automatic drafting.");
      } else if (result.status === "needs_trusted_source") {
        navigate("jobs");
        setNotice("No new drafts: matching jobs are manual or unverified imports. Automatic drafts require a recently refreshed, reviewed employer or official job feed.");
      } else if (result.created &&
                 ["prepared", "disabled_after_revocation"].includes(result.status)) {
        const firstNewKit = firstNewAutoDraftWorkspace(result);
        setSelectedWorkspaceId(firstNewKit);
        navigate("applications");
        setNotice(result.created + " new matched IT application draft(s) saved privately. " +
          (firstNewKit ? "Opened the first new draft for review. " :
            "Find your new drafts in My applications. ") +
          (result.stopped_on_opt_out ?
            "Automatic preparation stopped after you withdrew permission. " : "") +
          "Review each CV and letter before submitting." +
          agentTrackingNotice(result));
      } else if (result.status !== "prepared") {
        setNotice("Automatic drafts are not available for these account settings.");
      } else {
        navigate("jobs");
        setNotice("No new safe matches this time. Existing private drafts are preserved. Check the source and background-worker status before trying again." +
          agentTrackingNotice(result));
      }
    } catch (exc) {
      if (!(exc instanceof PrivateActionIdentityChanged) &&
          lastSessionIdentity.current === actionIdentity) {
        setNotice(exc instanceof Error ? exc.message : "Automatic draft preparation is unavailable.");
      }
    } finally {
      if (autoDraftInFlight.current === actionIdentity) autoDraftInFlight.current = null;
      if (lastSessionIdentity.current === actionIdentity) setAutoDraftBusy(false);
    }
  }

  async function onPrepareSelectedJobs(
    keys: string[], onProgress: (completed: number, total: number) => void,
    shouldStop: () => boolean = () => false, keepOnApply = false,
  ): Promise<AutoApplyBatchOutcome> {
    if (flowQueueInFlight.current) {
      throw new Error("An AutoApply preparation batch is already running.");
    }
    const selected = [...new Set(keys.filter(Boolean))].slice(0, 15);
    const empty: AutoApplyBatchOutcome = {
      preparedKeys: [], preparedWorkspaces: [], failedKeys: [], skippedKeys: [],
      stopRequested: false, accessInterrupted: false, issues: [],
      agentsActive: 0, agentsPaused: 0, agentsClosed: 0, agentsUnavailable: 0,
    };
    if (!selected.length) return empty;
    const identity = lastSessionIdentity.current;
    if (!identity) throw new Error("Sign in to prepare private applications.");
    const initialCVSelection = activeCVSelection.current;
    const ensureCVUnchanged = () => {
      if (activeCVSelection.current !== initialCVSelection) {
        throw new Error("Your CV changed during job preparation. Review the new CV and reselect jobs.");
      }
    };
    const token = Symbol("account-scoped-autoapply-batch");
    flowQueueInFlight.current = token;
    setFlowQueueBusy(true);
    const outcome: AutoApplyBatchOutcome = { ...empty };
    let firstWorkspace = "";
    let completed = 0;
    try {
      // SP49: one bad or retired posting must not starve subsequent chosen
      // jobs. Every request still passes the original private identity guard
      // and original idempotent workspace/Agent Zero create-or-get endpoints.
      for (let index = 0; index < selected.length; index += 1) {
        if (lastSessionIdentity.current !== identity ||
            flowQueueInFlight.current !== token) {
          throw new PrivateActionIdentityChanged();
        }
        ensureCVUnchanged();
        // Stop is cooperative and never interrupts a potentially committed
        // private workspace request. All remaining jobs are unattempted.
        if (shouldStop()) {
          outcome.stopRequested = true;
          outcome.skippedKeys!.push(...selected.slice(index));
          break;
        }
        const key = selected[index];
        try {
          const result = await runPrivateMutation((userId) =>
            startApplicationWorkspace(key, userId, true));
          if (!result.workspace?.workspace_id) {
            throw new Error("Application workspace response was incomplete.");
          }
          outcome.preparedKeys.push(key);
          // Preserve the exact owner-verified create-or-get response for
          // review; never guess an employer job from the workspace list order.
          outcome.preparedWorkspaces!.push({
            canonicalKey: key, workspaceId: result.workspace.workspace_id,
          });
          if (!firstWorkspace) firstWorkspace = result.workspace.workspace_id;
          switch (result.agent_tracking?.state) {
            case "active": outcome.agentsActive += 1; break;
            case "paused": outcome.agentsPaused += 1; break;
            case "closed": outcome.agentsClosed += 1; break;
            default: outcome.agentsUnavailable += 1;
          }
        } catch (exc) {
          // A changed/expired session is never a retryable job error:
          // stop before attempting another job under a different principal.
          if (exc instanceof PrivateActionIdentityChanged ||
              lastSessionIdentity.current !== identity ||
              flowQueueInFlight.current !== token) {
            throw new PrivateActionIdentityChanged();
          }
          // A login/permission failure applies to the whole batch. Never
          // attempt the next job under an unauthorized identity.
          const status = exc && typeof exc === "object" && "status" in exc
            ? (exc as { status?: unknown }).status : 0;
          if (status === 401 || status === 403) {
            // Keep already-created private drafts for this still-verified owner.
            // A different or expired OIDC subject is rejected above by the
            // original runPrivateMutation identity guard and never shown.
            outcome.failedKeys.push(key);
            outcome.issues!.push(describeAutoApplyBatchIssue(key, exc));
            outcome.accessInterrupted = true;
            outcome.skippedKeys!.push(...selected.slice(index + 1));
            completed += 1;
            if (flowQueueInFlight.current === token &&
                lastSessionIdentity.current === identity &&
                activeCVSelection.current === initialCVSelection) {
              onProgress(completed, selected.length);
            }
            break;
          }
          // A request may have committed its draft before a network error.
          // Existing create-or-get makes an explicit later retry idempotent.
          // Never copy raw API errors or personal details into the batch UI.
          outcome.failedKeys.push(key);
          outcome.issues!.push(describeAutoApplyBatchIssue(key, exc));
        }
        completed += 1;
        if (flowQueueInFlight.current === token &&
            lastSessionIdentity.current === identity &&
            activeCVSelection.current === initialCVSelection) {
          onProgress(completed, selected.length);
        }
      }
      if (lastSessionIdentity.current !== identity ||
          flowQueueInFlight.current !== token) {
        throw new PrivateActionIdentityChanged();
      }
      ensureCVUnchanged();
      const prepared = outcome.preparedKeys.length;
      const failed = outcome.failedKeys.length;
      const pending = outcome.skippedKeys!.length;
      if (prepared && !failed && !pending && !keepOnApply) {
        setSelectedWorkspaceId(firstWorkspace);
        navigate("applications");
      }
      // Partial success stays on Apply; successful exact keys will be
      // removed by the child's matching result, failures remain retryable.
      const agentSummary = outcome.agentsActive + " private per-job agent(s) ready for in-app tracking. " +
        (outcome.agentsPaused ? outcome.agentsPaused + " case(s) paused. " : "") +
        (outcome.agentsClosed ? outcome.agentsClosed + " case(s) closed. " : "") +
        (outcome.agentsUnavailable ? outcome.agentsUnavailable +
          " case(s) not actively tracking; check My applications and worker readiness. " : "") +
        "Agent reminders require the server worker. No applications were sent to employers.";
      if (outcome.accessInterrupted) {
        setNotice("Preparation stopped after an access denial. " + prepared +
          " private draft(s) remain saved; " + failed + " denied, " + pending +
          " not attempted. Restore access and reload before continuing. " +
          "No applications were sent to employers.");
      } else if (prepared && !failed && !pending) {
        setNotice(prepared + " private application draft(s) ready for review. " + agentSummary);
      } else if (prepared || pending) {
        setNotice(prepared + " private application draft(s) ready; " + failed +
          " failed, " + pending + " unattempted. " +
          (outcome.stopRequested ? "Stopped after the current job. " : "") +
          agentSummary);
      } else {
        setNotice("No selected drafts could be prepared. Review your CV, " +
          "current job source and account settings, then retry selected jobs. " +
          "No applications were sent to employers.");
      }
      return outcome;
    } finally {
      // An older asynchronous batch must never unlock the current account's
      // batch after logout, session switch or a newer run.
      if (flowQueueInFlight.current === token) {
        flowQueueInFlight.current = null;
        if (lastSessionIdentity.current === identity) setFlowQueueBusy(false);
      }
    }
  }

  async function onPrepare(canonicalKey: string) {
    const actionIdentity = lastSessionIdentity.current;
    setPreparing(canonicalKey);
    try {
      const response = await runPrivateMutation((userId) => startApplicationWorkspace(canonicalKey, userId));
      setSelectedWorkspaceId(response.workspace.workspace_id);
      navigate("applications");
      setNotice(response.created
        ? "Draft ready. Step 1: review and save your CV and letter. Step 2: complete the employer form. Step 3: confirm the outcome."
        : "Opened your existing private application documents.");
    } catch (exc) {
      if (!(exc instanceof PrivateActionIdentityChanged)) {
        const detail = exc instanceof Error ? exc.message : "Unable to create application documents.";
        if (/Upload a CV|approve profile facts|uploaded CV/i.test(detail)) navigate("profile");
        setNotice(detail);
      }
    } finally {
      if (lastSessionIdentity.current === actionIdentity) setPreparing("");
    }
  }

  if (loading && !dashboard) return <div className="loading-screen"><BrandMark className="loading-mark" /><span className="spinner" /><p>Preparing your workspace…</p></div>;
  if (!dashboard) return <div className="loading-screen"><BrandMark className="loading-mark" /><h1>SmartPloy isn't available</h1><p>{error}</p><button className="primary-btn" onClick={() => void load()} type="button">Try again</button></div>;

  if (preferences && !preferences.completed && page === "dashboard") {
    return <main className="setup-landing flow-first-use">
      <input ref={uploadRef} type="file" className="visually-hidden"
        aria-label="Select CV to upload"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        onChange={(event) => void onCVUpload(event)} />
      <div className="setup-brand"><BrandMark/><span><strong>SmartPloy</strong>
        <small>Simple job applications for Finland</small></span></div>
      <StartChoices onMode={(choice) => startApplyFlow(choice)}
        onBrowse={() => void startGeneralBrowse()} busyBrowse={startSearchBusy}
            onOpenApplications={() => navigate("applications")}
            cvPresent={cv.present} onUpload={onUploadClick}
            onCreateCV={() => navigate("profile")}/>
      <ReleaseStatus apiRevision={health?.release_revision} />
      {error ? <p className="setup-error" role="alert">{error}</p> : null}
      <details className="flow-advanced-setup">
        <summary>Advanced: customize search preferences (optional)</summary>
        <SearchSetup key={session?.user_id || session?.profile_id || session?.subject_fingerprint || "unidentified"}
          initial={preferences} onSave={saveSearchPreferences}/>
      </details>
      <p className="setup-privacy"><LockKeyhole size={14}/> Find jobs without a CV, or upload one for private matching.</p>
    </main>;
  }

  const accountViewKey = session?.user_id || session?.profile_id || session?.subject_fingerprint || "unidentified";
  const approved = facts.filter((item) => item.approved);
  const skills = approved.filter((item) => item.fact_type === "skill");
  const sourcesReady = dashboard.source_health.some((s) => s.status === "healthy");
  const obumReady = Boolean(localAI?.ready || health?.obumai_configured);
  const selectedNav = NAV.find((item) => item.id === page);
  const avatar = (session?.email?.charAt(0) || "U").toUpperCase();
  const counts = dashboard.applications;
  const onTool = (name: string) => {
    if (name === "CV Tailor" || name === "Cover Letter") {
      if (selectedWorkspaceId) {
        navigate("applications");
        setNotice("Open your selected application to edit and download its CV and cover letter.");
      } else {
        startApplyFlow("assisted");
        setNotice("Select a job below to open its CV and cover-letter editor.");
      }
    } else if (name === "Application prep") navigate("applications");
    else if (name === "Career insights") navigate("insights");
    else { navigate("tools"); setNotice("Interactive interview practice is planned, but not active yet."); }
  };

  // Derive background capability from the ORIGINAL worker task registry,
  // never from a candidate's opt-in checkbox alone.
  const autoDraftTask = dashboard.worker.tasks.find((task) =>
    task.task_id === "application:auto-draft-shortlist" && task.enabled
  );
  const autoDraftWorkerStatus: "not_configured" | "registered" | "degraded" =
    !dashboard.worker.ready || !autoDraftTask ? "not_configured" :
    ["failed", "degraded"].includes(autoDraftTask.last_status) ? "degraded" : "registered";

  const jobsSection = <SearchResultsPanel
    data={discovery} search={search} sector={sector} onSector={setSector}
    view={view} onView={setView} displayMode={mode}
    onToggleDisplay={() => setMode(mode === "heatmap" ? "percentage" : "heatmap")}
    currentPage={page === "jobs" ? "jobs" : "dashboard"}
    busyKey={preparing} onPrepare={(key) => void onPrepare(key)}
    onChooseFlow={(key, choice) => startApplyFlow(choice, key)}
    onAllJobs={() => navigate("jobs")}
    onChangeCriteria={() => navigate("settings")}
    onChangeMode={(choice) => void changeSearchMode(choice)}
    autoDraftEnabled={preferences?.auto_draft_enabled === true}
    autoDraftWorkerStatus={autoDraftWorkerStatus}
    autoDraftBusy={autoDraftBusy}
    onAutoDraft={() => void onPrepareMyAutoDrafts()}
  />;

  const cvBlock = <section className="panel cv-panel">
    <div className="panel-heading"><div><p className="section-kicker">YOUR CAREER EVIDENCE</p><h2>Your CV</h2><p>Private, on this SmartPloy account.</p></div></div>
    {cv.present ? <div className="uploaded-file">
      <span className="file-icon"><FileText size={24} /></span>
      <div className="uploaded-file-name"><strong>{cv.filename}</strong><small><CheckCircle2 size={13} /> Uploaded · {Math.round((cv.size_bytes ?? 0) / 1024)} KB</small></div>
      <a className="icon-btn" title="Download CV" aria-label="Download your CV" href="/api/v1/profile/cv/download"><Download size={19} /></a>
    </div> : <div className="cv-no-file"><UploadCloud size={23} /><strong>No CV uploaded yet</strong><span>Upload a PDF or DOCX to create your private profile workspace.</span></div>}
    <div className="row-actions">
      <button className="primary-btn" type="button" onClick={onUploadClick} disabled={busyCV}><UploadCloud size={17} /> {busyCV ? "Uploading…" : cv.present ? "Replace CV" : "Upload CV"}</button>
      {cv.present ? <button className="outline-btn" type="button" onClick={() => setCVPreview(!cvPreview)}>{cvPreview ? "Hide preview" : "Review text"}</button> : null}
      {cv.present ? <button className="icon-btn danger" type="button" aria-label="Delete CV" title="Delete uploaded CV" onClick={() => void onDeleteCV()} disabled={busyCV}><Trash2 size={18} /></button> : null}
    </div>
    {cv.present && cvPreview ? <div className="cv-text-preview"><strong>Extracted text for your review</strong><p>Text is not added to your approved profile automatically.</p><pre>{cv.text_preview || "No preview available."}</pre></div> : null}
    <p className="privacy-note"><LockKeyhole size={14} /> Your CV stays in SmartPloy. It is not submitted to employers or sent to ObumAI automatically.</p>
  </section>;

  const factPanel = <section className="panel facts-panel">
    <div className="panel-heading"><div><p className="section-kicker">VERIFIED PROFILE</p><h2>Skills & experience</h2><p>Only facts you approve affect job matching and AI drafts.</p></div><span className="subtle-count">{approved.length} approved</span></div>
    {facts.length ? <div className="facts-list">{facts.map((fact) => (
      <div className="fact-row" key={fact.fact_id}>
        <div><span className="fact-type">{fact.fact_type.replaceAll("_", " ")}</span><strong>{fact.value}</strong><small>{fact.approved ? "Verified by you" : "Needs your review"}</small></div>
        <button className={cx("fact-toggle", fact.approved && "approved")} type="button" disabled={busyFact === fact.fact_id} onClick={() => void onFactApproval(fact)} title={fact.approved ? "Mark unapproved" : "Approve this fact"}>{fact.approved ? <><Check size={15} /> Approved</> : "Approve"}</button>
        <button className="icon-btn subtle" type="button" title="Delete profile fact" aria-label="Delete profile fact" disabled={busyFact === fact.fact_id} onClick={() => void onFactDelete(fact)}><Trash2 size={16} /></button>
      </div>
    ))}</div> : <p className="muted padding-note">You have no profile evidence yet. Add a confirmed skill, qualification, language, or experience below.</p>}
    <form className="fact-form" onSubmit={(event) => void onAddFact(event)}>
      <div className="fact-inputs">
        <label>Fact type<select value={newFactType} onChange={(event) => setNewFactType(event.target.value)}>{FACT_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>What should SmartPloy know?<input type="text" maxLength={700} required placeholder="e.g. Python, Finnish B2, data analytics" value={newFactValue} onChange={(event) => setNewFactValue(event.target.value)} /></label>
      </div>
      <label className="check-confirm"><input type="checkbox" checked={confirmFact} onChange={(event) => setConfirmFact(event.target.checked)} /> I confirm this information is accurate and may be used for matching.</label>
      <button className="navy-btn" type="submit" disabled={busyFact === "new"}><Plus size={16} /> {busyFact === "new" ? "Saving…" : confirmFact ? "Save approved fact" : "Save for review"}</button>
    </form>
  </section>;

  const toolsPanel = <section className="panel tools-panel">
    <div className="panel-heading"><div><p className="section-kicker">YOUR WORKSPACE</p><h2>Career tools</h2><p>Practical tools built around your own evidence.</p></div></div>
    <div className="tool-grid">
      <Tool title="CV editor" description="Review and export a job-specific CV in PDF/DOCX" icon={FileText} ready={cv.present || approved.length > 0} onClick={() => onTool("CV Tailor")} />
      <Tool title="Cover letter editor" description="Edit and download a role-specific letter" icon={WandSparkles} ready={cv.present || approved.length > 0} onClick={() => onTool("Cover Letter")} />
      <Tool title="Application prep" description="Track and review draft packages" icon={FileCheck2} ready={true} onClick={() => onTool("Application prep")} />
      <Tool title="Interview prep" description="AI-assisted practice (planned)" icon={Sparkles} ready={false} onClick={() => onTool("Interview prep")} />
      <Tool title="Career insights" description="Explore your evidence and gaps" icon={ChartNoAxesColumn} ready={true} onClick={() => onTool("Career insights")} />
    </div>
    {!obumReady ? <div className="info-strip"><AlertCircle size={17} /> ObumAI service integration is not configured. AI generation tools stay unavailable until secure machine authentication is enabled.</div> : null}
  </section>;

  const privateSavedJobsPanel = <section className="panel sources-panel" aria-label="Your private saved jobs">
    <div className="panel-heading">
      <div>
        <p className="section-kicker">ONLY IN YOUR ACCOUNT</p>
        <h2>Your saved opportunities</h2>
        <p>Private bookmarks, not employer-verified vacancies or personalized match scores.</p>
      </div>
      <button className="outline-btn" type="button" onClick={() => setJobDialog(true)}>
        <Plus size={16} /> Save job
      </button>
    </div>
    {privateSavedJobs.length ? <div className="source-list">{privateSavedJobs.map((item) =>
      <div className="source-row" key={item.saved_job_id}>
        <span className="source-emblem"><LockKeyhole size={18} /></span>
        <div><strong>{item.role_title}</strong>
          <small>{item.company} · {item.location || "Location unknown"} · Employer availability unverified</small>
        </div>
        {safeExternalJobUrl(item.application_url) ?
          <a className="text-link" href={safeExternalJobUrl(item.application_url)}
            target="_blank" rel="noopener noreferrer" title="Check the original employer posting">
            Check posting <ArrowUpRight size={15} />
          </a> : item.application_url ? <span className="muted">Posting link unavailable</span> : null}
        <button className="icon-btn subtle" type="button"
          aria-label={"Remove saved job " + item.role_title}
          onClick={() => void onRemovePrivateJob(item)}
          disabled={removingPrivateJob === item.saved_job_id}>
          <Trash2 size={16} />
        </button>
      </div>
    )}</div> :
      <p className="muted padding-note">No private saved jobs yet. Your bookmarks appear here, separate from public job listings.</p>}
  </section>;

  const sourcePanel = <section className="panel sources-panel">
    <div className="panel-heading"><div><p className="section-kicker">SOURCE MONITOR</p><h2>Job sources</h2><p>Actual ingestion status — not estimated job counts.</p></div><span className={cx("state-pill", sourcesReady ? "good" : "waiting")}>{sourcesReady ? "Receiving jobs" : "Not active"}</span></div>
    {dashboard.source_health.length ? <div className="source-list">{dashboard.source_health.map((item) =>
      <div className="source-row" key={item.source_id}><span className="source-emblem"><Globe2 size={18} /></span><div><strong>{item.source_id}</strong><small>{item.last_item_count} jobs at last poll · {item.last_success_at ? relativeFreshness(item.last_success_at) : "No successful poll yet"}</small></div><span className={cx("state-pill", item.status === "healthy" ? "good" : "waiting")}>{item.status}</span></div>
    )}</div> : <Empty title="No live sources connected" description="Job Market Finland, Kuntarekry and public ATS integrations require an approved configuration before polling. No fake job numbers are displayed." icon={Database} action="Add a job manually" onAction={() => setJobDialog(true)} />}
  </section>;

  const sidePanel = <aside className="dashboard-side">
    <section className="panel profile-summary">
      <div className="small-heading"><h3>Your profile</h3><button className="text-link" type="button" onClick={() => navigate("profile")}>Edit profile <ArrowRight size={14} /></button></div>
      {cv.present ? <div className="profile-document"><FileText size={23} /><div><strong>{cv.filename}</strong><small><CheckCircle2 size={13} /> CV uploaded</small></div><button type="button" className="icon-btn" onClick={() => navigate("profile")} aria-label="View CV"><ChevronRight size={18} /></button></div> :
      <button type="button" className="profile-upload-placeholder" onClick={onUploadClick}><UploadCloud size={20} /> Upload your CV to get started <ArrowRight size={16} /></button>}
      <h4>Approved skills</h4>
      <div className="skill-tags">{skills.length ? skills.slice(0, 8).map((fact) => <span key={fact.fact_id}>{fact.value}</span>) : <small>No verified skills yet</small>}{skills.length > 8 ? <span>+{skills.length - 8}</span> : null}</div>
      <div className="evidence-summary"><span className="evidence-count">{approved.length}</span><div><strong>approved profile facts</strong><small>Used for matching, never inferred without review.</small></div></div>
      <button className="text-link" type="button" onClick={() => navigate("profile")}>Review your evidence <ArrowRight size={14} /></button>
    </section>
    <section className="panel compact-tools">
      <div className="small-heading"><h3>Your tools</h3><button className="text-link" type="button" onClick={() => navigate("tools")}>View all <ArrowRight size={14} /></button></div>
      <Tool title="CV documents" description="Editable PDF/DOCX application CV" icon={FileText} ready={cv.present || approved.length > 0} onClick={() => onTool("CV Tailor")} />
      <Tool title="Cover letters" description="Prepare and review a letter" icon={WandSparkles} ready={cv.present || approved.length > 0} onClick={() => onTool("Cover Letter")} />
      <Tool title="Applications" description="Review your pipeline" icon={BriefcaseBusiness} ready={true} onClick={() => navigate("applications")} />
    </section>
    <section className="panel source-overview">
      <div className="small-heading"><h3>Source activity</h3><button className="text-link" type="button" onClick={() => navigate("sources")}>Details <ArrowRight size={14} /></button></div>
      <span className={cx("state-pill", sourcesReady ? "good" : "waiting")}>{sourcesReady ? "Active source data" : "Awaiting configuration"}</span>
      <p>{dashboard.source_health.length ? String(dashboard.source_health.length) + " source status records available." : "No Finnish job feeds have completed a poll yet."}</p>
      <button className="text-link" type="button" onClick={() => setJobDialog(true)}>Add a job yourself <ArrowRight size={14} /></button>
    </section>
  </aside>;

  return <div className="smartploy-app">
    <a className="skip-to-content" href="#smartploy-main">Skip to main content</a>
    <input ref={uploadRef} type="file" className="visually-hidden" aria-label="Select CV to upload" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => void onCVUpload(event)} />
    <button className={cx("sidebar-scrim", mobileNav && "visible")} type="button" onClick={() => setMobileNav(false)} aria-label="Close navigation" />
    <aside className={cx("sidebar", mobileNav && "open")}>
      <button className="site-brand" type="button" onClick={() => navigate("dashboard")} aria-label="SmartPloy dashboard">
        <BrandMark className="site-brand-mark" /><span><strong>SmartPloy</strong><small>Job intelligence for Finland</small></span>
      </button>
      <nav className="sidebar-nav" aria-label="Main navigation">
        <div className="nav-label">WORKSPACE</div>
        {NAV.slice(0, 7).map((item) => { const Icon = item.icon; return <button type="button" key={item.id} className={cx("nav-item", page === item.id && "active")} onClick={() => navigate(item.id)} aria-current={page === item.id ? "page" : undefined}><Icon size={19} strokeWidth={1.9} /><span>{item.label}</span></button>; })}
        <div className="nav-divider" />
        <div className="nav-label">MANAGE</div>
        {NAV.slice(7).map((item) => { const Icon = item.icon; return <button type="button" key={item.id} className={cx("nav-item", page === item.id && "active")} onClick={() => navigate(item.id)} aria-current={page === item.id ? "page" : undefined}><Icon size={19} strokeWidth={1.9} /><span>{item.label}</span></button>; })}
      </nav>
      <div className="sidebar-bottom"><span className="country-chip"><span className="flag-finland" aria-hidden="true" /> Finland</span><span className="session-profile"><span className="avatar">{avatar}</span><span><strong>{session?.email ? session.email.split("@")[0] : "Your workspace"}</strong><small>{session?.authenticated ? "Signed in" : "Private workspace"}</small></span></span></div>
    </aside>
    <div className="main-column">
      <header className="site-header">
        <button className="icon-btn menu-toggle" aria-label="Open menu" type="button" onClick={() => setMobileNav(!mobileNav)}><Menu size={21} /></button>
        <div className="header-search"><Search size={19} /><input type="search" value={search} onChange={(event) => { setSearch(event.target.value); if (event.target.value) setPage("jobs"); }} placeholder="Search jobs, companies or locations…" aria-label="Search jobs" /></div>
        <span className="header-country"><MapPin size={16} /> Finland</span>
        <div className="header-tools">
          <a className="obumai-brand" href="https://app.obumai.com/" target="_self" title="Open ObumAI"><img src="/obumai-mark.svg" alt="" /> <strong>ObumAI</strong></a>
          <span className={cx("connection-status", obumReady ? "connected" : "disconnected")}><span />{localAI?.ready ? "Local AI ready" : health?.obumai_configured ? "ObumAI configured" : "AI optional"}</span>
          <button className="icon-btn header-refresh" type="button" onClick={() => void load(true)} disabled={refreshing} aria-label="Refresh workspace"><RefreshCw size={19} className={refreshing ? "rotate" : ""} /></button>
          <span className="avatar header-avatar" title={session?.email || "Your account"}>{avatar}</span>
        </div>
      </header>
      <main className="content" id="smartploy-main" tabIndex={-1}>
        {notice ? <div className="toast-notice" role="status"><Activity size={16} /><span>{notice}</span><button type="button" onClick={() => setNotice("")} aria-label="Dismiss notice"><X size={17} /></button></div> : null}
        {error ? <div className="toast-notice error" role="alert"><AlertCircle size={16} /><span>{error}</span><button type="button" onClick={() => void load()} aria-label="Retry"><RefreshCw size={17} /></button></div> : null}
        {page === "dashboard" ? <>
          {/* Make the actual CV-first application journey the first thing
              a signed-in applicant sees, not a hero followed by mode cards. */}
          <StartChoices onMode={(choice) => startApplyFlow(choice)}
            onBrowse={() => void startGeneralBrowse()} busyBrowse={startSearchBusy}
            onOpenApplications={() => navigate("applications")}
            cvPresent={cv.present} onUpload={onUploadClick}
            onCreateCV={() => navigate("profile")}/>
          <ReleaseStatus apiRevision={health?.release_revision} />
          {cv.present ? <section className="welcome-banner" aria-label="Finnish job discovery">
            <div className="welcome-copy"><p className="section-kicker">YOUR NORDIC CAREER WORKSPACE</p><h1>Make your next move.<br /><em>With clarity.</em></h1><p>Discover Finnish opportunities, build a trusted career profile and prepare the next step with SmartPloy.</p></div>
            <img className="helsinki-art" src="/helsinki-skyline.svg" alt="" />
            <div className="hero-tag"><span className="flag-finland" aria-hidden="true" /> Built for the Finnish job market</div>
          </section> : null}
          <div className="stats-grid">
            <Stat label={preferences?.mode === "general" ? "Available jobs" : "Preference matches"}
              value={preferences?.mode === "general" ? discovery?.available_count || 0 : discovery?.recommendations.length || 0}
              note={preferences?.mode === "general" ? "Current public listings" : "Based on your target roles and criteria"}
              icon={Target} tone="blue" onClick={() => { setView("top"); navigate("jobs"); }} />
            <Stat label={preferences?.mode === "general" ? "Healthy sources" : "Explore more"}
              value={preferences?.mode === "general" ? dashboard.source_health.filter((source) => source.status === "healthy").length : discovery?.broader.length || 0}
              note={preferences?.mode === "general" ? "Live job feeds" : "Other opportunities outside your main targets"}
              icon={BriefcaseBusiness} tone="orange" onClick={() => { setView("possible"); navigate("jobs"); }} />
            <Stat label="Awaiting review" value={counts.awaiting_review} note="Drafts, not submitted" icon={Clock3} tone="violet" onClick={() => navigate("applications")} />
            <Stat label="Actually submitted" value={counts.actually_submitted} note="Evidence of submission" icon={CheckCircle2} tone="green" onClick={() => navigate("applications")} />
          </div>
          <div className="dashboard-grid"><div>{jobsSection}</div>{sidePanel}</div>
        </> : null}
        {page !== "dashboard" ? <>
          <ReleaseStatus apiRevision={health?.release_revision} />
          <div className="page-intro"><div><p className="section-kicker">SMARTPLOY / {selectedNav?.label.toUpperCase()}</p><h1>{selectedNav?.label}</h1><p>{preferences?.mode === "general" ? "General search across current Finnish vacancies." : "Your private workspace, ranked by the search criteria you chose."}</p></div>
            {page === "jobs" ? <button type="button" className="primary-btn" onClick={() => setJobDialog(true)}><Plus size={17} /> Save job</button> : null}
            {page === "profile" ? <button type="button" className="primary-btn" onClick={onUploadClick}><UploadCloud size={17} /> {cv.present ? "Replace CV" : "Upload CV"}</button> : null}
          </div>
          {page === "apply" ? <ApplicationJourney
            key={accountViewKey} userId={session?.user_id || ""}
            cv={cv} mode={flowMode} selectedJobKey={flowSelectedJob}
            uploading={busyCV} preparing={preparing} queueBusy={flowQueueBusy}
            onMode={setFlowMode} onUpload={onUploadClick}
            onReviewCV={() => navigate("profile")}
            onFindJobs={() => void startGeneralBrowse()}
            onOpenApplications={(workspaceId) => {
              if (workspaceId) setSelectedWorkspaceId(workspaceId);
              navigate("applications");
            }}
            onPrepare={onPrepare} onPrepareSelected={onPrepareSelectedJobs}
          /> : null}
          {page === "jobs" ? <div className="stacked"><div className="secondary-grid">{jobsSection}<aside>{sourcePanel}</aside></div>{privateSavedJobsPanel}</div> : null}
          {page === "training" ? <TrainingProgramsPanel /> : null}
          {page === "profile" ? <div className="secondary-grid"><div className="stacked">
            {cvBlock}
            <MasterCVEditor key={accountViewKey} expectedUserId={session?.user_id || ""}
              cv={cv}
              onSave={(text, expectedSha256) => runPrivateMutation(
                (userId) => saveCVEditor(text, expectedSha256, userId)
              )}
              onRestore={(digest, expectedSha256) => runPrivateMutation(
                (userId) => restoreCVEditor(digest, expectedSha256, userId)
              )}
              onSaved={(saved) => {
                const firstCV = !cv.present && saved.present;
                setCV(saved); setCVPreview(false);
                setFlowMode(null); setFlowSelectedJob("");
                if (firstCV) {
                  // Creating a CV is equivalent to uploading one: immediately
                  // continue to Step 2, without forcing a separate search setup.
                  navigate("apply");
                  setNotice("Your new CV is saved. Step 2: choose Manual, Assisted or Automatic.");
                } else {
                  setNotice("Master CV saved. Revisit your application method and job documents before sending.");
                }
              }} />
            {factPanel}</div><aside>{sidePanel}</aside></div> : null}
          {page === "tools" ? <div className="secondary-grid">{toolsPanel}<aside>{cvBlock}</aside></div> : null}
          {page === "sources" ? <div className="secondary-grid">{sourcePanel}<aside><section className="panel"><h3>Continuous worker</h3><p className="muted">{dashboard.worker.ready ? "Worker available" : "Worker unavailable"} · {dashboard.worker.count} registered tasks</p>{dashboard.worker.tasks.map((task) => <div className="source-row" key={task.task_id}><span><strong>{formatState(task.task_kind)}</strong><small>{formatState(task.last_status)}</small></span></div>)}</section></aside></div> : null}
          {page === "applications" ? <div className="stacked">
            <ApplicationStudio key={accountViewKey} mode={flowMode} focusId={selectedWorkspaceId}
              expectedUserId={session?.user_id || ""} expectedAuthSource={session?.auth_source || ""}
              onFindJobs={() => navigate("apply")} />
            <section className="panel"><div className="panel-heading"><div><p className="section-kicker">APPLICATION TRACKER</p><h2>Your application pipeline</h2><p>A preparation draft is never counted as submitted.</p></div><span className="subtle-count">{applications.length} records</span></div>
            {applications.length ? <div className="applications-list">{applications.map((item) => <div className="application-list-row" key={item.application_id}><FileText size={20} /><div><strong>{formatState(item.state)}</strong><small>Job {item.canonical_key} · {item.updated_at ? relativeFreshness(item.updated_at) : "Updated time unknown"}</small></div><span className={cx("state-pill", item.has_been_submitted ? "good" : "waiting")}>{item.has_been_submitted ? "Submitted" : "Not submitted"}</span></div>)}</div> :
              <Empty title="No applications yet" description="When you've reviewed a job and prepared an application, the draft will appear here. No submissions are claimed without external evidence." icon={FileCheck2} action="Find jobs" onAction={() => navigate("jobs")} />}
            </section></div> : null}
          {page === "insights" ? <div className="secondary-grid"><section className="panel insights-panel"><p className="section-kicker">PROFILE INSIGHTS</p><h2>Your evidence, at a glance</h2><p className="muted">These figures come from your own verified profile, not estimates.</p><div className="insight-numbers"><div><strong>{facts.length}</strong><span>Total facts</span></div><div><strong>{approved.length}</strong><span>Approved facts</span></div><div><strong>{dashboard.top_matches.length + dashboard.possible_matches.length}</strong><span>Ranked matches</span></div></div><button className="primary-btn" type="button" onClick={() => navigate("profile")}>Improve profile <ArrowRight size={16} /></button></section><aside>{sourcePanel}</aside></div> : null}
          {page === "settings" && preferences ? <div className="stacked">
            <SearchSetup key={accountViewKey} initial={preferences} settings onSave={saveSearchPreferences} />
            <AIConsentSettings key={accountViewKey + "-ai-consent"}
              jobs={jobs} consents={aiConsents} events={aiConsentEvents}
              status={aiConsentStatus} busy={aiConsentBusy}
              onGrant={grantConsent} onRevoke={revokeConsent} />
            <section className="panel settings-panel">
              <h2>Privacy and account</h2>
              <p>Your search choices belong to your signed-in SmartPloy profile.
                General search does not rank jobs from personal data.</p>
              <p><ShieldCheck size={17} /> Account access is protected with the configured identity provider.</p>
              <p><LockKeyhole size={17} /> You decide which CV facts to approve and when to share application data.</p>
              <button className="outline-btn" type="button" onClick={() => navigate("profile")}>
                Manage personal data <ArrowRight size={16} />
              </button>
              {session?.auth_source === "oidc" ? <a className="outline-btn" href="/auth/logout">
                Sign out securely <ArrowRight size={16} />
              </a> : null}
            </section>
          </div> : null}
        </> : null}
        <footer className="site-footer"><span>SmartPloy · Job intelligence for Finland</span><span>Private CV matching · AI-assisted drafts · Employer submission requires confirmation</span></footer>
      </main>
    </div>
    {jobDialog ? <div className="modal-backdrop" role="presentation" onClick={() => setJobDialog(false)}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="add-job-title" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-heading"><div><p className="section-kicker">PRIVATE BOOKMARK</p><h2 id="add-job-title">Save an opportunity</h2><p>Only you can see this saved job. It is not added to the public feed, ranked, verified or submitted anywhere.</p></div><button className="icon-btn" type="button" onClick={() => setJobDialog(false)} aria-label="Close"><X size={21} /></button></div>
        <form className="dialog-form" onSubmit={(event) => void onManualJob(event)}>
          <label>Job title<input required maxLength={160} value={jobForm.role_title} onChange={(event) => setJobForm({ ...jobForm, role_title: event.target.value })} placeholder="e.g. Junior Data Analyst" /></label>
          <label>Company<input required maxLength={160} value={jobForm.company} onChange={(event) => setJobForm({ ...jobForm, company: event.target.value })} placeholder="Employer name" /></label>
          <label>Location<input maxLength={160} value={jobForm.location} onChange={(event) => setJobForm({ ...jobForm, location: event.target.value })} placeholder="e.g. Helsinki / Remote" /></label>
          <label>Job posting URL<input type="url" value={jobForm.application_url} onChange={(event) => setJobForm({ ...jobForm, application_url: event.target.value })} placeholder="https://..." /></label>
          <label>Description or key requirements<textarea required rows={5} maxLength={12000} value={jobForm.description} onChange={(event) => setJobForm({ ...jobForm, description: event.target.value })} placeholder="Paste the responsibilities and key requirements here." /></label>
          <button className="primary-btn" type="submit" disabled={manualBusy}><Plus size={17} /> {manualBusy ? "Saving…" : "Save job"}</button>
        </form>
      </div>
    </div> : null}
  </div>;
}
