/**
 * dom.js — shared DOM element references for the browser app.
 */

const $ = (id) => document.getElementById(id);

export const statusEl = $("status");
export const sessionsList = $("sessions-list");
export const messagesEl = $("messages");
export const emptyState = $("empty-state");
export const errorBanner = $("error-banner");
export const composerBannerEl = $("composer-banner");
export const chatTitleEl = $("chat-title");
export const chatSubtitleEl = $("chat-subtitle");
export const chatProviderBadgeEl = $("chat-provider-badge");
export const chatModelBadgeEl = $("chat-model-badge");
export const chatProfileBadgeEl = $("chat-profile-badge");
export const chatModeBadgeEl = $("chat-mode-badge");
export const chatLockBadgeEl = $("chat-lock-badge");
export const draftConfigEl = $("draft-config");
export const draftProviderSelectEl = $("draft-provider-select");
export const draftModelSelectEl = $("draft-model-select");
export const draftProfileSelectEl = $("draft-profile-select");
export const draftTaskSelectEl = $("draft-task-select");
export const promptSettingsBtn = $("prompt-settings");
export const renameSessionBtn = $("rename-session");
export const archiveSessionBtn = $("archive-session");
export const newChatBtn = $("new-chat");
export const inputEl = $("input");
export const sendBtn = $("send");
export const providerPillEl = $("provider-pill");
