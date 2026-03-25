/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ── Helpers ──────────────────────────────────────────────────────
const COLORS = ["#00a884","#5b72e0","#d4508b","#ff9500","#8e5ec8","#e55050","#20b2aa","#cd853f"];
function avatarColor(id) { return COLORS[(id || 0) % 8]; }
function avatarInitial(name) { return name ? name.charAt(0).toUpperCase() : "?"; }
function timeAgo(d) {
    if (!d) return "";
    const s = (Date.now() - new Date(d).getTime()) / 1000;
    if (s < 60) return "now";
    if (s < 3600) return Math.floor(s / 60) + "m";
    if (s < 86400) return Math.floor(s / 3600) + "h";
    if (s < 172800) return "yesterday";
    return new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
function formatTime(d) {
    return d ? new Date(d).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "";
}
function formatDate(d) {
    if (!d) return "";
    const dt = new Date(d);
    const today = new Date();
    const yest = new Date(today); yest.setDate(yest.getDate() - 1);
    if (dt.toDateString() === today.toDateString()) return "Today";
    if (dt.toDateString() === yest.toDateString()) return "Yesterday";
    return dt.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}
function truncate(t, l) { l = l || 50; return t && t.length > l ? t.substring(0, l) + "..." : (t || ""); }

const STATE_DOTS = { new: "#00a884", active: "#00a884", ai_handled: "#8e5ec8", human_takeover: "#f59e0b", closed: "#9ca3af" };
const STATE_LABELS = { new: "New", active: "Active", ai_handled: "AI handling", human_takeover: "Human agent", closed: "Closed" };


// ══════════════════════════════════════════════════════════════════
// MAIN APP COMPONENT — registered as client action
// ══════════════════════════════════════════════════════════════════

export class WhatsAppApp extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.messagesRef = useRef("messagesContainer");

        this.state = useState({
            view: "chat",
            loading: true,
            conversations: [],
            selectedConvId: null,
            messages: [],
            filter: "all",
            searchQuery: "",
            showInfo: false,
            sending: false,
            composerText: "",
            partner: null,
            stats: {
                total_conversations: 0, active_conversations: 0,
                ai_handled: 0, human_takeover: 0,
                messages_today: 0, messages_week: 0,
                failed_messages: 0, total_messages: 0,
            },
            recentConversations: [],
            recentMessages: [],
        });

        onWillStart(async () => {
            await this.loadConversations();
            await this.loadDashboardStats();
            this.state.loading = false;
        });

        this._pollInterval = null;
        onMounted(() => {
            this._pollInterval = setInterval(() => this.pollUpdates(), 10000);
        });
    }

    willUnmount() {
        if (this._pollInterval) clearInterval(this._pollInterval);
    }

    // ── Data ─────────────────────────────────────────────────────

    async loadConversations() {
        try {
            this.state.conversations = await this.orm.searchRead(
                "whatsapp.conversation", [],
                ["display_name", "phone", "state", "last_message_body",
                 "last_message_date", "message_count", "partner_id", "assigned_user_id"],
                { order: "last_message_date desc", limit: 100 },
            );
        } catch (e) { console.error(e); }
    }

    async loadMessages(convId) {
        if (!convId) { this.state.messages = []; return; }
        try {
            this.state.messages = await this.orm.searchRead(
                "whatsapp.message",
                [["conversation_id", "=", convId]],
                ["create_date", "direction", "body", "state", "is_chatbot",
                 "message_type", "phone", "wa_message_id", "error_message"],
                { order: "create_date asc", limit: 200 },
            );
        } catch (e) { console.error(e); }
    }

    async loadPartner(pid) {
        if (!pid) { this.state.partner = null; return; }
        try {
            const r = await this.orm.searchRead(
                "res.partner", [["id", "=", pid]],
                ["name", "email", "phone", "mobile", "city", "country_id"],
                { limit: 1 },
            );
            this.state.partner = r.length ? r[0] : null;
        } catch (e) { this.state.partner = null; }
    }

    async loadDashboardStats() {
        try {
            const today = new Date().toISOString().split("T")[0];
            const week = new Date(Date.now() - 7 * 86400000).toISOString().split("T")[0];
            const [total, active, ai, human, mToday, mWeek, failed, totalMsg] =
                await Promise.all([
                    this.orm.searchCount("whatsapp.conversation", []),
                    this.orm.searchCount("whatsapp.conversation", [["state", "in", ["active", "ai_handled", "new"]]]),
                    this.orm.searchCount("whatsapp.conversation", [["state", "=", "ai_handled"]]),
                    this.orm.searchCount("whatsapp.conversation", [["state", "=", "human_takeover"]]),
                    this.orm.searchCount("whatsapp.message", [["create_date", ">=", today]]),
                    this.orm.searchCount("whatsapp.message", [["create_date", ">=", week]]),
                    this.orm.searchCount("whatsapp.message", [["state", "=", "failed"]]),
                    this.orm.searchCount("whatsapp.message", []),
                ]);
            Object.assign(this.state.stats, {
                total_conversations: total, active_conversations: active,
                ai_handled: ai, human_takeover: human,
                messages_today: mToday, messages_week: mWeek,
                failed_messages: failed, total_messages: totalMsg,
            });
            this.state.recentConversations = await this.orm.searchRead(
                "whatsapp.conversation", [["state", "!=", "closed"]],
                ["display_name", "phone", "state", "last_message_body", "last_message_date", "message_count"],
                { limit: 6, order: "last_message_date desc" },
            );
            this.state.recentMessages = await this.orm.searchRead(
                "whatsapp.message", [],
                ["create_date", "phone", "direction", "body", "state", "is_chatbot"],
                { limit: 8, order: "create_date desc" },
            );
        } catch (e) { console.error(e); }
    }

    async pollUpdates() {
        await this.loadConversations();
        if (this.state.selectedConvId) await this.loadMessages(this.state.selectedConvId);
    }

    // ── Computed ──────────────────────────────────────────────────

    get selectedConversation() {
        return this.state.conversations.find(c => c.id === this.state.selectedConvId) || null;
    }

    get filteredConversations() {
        let list = this.state.conversations;
        const f = this.state.filter;
        if (f === "unread") list = list.filter(c => c.state === "new");
        else if (f === "ai") list = list.filter(c => c.state === "ai_handled");
        else if (f === "human") list = list.filter(c => c.state === "human_takeover");
        const q = (this.state.searchQuery || "").toLowerCase();
        if (q) list = list.filter(c =>
            (c.display_name || "").toLowerCase().includes(q) || (c.phone || "").includes(q)
        );
        return list;
    }

    get groupedMessages() {
        const groups = [];
        let lastDate = null;
        for (const msg of this.state.messages) {
            const ds = formatDate(msg.create_date);
            if (ds !== lastDate) { groups.push({ type: "date", label: ds }); lastDate = ds; }
            groups.push({ type: "message", data: msg });
        }
        return groups;
    }

    get activeConvCount() {
        return this.state.conversations.filter(c => c.state === "new").length;
    }

    // ── Helpers exposed to template ──────────────────────────────

    avatarColor(id) { return avatarColor(id); }
    avatarInitial(n) { return avatarInitial(n); }
    timeAgo(d) { return timeAgo(d); }
    formatTime(d) { return formatTime(d); }
    truncate(t, l) { return truncate(t, l); }
    stateDot(s) { return STATE_DOTS[s] || "#9ca3af"; }
    stateLabel(s) { return STATE_LABELS[s] || s; }

    bubbleClass(msg) {
        if (msg.direction === "incoming") return "wa-bubble incoming";
        if (msg.is_chatbot) return "wa-bubble ai-reply";
        return "wa-bubble outgoing";
    }
    statusIcon(msg) {
        if (msg.direction === "incoming") return "";
        const m = { sent: "fa-check", delivered: "fa-check delivered", read: "fa-check read", failed: "fa-exclamation-circle" };
        return m[msg.state] || "fa-clock-o";
    }

    // ── UI handlers ──────────────────────────────────────────────

    setView(v) {
        this.state.view = v;
        if (v === "dashboard") this.loadDashboardStats();
    }

    async selectConversation(convId) {
        this.state.selectedConvId = convId;
        this.state.showInfo = false;
        await this.loadMessages(convId);
        const c = this.selectedConversation;
        if (c && c.partner_id) await this.loadPartner(c.partner_id[0]);
        else this.state.partner = null;
        this.scrollToBottom();
    }

    scrollToBottom() {
        setTimeout(() => {
            const el = this.messagesRef.el;
            if (el) el.scrollTop = el.scrollHeight;
        }, 50);
    }

    setFilter(f) { this.state.filter = f; }
    onSearchInput(ev) { this.state.searchQuery = ev.target.value; }
    toggleInfo() { this.state.showInfo = !this.state.showInfo; }
    onComposerInput(ev) { this.state.composerText = ev.target.value; }

    onComposerKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); this.sendMessage(); }
    }

    async sendMessage() {
        const text = this.state.composerText.trim();
        const conv = this.selectedConversation;
        if (!text || !conv) return;
        this.state.sending = true;
        this.state.composerText = "";
        try {
            await this.orm.call("whatsapp.conversation", "send_whatsapp_reply", [[conv.id], text]);
            await this.loadMessages(conv.id);
            await this.loadConversations();
            this.notification.add("Message sent", { type: "success" });
        } catch (e) {
            this.notification.add("Failed: " + (e.message || "Error"), { type: "danger" });
        }
        this.state.sending = false;
        this.scrollToBottom();
    }

    async takeoverConversation() {
        const c = this.selectedConversation;
        if (!c) return;
        await this.orm.call("whatsapp.conversation", "action_human_takeover", [[c.id]]);
        await this.loadConversations();
    }

    async resumeAi() {
        const c = this.selectedConversation;
        if (!c) return;
        await this.orm.call("whatsapp.conversation", "action_resume_ai", [[c.id]]);
        await this.loadConversations();
    }

    async closeConversation() {
        const c = this.selectedConversation;
        if (!c) return;
        await this.orm.call("whatsapp.conversation", "action_close", [[c.id]]);
        this.state.selectedConvId = null;
        this.state.messages = [];
        await this.loadConversations();
    }

    openInOdoo() {
        const c = this.selectedConversation;
        if (!c) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "whatsapp.conversation",
            res_id: c.id,
            view_mode: "form",
            views: [[false, "form"]],
        });
    }

    openCompose() {
        this.action.doAction("whatsapp_ai_integration.action_whatsapp_compose_wizard");
    }

    openSettings() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Settings",
            res_model: "res.config.settings",
            view_mode: "form",
            target: "inline",
            context: { module: "whatsapp_ai_integration" },
        });
    }

    openConversationFromDash(convId) {
        this.state.view = "chat";
        this.selectConversation(convId);
    }

    navigateFromDash(target) {
        if (target === "conversations") this.state.view = "chat";
        else if (target === "failed") this.action.doAction("whatsapp_ai_integration.action_whatsapp_message_failed");
    }
}

WhatsAppApp.template = "whatsapp_ai_integration.App";

registry.category("actions").add("whatsapp_ai_dashboard", WhatsAppApp);
