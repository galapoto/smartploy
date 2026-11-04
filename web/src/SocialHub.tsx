import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  AtSign, ArrowRight, CheckCircle2, LockKeyhole, MessageCircle,
  RefreshCw, Search, Send, ShieldCheck, UserPlus, UsersRound, X
} from "lucide-react";
import {
  blockSocialPerson, followSocialPerson, getSession, getSocialConnections,
  getSocialMe, getSocialMessages, lookupSocialPerson, saveSocialProfile,
  sendSocialMessage,
  type SocialConnection, type SocialConnections, type SocialLookup,
  type SocialMe, type SocialMessage,
} from "./api";

/** Human-to-human messaging only. No network directory scraping, shared CV or
 * unattended employer contact. Never label it WhatsApp or E2EE. */
export default function SocialHub(props: {
  expectedUserId: string;
  view: "network" | "messages";
  initialPeer?: string;
  onOpenMessages: (handle: string) => void;
}) {
  const [me, setMe] = useState<SocialMe | null>(null);
  const [connections, setConnections] = useState<SocialConnections | null>(null);
  const [handle, setHandle] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [discoverable, setDiscoverable] = useState(false);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<SocialLookup | null>(null);
  const [peer, setPeer] = useState(props.initialPeer || "");
  const [thread, setThread] = useState<SocialMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [blocked, setBlocked] = useState(false);
  const touchedProfile = useRef(false);
  const mounted = useRef(true);
  const viewEpoch = useRef(0);

  const denySwitchedAccount = useCallback((): never => {
    setBlocked(true); setMe(null); setConnections(null); setThread([]);
    setFound(null); setPeer(""); setDraft("");
    throw new Error("Your signed-in SmartPloy account changed. Reload before continuing.");
  }, []);

  const verifyAccount = useCallback(async () => {
    const session = await getSession();
    if (!session.authenticated || !props.expectedUserId ||
        session.user_id !== props.expectedUserId) {
      denySwitchedAccount();
    }
  }, [props.expectedUserId, denySwitchedAccount]);

  const load = useCallback(async () => {
    if (!props.expectedUserId) { setBlocked(true); setLoading(false); return; }
    const epoch = ++viewEpoch.current;
    try {
      const [mine, network] = await Promise.all([getSocialMe(), getSocialConnections()]);
      await verifyAccount();
      if (!mounted.current || epoch !== viewEpoch.current) return;
      setMe(mine); setConnections(network); setError("");
      if (mine.profile && !touchedProfile.current) {
        setHandle(mine.profile.handle);
        setDisplayName(mine.profile.display_name);
        setDiscoverable(mine.profile.discoverable);
      }
    } catch (exc) {
      if (!mounted.current || epoch !== viewEpoch.current) return;
      setError(exc instanceof Error ? exc.message : "Could not load your network");
    } finally {
      if (mounted.current && epoch === viewEpoch.current) setLoading(false);
    }
  }, [props.expectedUserId, verifyAccount]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; ++viewEpoch.current; };
  }, [load]);

  const run = useCallback(async (action: () => Promise<void>, success: string) => {
    if (busy || blocked) return;
    setBusy(true); setError(""); setStatus("");
    try {
      await verifyAccount();
      await action();
      await verifyAccount();
      if (!mounted.current) return;
      setStatus(success);
      await load();
    } catch (exc) {
      if (mounted.current) setError(exc instanceof Error ? exc.message : "Action failed");
    } finally {
      if (mounted.current) setBusy(false);
    }
  }, [busy, blocked, verifyAccount, load]);

  const saveProfile = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      await saveSocialProfile({
        handle: handle.trim().toLowerCase(),
        display_name: displayName.trim(), discoverable
      }, props.expectedUserId);
      touchedProfile.current = false;
    }, discoverable ? "Your professional handle is now available to people who know it." :
      "Your professional handle is private. People cannot discover or message you.");
  };

  const findPerson = (event: FormEvent) => {
    event.preventDefault();
    if (blocked || searching) return;
    const exact = query.trim().toLowerCase();
    setSearching(true); setFound(null); setError(""); setStatus("");
    void (async () => {
      try {
        if (!/^[a-z][a-z0-9_]{2,23}$/.test(exact)) {
          throw new Error("Enter an exact professional handle, such as alex_jobs");
        }
        const person = await lookupSocialPerson(exact);
        await verifyAccount();
        if (mounted.current) setFound(person);
      } catch (exc) {
        if (mounted.current) setError(
          exc instanceof Error ? exc.message : "That member is not available");
      } finally {
        if (mounted.current) setSearching(false);
      }
    })();
  };

  const changeFollow = (person: SocialLookup, value: boolean) => {
    void run(async () => {
      await followSocialPerson(person.handle, value, props.expectedUserId);
      const latest = await lookupSocialPerson(person.handle);
      await verifyAccount();
      if (mounted.current) setFound(latest);
    }, value ? "You are following @" + person.handle : "You unfollowed @" + person.handle);
  };

  const block = (person: { handle: string }, value: boolean) => {
    if (value && !window.confirm("Block @" + person.handle +
      "? You will stop following each other and cannot message.")) return;
    void run(async () => {
      await blockSocialPerson(person.handle, value, props.expectedUserId);
      setFound(null);
      if (peer === person.handle) { setPeer(""); setThread([]); }
    }, value ? "Member blocked. Both follow links have been removed." :
      "Member unblocked. You must follow each other again to message.");
  };

  const mutual = useMemo(() => {
    const unique = new Map<string, SocialConnection>();
    for (const person of connections?.following || []) {
      if (person.mutual) unique.set(person.handle, person);
    }
    return Array.from(unique.values());
  }, [connections]);

  useEffect(() => {
    if (props.view !== "messages" || !peer || blocked) return;
    let active = true;
    const update = async () => {
      try {
        const result = await getSocialMessages(peer);
        await verifyAccount();
        if (mounted.current && active) setThread(result.messages);
      } catch (exc) {
        if (mounted.current && active) setError(
          exc instanceof Error ? exc.message : "Messages unavailable");
      }
    };
    setThread([]);
    void update();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void update();
    }, 15000);
    return () => { active = false; window.clearInterval(id); };
  }, [props.view, peer, blocked, verifyAccount]);

  const send = (event: FormEvent) => {
    event.preventDefault();
    const body = draft.trim();
    if (!body || !peer) return;
    void run(async () => {
      const result = await sendSocialMessage(peer, body, props.expectedUserId);
      await verifyAccount();
      if (!mounted.current) return;
      setDraft("");
      setThread(previous => [...previous, result.message]);
    }, "Message saved and sent to the connected SmartPloy member.");
  };

  if (blocked || !props.expectedUserId) {
    return <section className="sp127-hub" role="alert">
      <h2>Sign-in verification required</h2>
      <p>Your network is private. Reload SmartPloy and sign in to continue.</p>
    </section>;
  }

  return <section className="sp127-hub" aria-label="Professional network and messages">
    <header className="sp127-intro">
      <div>
        <p className="section-kicker">SMARTPLOY · PROFESSIONAL COMMUNITY</p>
        <h2>{props.view === "network" ? "Build meaningful connections." :
          "Conversations with your connections."}</h2>
        <p>Follow professionals who choose to be visible. Private messages are available
          only when you follow each other. Your CV and account email are never shown.</p>
      </div>
      <span className="sp127-privacy-pill"><ShieldCheck size={16} aria-hidden="true"/>
        Opt-in connections</span>
    </header>
    {loading ? <p role="status" className="sp127-feedback">Loading your private network…</p> : null}
    {error ? <div role="alert" className="sp127-error">{error}</div> : null}
    {status ? <div role="status" className="sp127-feedback">
      <CheckCircle2 size={17} aria-hidden="true"/>{status}</div> : null}
    <nav className="sp127-shortcuts" aria-label="Network views">
      <span><UsersRound size={18} aria-hidden="true"/> Following and connections</span>
      <span><MessageCircle size={18} aria-hidden="true"/> Mutual-follow messages</span>
    </nav>
    {props.view === "network" ? <div className="sp127-columns">
      <div className="sp127-stack">
        <section className="sp127-card">
          <div className="sp127-card-heading">
            <div><p className="section-kicker">YOUR CHOICE</p>
              <h3>Your professional handle</h3></div>
            <span className={me?.opted_in ? "sp127-tag" : "sp127-tag neutral"}>
              {me?.opted_in ? "Discoverable by handle" : "Private"}</span>
          </div>
          <p className="sp127-muted">This is a separate profile for professional networking.
            Only your chosen handle and display name can be seen. It starts private.</p>
          <form className="sp127-form" onSubmit={saveProfile}>
            <label>Handle
              <div className="sp127-input-icon"><AtSign size={17} aria-hidden="true"/>
                <input required maxLength={24} minLength={3} pattern="[a-z][a-z0-9_]{2,23}"
                  value={handle} disabled={busy}
                  placeholder="alex_jobs" autoComplete="off"
                  onChange={event => { touchedProfile.current = true;
                    setHandle(event.target.value.toLowerCase()); }}/>
              </div>
            </label>
            <label>Display name
              <input required minLength={2} maxLength={60} disabled={busy}
                value={displayName} placeholder="Your professional display name"
                onChange={event => { touchedProfile.current = true;
                  setDisplayName(event.target.value); }}/>
            </label>
            <label className="sp127-opt-in"><input type="checkbox" checked={discoverable}
              disabled={busy} onChange={event => { touchedProfile.current = true;
                setDiscoverable(event.target.checked); }}/>
              <span>Allow other signed-in members to find me by my exact handle</span>
            </label>
            <button type="submit" disabled={busy || !handle || !displayName}
              className="navy-btn">Save networking preferences <ArrowRight size={17} /></button>
          </form>
        </section>
        <section className="sp127-card">
          <div className="sp127-card-heading"><h3>Find a professional</h3>
            <Search size={19} aria-hidden="true"/></div>
          <p className="sp127-muted">Enter an exact handle. There is no searchable
            directory of private users.</p>
          <form className="sp127-search" onSubmit={findPerson}>
            <input type="search" aria-label="Exact member handle" maxLength={24}
              value={query} placeholder="e.g. alex_jobs"
              onChange={event => setQuery(event.target.value)}/>
            <button className="primary-btn" type="submit" disabled={searching || busy}>
              {searching ? "Finding…" : "Find member"}</button>
          </form>
          {found ? <div className="sp127-found" aria-label="Matching professional">
            <span className="sp127-avatar">{found.display_name.slice(0,1).toUpperCase()}</span>
            <div className="sp127-person"><strong>{found.display_name}</strong>
              <small>@{found.handle} {found.follows_you ? "· follows you" : ""}</small>
            </div>
            {!found.self ? <div className="sp127-person-actions">
              <button type="button" className="outline-btn" disabled={busy || !me?.opted_in}
                onClick={() => changeFollow(found, !found.following)}>
                <UserPlus size={15} aria-hidden="true"/>
                {found.following ? "Unfollow" : "Follow"}</button>
              {found.following && found.follows_you ?
                <button className="navy-btn" type="button"
                  onClick={() => props.onOpenMessages(found.handle)}>
                  <MessageCircle size={15} aria-hidden="true"/> Message</button> : null}
              <button type="button" className="sp127-quiet" disabled={busy}
                onClick={() => block(found, true)}>Block</button>
            </div> : <small>This is your own profile.</small>}
          </div> : null}
        </section>
      </div>
      <div className="sp127-stack">
        <section className="sp127-card">
          <div className="sp127-card-heading"><h3>Following</h3>
            <span className="sp127-count">{connections?.following.length || 0}</span></div>
          {connections?.following.length ? connections.following.map(person =>
            <div className="sp127-connection" key={person.handle}>
              <span className="sp127-avatar">{person.display_name.slice(0,1).toUpperCase()}</span>
              <div className="sp127-person"><strong>{person.display_name}</strong>
                <small>@{person.handle} · {person.mutual ? "Mutual connection" : "Following"}</small></div>
              {person.mutual ? <button type="button" className="sp127-icon"
                aria-label={"Message " + person.display_name}
                onClick={() => props.onOpenMessages(person.handle)}>
                <MessageCircle size={18}/></button> : null}
            </div>
          ) : <p className="sp127-muted">Follow someone by their exact handle to begin.</p>}
        </section>
        <section className="sp127-card">
          <div className="sp127-card-heading"><h3>Followers</h3>
            <span className="sp127-count">{connections?.followers.length || 0}</span></div>
          {connections?.followers.length ? connections.followers.map(person =>
            <div className="sp127-connection" key={person.handle}>
              <span className="sp127-avatar">{person.display_name.slice(0,1).toUpperCase()}</span>
              <div className="sp127-person"><strong>{person.display_name}</strong>
                <small>@{person.handle} {person.mutual ? "· Connected" : ""}</small></div>
            </div>
          ) : <p className="sp127-muted">No followers yet. Share your handle personally.</p>}
        </section>
        {connections?.blocked.length ? <section className="sp127-card">
          <h3>Blocked members</h3>
          {connections.blocked.map(person => <div className="sp127-connection"
            key={person.handle}>
            <span>@{person.handle}</span>
            <button className="outline-btn" disabled={busy} type="button"
              onClick={() => block(person, false)}>Unblock</button>
          </div>)}
        </section> : null}
      </div>
    </div> : <div className="sp127-inbox">
      <section className="sp127-card sp127-inbox-people">
        <div className="sp127-card-heading"><h3>Connected people</h3>
          <span className="sp127-count">{mutual.length}</span></div>
        {mutual.length ? mutual.map(person =>
          <button type="button" key={person.handle}
            className={"sp127-chat-peer " + (peer === person.handle ? "selected" : "")}
            aria-current={peer === person.handle ? "true" : undefined}
            onClick={() => {setPeer(person.handle); setError("");}}>
            <span className="sp127-avatar">{person.display_name.slice(0,1).toUpperCase()}</span>
            <span className="sp127-person"><strong>{person.display_name}</strong>
              <small>@{person.handle}</small></span><ArrowRight size={16}/>
          </button>
        ) : <p className="sp127-muted">A conversation becomes available after
          you and another professional follow each other.</p>}
      </section>
      <section className="sp127-card sp127-conversation" aria-label="Private conversation">
        {peer && mutual.some(item => item.handle === peer) ? <>
          <div className="sp127-card-heading">
            <div><p className="section-kicker">PRIVATE CONVERSATION</p>
              <h3>@{peer}</h3></div>
            <button type="button" className="sp127-icon" onClick={() => setPeer("")}
              aria-label="Close conversation"><X size={19}/></button>
          </div>
          <div className="sp127-messages" role="log" aria-label={"Messages with " + peer}>
            {thread.length ? thread.map(item =>
              <article key={item.message_id}
                className={"sp127-message " + (item.mine ? "mine" : "theirs")}>
                <p>{item.body}</p>
                <time dateTime={item.created_at}>
                  {new Date(item.created_at).toLocaleString()}</time>
              </article>
            ) : <p className="sp127-muted">No messages here yet. Say hello to start.</p>}
          </div>
          <form className="sp127-compose" onSubmit={send}>
            <label htmlFor="sp127-message-draft" className="visually-hidden">Write a private message</label>
            <textarea id="sp127-message-draft" rows={2} maxLength={2000} required
              disabled={busy} value={draft} placeholder="Write a professional message…"
              onChange={event => setDraft(event.target.value)}/>
            <button className="primary-btn" type="submit" disabled={busy || !draft.trim()}>
              <Send size={17} aria-hidden="true"/>{busy ? "Sending…" : "Send"}</button>
          </form>
          <p className="sp127-muted sp127-security"><LockKeyhole size={14} aria-hidden="true"/>
            Messages are private to the two SmartPloy accounts, but are not
            end-to-end encrypted. Do not share passwords or sensitive documents.</p>
        </> : <div className="sp127-conversation-empty">
          <MessageCircle size={32} aria-hidden="true"/>
          <h3>Choose a conversation</h3>
          <p>Messages stay inside SmartPloy. Only mutual followers can write to each other.</p>
        </div>}
      </section>
    </div>}
    <p className="sp127-legal"><ShieldCheck size={15} aria-hidden="true"/>
      This feature does not send job applications, expose your CV,
      connect to Facebook, WhatsApp or LinkedIn, or message employers automatically.</p>
    <button className="sp127-refresh" type="button" disabled={busy}
      onClick={() => void load()}><RefreshCw size={15}/> Refresh connections</button>
  </section>;
}
