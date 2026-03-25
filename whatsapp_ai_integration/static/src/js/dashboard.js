/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ── Utility helpers ──────────────────────────────────────────────
function avatarColor(id) {
    return `wa-avatar-${(id || 0) % 8}`;
}

function avatarInitial(name) {
    if (!name) return "?";
    return name.charAt(0).toUpperCase();
}

function timeAgo(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    const now = new Date();
    const diff = (now - d) / 1000;
    if (diff < 60) return "now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    if (diff < 172800) return "yesterday";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatTime(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function formatDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return "Today";
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    return d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

function truncate(text, len = 50) {
    if (!text) return "";
    return text.length > len ? text.substring(0, len) + "..." : text;
}


// ══════════════════════════════════════════════════════════════════
// CONVERSATION LIST (sidebar)
// ══════════════════════════════════════════════════════════════════

class ConversationList extends Component {
    static template = "whatsapp_ai_integration.ConversationList";
    static props = {
        conversations: { type: Array },
        selectedId: { type: [Number, { value: null }], optional: true },
        filter: { type: String },
        searchQuery: { type: String },
        onSelect: { type: Function },
        onFilterChange: { type: Function },
        onSearchChange: { type: Function },
    };

    get filteredConversations() {
        let list = this.props.conversations;
        const f = this.props.filter;
        if (f === "unread") {
            list = list.filter(c => c.state === "new");
        } else if (f === "ai") {
            list = list.filter(c => c.state === "ai_handled");
        } else if (f === "human") {
            list = list.filter(c => c.state === "human_takeover");
        }
        const q = (this.props.searchQuery || "").toLowerCase();
        if (q) {
            list = list.filter(c =>
                (c.display_name || "").toLowerCase().includes(q) ||
                (c.phone || "").includes(q)
            );
        }
        return list;
    }

    avatarColor(id) { return avatarColor(id); }
    avatarInitial(name) { return avatarInitial(name); }
    timeAgo(d) { return timeAgo(d); }
    truncate(t, l) { return truncate(t, l); }
}


// ══════════════════════════════════════════════════════════════════
// CHAT VIEW (message thread)
// ══════════════════════════════════════════════════════════════════

class ChatView extends Component {
    static template = "whatsapp_ai_integration.ChatView";
    static props = {
        conversation: { type: [Object, { value: null }], optional: true },
        messages: { type: Array },
        sending: { type: Boolean },
        onSend: { type: Function },
        onToggleInfo: { type: Function },
        onTakeover: { type: Function },
        onResumeAi: { type: Function },
    };

    setup() {
        this.state = useState({ text: "" });
        this.messagesRef = useRef("messagesContainer");

        onMounted(() => this.scrollToBottom());
    }

    scrollToBottom() {
        const el = this.messagesRef.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }

    get groupedMessages() {
        const groups = [];
        let lastDate = null;
        for (const msg of this.props.messages) {
            const dateStr = formatDate(msg.create_date);
            if (dateStr !== lastDate) {
                groups.push({ type: "date", label: dateStr });
                lastDate = dateStr;
            }
            groups.push({ type: "message", data: msg });
        }
        return groups;
    }

    getBubbleClass(msg) {
        let cls = "wa-bubble ";
        if (msg.direction === "incoming") {
            cls += "incoming";
        } else if (msg.is_chatbot) {
            cls += "ai-reply";
        } else {
            cls += "outgoing";
        }
        return cls;
    }

    getStatusIcon(msg) {
        if (msg.direction === "incoming") return "";
        switch (msg.state) {
            case "sent": return "fa-check";
            case "delivered": return "fa-check delivered";
            case "read": return "fa-check read";
            case "failed": return "fa-exclamation-circle";
            default: return "fa-clock-o";
        }
    }

    formatTime(d) { return formatTime(d); }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    sendMessage() {
        const text = this.state.text.trim();
        if (!text) return;
        this.props.onSend(text);
        this.state.text = "";
        setTimeout(() => this.scrollToBottom(), 100);
    }
}


// ══════════════════════════════════════════════════════════════════
// INFO PANEL (right sidebar contact details)
// ══════════════════════════════════════════════════════════════════

class InfoPanel extends Component {
    static template = "whatsapp_ai_integration.InfoPanel";
    static props = {
        conversation: { type: Object },
        partner: { type: [Object, { value: null }], optional: true },
        onClose: { type: Function },
        onOpenInOdoo: { type: Function },
        onTakeover: { type: Function },
        onResumeAi: { type: Function },
        onCloseConversation: { type: Function },
    };

    avatarColor(id) { return avatarColor(id); }
    avatarInitial(name) { return avatarInitial(name); }
}


// ══════════════════════════════════════════════════════════════════
// DASHBOARD VIEW (KPIs + activity)
// ══════════════════════════════════════════════════════════════════

class DashboardView extends Component {
    static template = "whatsapp_ai_integration.DashboardView";
    static props = {
        stats: { type: Object },
        recentConversations: { type: Array },
        recentMessages: { type: Array },
        onOpenConversation: { type: Function },
        onNavigate: { type: Function },
    };

    avatarColor(id) { return avatarColor(id); }
    avatarInitial(name) { return avatarInitial(name); }
    timeAgo(d) { return timeAgo(d); }
    truncate(t, l) { return truncate(t, l); }
}


// ══════════════════════════════════════════════════════════════════
// MAIN APP COMPONENT
// ══════════════════════════════════════════════════════════════════

export class WhatsAppApp extends Component {
    static template = "whatsapp_ai_integration.App";
    static components = { ConversationList, ChatView, InfoPanel, DashboardView };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            view: "chat",          // "chat" | "dashboard"
            loading: true,
            conversations: [],
            selectedConvId: null,
            messages: [],
            filter: "all",
            searchQuery: "",
            showInfo: false,
            sending: false,
            partner: null,
            stats: {
                total_conversations: 0,
                active_conversations: 0,
                ai_handled: 0,
                human_takeover: 0,
                messages_today: 0,
                messages_week: 0,
                failed_messages: 0,
                total_messages: 0,
            },
            recentConversations: [],
            recentMessages: [],
        });

        onWillStart(async () => {
            await this.loadConversations();
            await this.loadDashboardStats();
            this.state.loading = false;
        });

        // Poll for new messages every 10 seconds
        this._pollInterval = null;
        onMounted(() => {
            this._pollInterval = setInterval(() => this.pollUpdates(), 10000);
        });
    }

    willUnmount() {
        if (this._pollInterval) clearInterval(this._pollInterval);
    }

    // ── Data loading ─────────────────────────────────────────────

    async loadConversations() {
        try {
            const convs = await this.orm.searchRead(
                "whatsapp.conversation",
                [],
                ["display_name", "phone", "state", "last_message_body",
                 "last_message_date", "message_count", "partner_id", "assigned_user_id"],
                { order: "last_message_date desc", limit: 100 }
            );
            this.state.conversations = convs;
        } catch (e) {
            console.error("Error loading conversations:", e);
        }
    }

    async loadMessages(convId) {
        if (!convId) {
            this.state.messages = [];
            return;
        }
        try {
            const msgs = await this.orm.searchRead(
                "whatsapp.message",
                [["conversation_id", "=", convId]],
                ["create_date", "direction", "body", "state", "is_chatbot",
                 "message_type", "phone", "wa_message_id", "error_message"],
                { order: "create_date asc", limit: 200 }
            );
            this.state.messages = msgs;
        } catch (e) {
            console.error("Error loading messages:", e);
        }
    }

    async loadPartner(partnerId) {
        if (!partnerId) {
            this.state.partner = null;
            return;
        }
        try {
            const partners = await this.orm.searchRead(
                "res.partner",
                [["id", "=", partnerId]],
                ["name", "email", "phone", "mobile", "city",
                 "country_id", "total_invoiced", "credit"],
                { limit: 1 }
            );
            this.state.partner = partners.length ? partners[0] : null;
        } catch (e) {
            this.state.partner = null;
        }
    }

    async loadDashboardStats() {
        try {
            const today = new Date().toISOString().split("T")[0];
            const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().split("T")[0];

            const [total, active, ai, human, msgToday, msgWeek, failed, totalMsg] =
                await Promise.all([
                    this.orm.searchCount("whatsapp.conversation", []),
                    this.orm.searchCount("whatsapp.conversation", [["state", "in", ["active", "ai_handled", "new"]]]),
                    this.orm.searchCount("whatsapp.conversation", [["state", "=", "ai_handled"]]),
                    this.orm.searchCount("whatsapp.conversation", [["state", "=", "human_takeover"]]),
                    this.orm.searchCount("whatsapp.message", [["create_date", ">=", today]]),
                    this.orm.searchCount("whatsapp.message", [["create_date", ">=", weekAgo]]),
                    this.orm.searchCount("whatsapp.message", [["state", "=", "failed"]]),
                    this.orm.searchCount("whatsapp.message", []),
                ]);

            this.state.stats = {
                total_conversations: total,
                active_conversations: active,
                ai_handled: ai,
                human_takeover: human,
                messages_today: msgToday,
                messages_week: msgWeek,
                failed_messages: failed,
                total_messages: totalMsg,
            };

            const recentConvs = await this.orm.searchRead(
                "whatsapp.conversation",
                [["state", "!=", "closed"]],
                ["display_name", "phone", "state", "last_message_body", "last_message_date", "message_count"],
                { limit: 6, order: "last_message_date desc" }
            );
            this.state.recentConversations = recentConvs;

            const recentMsgs = await this.orm.searchRead(
                "whatsapp.message",
                [],
                ["create_date", "phone", "direction", "body", "state", "is_chatbot"],
                { limit: 8, order: "create_date desc" }
            );
            this.state.recentMessages = recentMsgs;
        } catch (e) {
            console.error("Dashboard stats error:", e);
        }
    }

    async pollUpdates() {
        await this.loadConversations();
        if (this.state.selectedConvId) {
            await this.loadMessages(this.state.selectedConvId);
        }
    }

    // ── UI handlers ──────────────────────────────────────────────

    get selectedConversation() {
        return this.state.conversations.find(c => c.id === this.state.selectedConvId) || null;
    }

    setView(view) {
        this.state.view = view;
        if (view === "dashboard") {
            this.loadDashboardStats();
        }
    }

    async selectConversation(convId) {
        this.state.selectedConvId = convId;
        this.state.showInfo = false;
        await this.loadMessages(convId);
        const conv = this.selectedConversation;
        if (conv && conv.partner_id) {
            await this.loadPartner(conv.partner_id[0]);
        } else {
            this.state.partner = null;
        }
    }

    setFilter(f) {
        this.state.filter = f;
    }

    setSearchQuery(q) {
        this.state.searchQuery = q;
    }

    toggleInfo() {
        this.state.showInfo = !this.state.showInfo;
    }

    async sendMessage(text) {
        const conv = this.selectedConversation;
        if (!conv || !text) return;

        this.state.sending = true;
        try {
            await this.orm.call(
                "whatsapp.conversation",
                "send_whatsapp_reply",
                [[conv.id], text]
            );
            await this.loadMessages(conv.id);
            await this.loadConversations();
            this.notification.add("Message sent", { type: "success" });
        } catch (e) {
            this.notification.add("Failed to send: " + (e.message || "Unknown error"), { type: "danger" });
        }
        this.state.sending = false;
    }

    async takeoverConversation() {
        const conv = this.selectedConversation;
        if (!conv) return;
        await this.orm.call("whatsapp.conversation", "action_human_takeover", [[conv.id]]);
        await this.loadConversations();
        this.notification.add("You are now handling this conversation", { type: "info" });
    }

    async resumeAi() {
        const conv = this.selectedConversation;
        if (!conv) return;
        await this.orm.call("whatsapp.conversation", "action_resume_ai", [[conv.id]]);
        await this.loadConversations();
        this.notification.add("AI chatbot resumed", { type: "info" });
    }

    async closeConversation() {
        const conv = this.selectedConversation;
        if (!conv) return;
        await this.orm.call("whatsapp.conversation", "action_close", [[conv.id]]);
        this.state.selectedConvId = null;
        this.state.messages = [];
        await this.loadConversations();
    }

    openInOdoo() {
        const conv = this.selectedConversation;
        if (!conv) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "whatsapp.conversation",
            res_id: conv.id,
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

    openConversationFromDashboard(convId) {
        this.state.view = "chat";
        this.selectConversation(convId);
    }

    navigateFromDashboard(target) {
        if (target === "conversations") {
            this.state.view = "chat";
        } else if (target === "failed") {
            this.action.doAction("whatsapp_ai_integration.action_whatsapp_message_failed");
        }
    }

    get activeConvCount() {
        return this.state.conversations.filter(
            c => c.state === "new"
        ).length;
    }

    get humanCount() {
        return this.state.conversations.filter(
            c => c.state === "human_takeover"
        ).length;
    }
}

WhatsAppApp.template = "whatsapp_ai_integration.App";

// Register as a client action
registry.category("actions").add("whatsapp_ai_dashboard", WhatsAppApp);
