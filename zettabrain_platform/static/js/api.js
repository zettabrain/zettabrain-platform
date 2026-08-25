"use strict";

const API = {
    _token: null,
    _baseUrl: "",

    setToken(token) {
        this._token = token;
        if (token) {
            sessionStorage.setItem("zbp_token", token);
        } else {
            sessionStorage.removeItem("zbp_token");
        }
    },

    getToken() {
        if (!this._token) {
            this._token = sessionStorage.getItem("zbp_token");
        }
        return this._token;
    },

    async _fetch(path, opts = {}) {
        const headers = { "Content-Type": "application/json", ...opts.headers };
        const token = this.getToken();
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const res = await fetch(this._baseUrl + path, { ...opts, headers });

        if (res.status === 401) {
            this.setToken(null);
            window.dispatchEvent(new CustomEvent("zbp:session-expired"));
            throw new Error("Session expired");
        }
        if (res.status === 429) {
            const detail = (await res.json().catch(() => ({}))).detail || "Rate limited";
            throw new Error(detail);
        }
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(body.detail || `HTTP ${res.status}`);
        }
        if (res.status === 204) return null;
        return res.json();
    },

    // Auth
    async login(username, password) {
        const body = new URLSearchParams({ username, password });
        const res = await fetch("/api/auth/token", { method: "POST", body });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || "Login failed");
        }
        return res.json();
    },

    async getMe() {
        return this._fetch("/api/auth/me");
    },

    async changePassword(newPassword) {
        return this._fetch("/api/auth/change-password", {
            method: "POST",
            body: JSON.stringify({ new_password: newPassword }),
        });
    },

    // Teams
    async getTeams() {
        return this._fetch("/api/teams/");
    },

    async createTeam(name, description) {
        return this._fetch("/api/teams/", {
            method: "POST",
            body: JSON.stringify({ name, description }),
        });
    },

    // Chat
    async chat(teamId, question) {
        return this._fetch("/api/chat/", {
            method: "POST",
            body: JSON.stringify({ team_id: teamId, question }),
        });
    },

    // Generate
    async getSkills() {
        return this._fetch("/api/generate/skills");
    },

    async generate(body) {
        return this._fetch("/api/generate/", {
            method: "POST",
            body: JSON.stringify(body),
        });
    },

    // Documents
    async getDocuments(teamId) {
        const query = teamId ? `?team_id=${teamId}` : "";
        return this._fetch(`/api/generate/documents${query}`);
    },

    async getDocument(docId) {
        return this._fetch(`/api/generate/documents/${docId}`);
    },

    // Admin
    async getSettings() {
        return this._fetch("/api/admin/settings");
    },

    async updateSettings(settings) {
        return this._fetch("/api/admin/settings", {
            method: "PUT",
            body: JSON.stringify(settings),
        });
    },

    async getHealth() {
        return this._fetch("/api/admin/health");
    },

    // Ingestion (file upload)
    async ingest(teamId, files) {
        const token = this.getToken();
        const formData = new FormData();
        formData.append("team_id", teamId.toString());
        for (const file of files) {
            formData.append("files", file);
        }
        const res = await fetch("/api/ingest/upload", {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: formData,
        });
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(body.detail || "Ingestion failed");
        }
        return res.json();
    },
};
