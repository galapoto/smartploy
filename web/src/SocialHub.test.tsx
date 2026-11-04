// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import SocialHub from "./SocialHub";
import * as api from "./api";
import type { SocialMe, SocialConnections } from "./api";

vi.mock("./api", () => ({
  getSession: vi.fn(), getSocialMe: vi.fn(), getSocialConnections: vi.fn(),
  lookupSocialPerson: vi.fn(), saveSocialProfile: vi.fn(),
  followSocialPerson: vi.fn(), blockSocialPerson: vi.fn(),
  getSocialMessages: vi.fn(), sendSocialMessage: vi.fn(),
}));

const blank: SocialMe = {profile: null, opted_in: false};
const empty: SocialConnections = {
  following: [], followers: [], blocked: [], private: true,
};
let mine: SocialMe;
let network: SocialConnections;
let current = "usr-a";

beforeEach(() => {
  vi.resetAllMocks();
  current = "usr-a"; mine = structuredClone(blank); network = structuredClone(empty);
  vi.mocked(api.getSession).mockImplementation(async () => ({
    authenticated: true, user_id: current, profile_id: "profile-" + current,
    auth_source: "oidc", email: "same@example.invalid",
  }));
  vi.mocked(api.getSocialMe).mockImplementation(async () => mine);
  vi.mocked(api.getSocialConnections).mockImplementation(async () => network);
  vi.mocked(api.saveSocialProfile).mockImplementation(async payload => {
    mine = {profile: payload, opted_in: payload.discoverable};
    return mine;
  });
  vi.mocked(api.lookupSocialPerson).mockResolvedValue({
    handle: "colleague_1", display_name: "Synthetic Colleague",
    discoverable: true, following: false, follows_you: false, self: false,
  });
  vi.mocked(api.followSocialPerson).mockResolvedValue({
    following: true, follows_you: false, handle: "colleague_1",
  });
  vi.mocked(api.blockSocialPerson).mockResolvedValue({ blocked: true });
  vi.mocked(api.getSocialMessages).mockResolvedValue({
    messages: [], handle: "colleague_1", private: true,
  });
  vi.mocked(api.sendSocialMessage).mockResolvedValue({
    message: {message_id: "msg-1", body: "Hello", mine: true,
      created_at: "2026-11-04T19:00:00Z"}, private: true,
  });
});
afterEach(() => {cleanup(); vi.restoreAllMocks();});

describe("SP127 real network UI and owner identity", () => {
  it("starts private with an explicit opt-in; saving sends a bound user precondition", async () => {
    render(<SocialHub expectedUserId="usr-a" view="network" onOpenMessages={vi.fn()}/>);
    expect(await screen.findByRole("heading", {name: "Your professional handle"})).toBeTruthy();
    expect(screen.getByText(/It starts private/)).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("alex_jobs"), {
      target: {value: "newhandle1"},
    });
    fireEvent.change(screen.getByPlaceholderText("Your professional display name"), {
      target: {value: "Professional Person"},
    });
    fireEvent.click(screen.getByRole("checkbox", {
      name: /Allow other signed-in members to find me/,
    }));
    fireEvent.click(screen.getByRole("button", {
      name: /Save networking preferences/,
    }));
    await waitFor(() => expect(api.saveSocialProfile).toHaveBeenCalledWith({
      handle: "newhandle1", display_name: "Professional Person", discoverable: true,
    }, "usr-a"));
    expect(api.sendSocialMessage).not.toHaveBeenCalled();
    expect(api.followSocialPerson).not.toHaveBeenCalled();
  });

  it("can find an opt-in member but never follows or sends without an explicit click", async () => {
    render(<SocialHub expectedUserId="usr-a" view="network" onOpenMessages={vi.fn()}/>);
    expect(await screen.findByRole("heading", {name: "Find a professional"})).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", {name: "Exact member handle"}), {
      target: {value: "colleague_1"},
    });
    fireEvent.click(screen.getByRole("button", {name: "Find member"}));
    expect(await screen.findByText("Synthetic Colleague")).toBeTruthy();
    expect(api.lookupSocialPerson).toHaveBeenCalledWith("colleague_1");
    expect(screen.getByRole("button", {name: /Follow/})).toHaveProperty("disabled", true);
    expect(api.followSocialPerson).not.toHaveBeenCalled();
    expect(api.sendSocialMessage).not.toHaveBeenCalled();
  });

  it("opens a mutual conversation, renders text and sends only the approved message", async () => {
    mine = {profile: {handle:"mine123",display_name:"Own Person",discoverable:true},
      opted_in: true};
    network = { ...empty, following: [{
      handle:"colleague_1", display_name:"Synthetic Colleague",
      discoverable:true, mutual:true,
    }]};
    const onOpen = vi.fn();
    render(<SocialHub expectedUserId="usr-a" view="messages" initialPeer="colleague_1"
      onOpenMessages={onOpen}/>);
    expect(await screen.findByRole("heading", {name: "@colleague_1"})).toBeTruthy();
    await waitFor(() => expect(api.getSocialMessages).toHaveBeenCalledWith("colleague_1"));
    expect(api.sendSocialMessage).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox", {name: "Write a private message"}), {
      target: {value: "Hello"},
    });
    fireEvent.click(screen.getByRole("button", {name: "Send"}));
    await waitFor(() => expect(api.sendSocialMessage).toHaveBeenCalledWith(
      "colleague_1", "Hello", "usr-a"));
    expect(screen.getByText(/not end-to-end encrypted/)).toBeTruthy();
    expect(screen.queryByText(/All sent/)).toBeNull();
  });

  it("discards private network state on an account switch", async () => {
    let resolveMe!: (value: SocialMe) => void;
    vi.mocked(api.getSocialMe).mockImplementationOnce(
      () => new Promise<SocialMe>(resolve => {resolveMe = resolve;})
    );
    render(<SocialHub expectedUserId="usr-a" view="network" onOpenMessages={vi.fn()}/>);
    await waitFor(() => expect(api.getSocialMe).toHaveBeenCalledTimes(1));
    current = "usr-b";
    resolveMe({profile: {handle:"private_a",display_name:"PRIVATE ACCOUNT A",
      discoverable:true}, opted_in:true});
    expect(await screen.findByRole("heading", {name:"Sign-in verification required"})).toBeTruthy();
    expect(screen.queryByText("PRIVATE ACCOUNT A")).toBeNull();
    expect(api.saveSocialProfile).not.toHaveBeenCalled();
  });
});
