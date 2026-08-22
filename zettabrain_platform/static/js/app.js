"use strict";

(function () {
    // State
    let currentUser = null;
    let teams = [];
    let skills = [];

    // DOM refs
    const screens = {
        login: document.getElementById("login-screen"),
        changePw: document.getElementById("change-pw-screen"),
        app: document.getElementById("app-screen"),
    };
    const tabs = document.querySelectorAll("#main-tabs .tab");
    const panels = document.querySelectorAll(".panel");

    // ─── Navigation ───────────────────────────────────────────────────────
    function showScreen(name) {
        Object.values(screens).forEach((s) => s.classList.remove("active"));
        screens[name].classList.add("active");
    }

    function switchTab(tabName) {
        tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === tabName));
        panels.forEach((p) => p.classList.toggle("active", p.id === `panel-${tabName}`));

        if (tabName === "documents") loadDocuments();
        if (tabName === "skills") loadSkills();
        if (tabName === "admin") loadAdmin();
    }

    tabs.forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));

    // ─── Auth ─────────────────────────────────────────────────────────────
    document.getElementById("login-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const errEl = document.getElementById("login-error");
        errEl.textContent = "";

        const username = document.getElementById("login-username").value.trim();
        const password = document.getElementById("login-password").value;

        try {
            const data = await API.login(username, password);
            API.setToken(data.access_token);

            if (data.must_change_password) {
                showScreen("changePw");
            } else {
                await initApp();
            }
        } catch (err) {
            errEl.textContent = err.message;
        }
    });

    document.getElementById("change-pw-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const errEl = document.getElementById("change-pw-error");
        errEl.textContent = "";

        const pw = document.getElementById("new-password").value;
        const confirm = document.getElementById("confirm-password").value;

        if (pw !== confirm) {
            errEl.textContent = "Passwords do not match";
            return;
        }

        try {
            await API.changePassword(pw);
            await initApp();
        } catch (err) {
            errEl.textContent = err.message;
        }
    });

    document.getElementById("logout-btn").addEventListener("click", () => {
        API.setToken(null);
        currentUser = null;
        showScreen("login");
    });

    window.addEventListener("zbp:session-expired", () => {
        currentUser = null;
        showScreen("login");
        document.getElementById("login-error").textContent = "Session expired. Please login again.";
    });

    // ─── Init App ─────────────────────────────────────────────────────────
    async function initApp() {
        try {
            currentUser = await API.getMe();
        } catch {
            showScreen("login");
            return;
        }

        document.getElementById("user-display").textContent = currentUser.username;
        const adminTab = document.getElementById("admin-tab");
        adminTab.style.display = currentUser.system_role === "admin" ? "" : "none";

        showScreen("app");
        await loadTeams();
        switchTab("chat");
    }

    // ─── Teams ────────────────────────────────────────────────────────────
    async function loadTeams() {
        try {
            teams = await API.getTeams();
        } catch {
            teams = [];
        }
        populateTeamSelects();
    }

    function populateTeamSelects() {
        const selects = ["chat-team-select", "gen-team-select", "docs-team-filter", "ingest-team-select"];
        selects.forEach((id) => {
            const el = document.getElementById(id);
            const isFilter = id === "docs-team-filter";
            el.innerHTML = isFilter ? '<option value="">All Teams</option>' : "";
            teams.forEach((t) => {
                el.innerHTML += `<option value="${t.id}">${t.name}</option>`;
            });
        });
    }

    // ─── Chat ─────────────────────────────────────────────────────────────
    const chatMessages = document.getElementById("chat-messages");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const question = chatInput.value.trim();
        const teamId = document.getElementById("chat-team-select").value;
        if (!question || !teamId) return;

        appendMessage("user", question);
        chatInput.value = "";

        const loadingEl = appendMessage("assistant", '<span class="loading"></span>');

        try {
            const result = await API.chat(parseInt(teamId), question);
            loadingEl.querySelector(".msg-bubble").innerHTML = escapeHtml(result.answer);

            let meta = `${result.duration_ms}ms | ${result.chunks} chunks | ${(result.confidence * 100).toFixed(0)}% confidence`;
            loadingEl.querySelector(".msg-meta").textContent = meta;

            if (result.sources && result.sources.length > 0) {
                const sourcesHtml = result.sources.map((s) => `<span>${escapeHtml(s)}</span>`).join("");
                loadingEl.querySelector(".msg-bubble").innerHTML +=
                    `<div class="msg-sources">${sourcesHtml}</div>`;
            }
        } catch (err) {
            loadingEl.querySelector(".msg-bubble").innerHTML =
                `<span style="color:var(--error)">${escapeHtml(err.message)}</span>`;
        }
    });

    function appendMessage(role, content) {
        const emptyEl = chatMessages.querySelector(".chat-empty");
        if (emptyEl) emptyEl.remove();

        const div = document.createElement("div");
        div.className = `msg msg-${role}`;
        div.innerHTML = `<div class="msg-bubble">${role === "user" ? escapeHtml(content) : content}</div><div class="msg-meta"></div>`;
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return div;
    }

    // ─── Generate ─────────────────────────────────────────────────────────
    const genSkillSelect = document.getElementById("gen-skill-select");
    const genSkillInfo = document.getElementById("gen-skill-info");
    const genSubmit = document.getElementById("gen-submit");
    const genOutput = document.getElementById("gen-output");

    document.getElementById("gen-team-select").addEventListener("change", loadSkillsForGen);

    genSkillSelect.addEventListener("change", () => {
        const skill = skills.find((s) => s.file === genSkillSelect.value);
        if (skill) {
            genSkillInfo.innerHTML = `<strong>${skill.display_name}</strong> — ${escapeHtml(skill.description || "")}`;
            genSkillInfo.style.display = "";
        } else {
            genSkillInfo.style.display = "none";
        }
    });

    async function loadSkillsForGen() {
        try {
            skills = await API.getSkills();
            genSkillSelect.innerHTML = '<option value="">Select a skill...</option>';
            skills.forEach((s) => {
                genSkillSelect.innerHTML += `<option value="${s.file}">${s.display_name}</option>`;
            });
        } catch {
            genSkillSelect.innerHTML = '<option value="">No skills available</option>';
        }
    }

    genSubmit.addEventListener("click", async () => {
        const teamId = document.getElementById("gen-team-select").value;
        const skillFile = genSkillSelect.value;
        const inputText = document.getElementById("gen-input").value.trim();

        if (!teamId || !skillFile || !inputText) {
            genOutput.innerHTML = '<div class="gen-output-placeholder" style="color:var(--warning)">Please select a team, skill, and provide input text.</div>';
            return;
        }

        genSubmit.disabled = true;
        genOutput.innerHTML = '<div class="gen-output-placeholder"><span class="loading"></span> Generating...</div>';

        try {
            const result = await API.generate({
                team_id: parseInt(teamId),
                skill_file: skillFile,
                input_text: inputText,
                customer_name: document.getElementById("gen-customer-name").value,
                customer_email: document.getElementById("gen-customer-email").value,
                customer_phone: document.getElementById("gen-customer-phone").value,
            });

            genOutput.innerHTML = `<div class="gen-output-content">${escapeHtml(result.content)}</div>
                <div style="margin-top:1rem;font-size:0.75rem;color:var(--text-muted)">
                    Generated in ${result.generation_time_ms}ms | ID: ${result.id}
                </div>`;
        } catch (err) {
            genOutput.innerHTML = `<div class="gen-output-placeholder" style="color:var(--error)">${escapeHtml(err.message)}</div>`;
        } finally {
            genSubmit.disabled = false;
        }
    });

    // ─── Documents ────────────────────────────────────────────────────────
    const docsList = document.getElementById("docs-list");
    const docsFilter = document.getElementById("docs-team-filter");

    docsFilter.addEventListener("change", loadDocuments);

    async function loadDocuments() {
        const teamId = docsFilter.value;
        try {
            const docs = await API.getDocuments(teamId || null);
            if (!docs || docs.length === 0) {
                docsList.innerHTML = '<p class="empty-state">No documents generated yet.</p>';
                return;
            }
            docsList.innerHTML = docs
                .map(
                    (d) => `<div class="doc-card" data-id="${d.id}">
                    <div class="doc-card-header">
                        <span class="doc-card-title">${escapeHtml(d.skill_display)}</span>
                        <span class="doc-card-date">${formatDate(d.created_at)}</span>
                    </div>
                    <div class="doc-card-meta">
                        ${escapeHtml(d.customer_name || "")} | ${escapeHtml(d.request)}
                    </div>
                </div>`
                )
                .join("");

            docsList.querySelectorAll(".doc-card").forEach((card) => {
                card.addEventListener("click", () => openDocument(card.dataset.id));
            });
        } catch (err) {
            docsList.innerHTML = `<p class="empty-state" style="color:var(--error)">${escapeHtml(err.message)}</p>`;
        }
    }

    async function openDocument(docId) {
        const modal = document.getElementById("doc-modal");
        const title = document.getElementById("doc-modal-title");
        const body = document.getElementById("doc-modal-body");

        title.textContent = "Loading...";
        body.textContent = "";
        modal.classList.remove("hidden");

        try {
            const doc = await API.getDocument(docId);
            title.textContent = doc.skill_display;
            body.innerHTML = `<div style="margin-bottom:1rem;font-size:0.8rem;color:var(--text-secondary)">
                Customer: ${escapeHtml(doc.customer_name || "N/A")} |
                Generated: ${formatDate(doc.created_at)} |
                Time: ${doc.generation_time_ms}ms
            </div>${escapeHtml(doc.content)}`;
        } catch (err) {
            title.textContent = "Error";
            body.textContent = err.message;
        }
    }

    document.querySelector(".modal-close").addEventListener("click", () => {
        document.getElementById("doc-modal").classList.add("hidden");
    });
    document.querySelector(".modal-backdrop").addEventListener("click", () => {
        document.getElementById("doc-modal").classList.add("hidden");
    });

    // ─── Skills ───────────────────────────────────────────────────────────
    const skillsGrid = document.getElementById("skills-grid");

    async function loadSkills() {
        try {
            const data = await API.getSkills();
            if (!data || data.length === 0) {
                skillsGrid.innerHTML = '<p class="empty-state">No skills configured. Add .md skill files to the skills directory.</p>';
                return;
            }
            skillsGrid.innerHTML = data
                .map(
                    (s) => `<div class="skill-card">
                    <h4>${escapeHtml(s.display_name)}</h4>
                    <p>${escapeHtml(s.description || "No description")}</p>
                    <div>
                        ${s.business_type ? `<span class="badge">${escapeHtml(s.business_type)}</span>` : ""}
                        <span class="badge">v${s.version || "1"}</span>
                        ${s.requires_corpus ? '<span class="badge">Corpus</span>' : ""}
                        ${s.citation_required ? '<span class="badge">Citations</span>' : ""}
                    </div>
                    ${s.variables && s.variables.length ? `<div style="margin-top:0.5rem;font-size:0.7rem;color:var(--text-muted)">Variables: ${s.variables.join(", ")}</div>` : ""}
                </div>`
                )
                .join("");
        } catch (err) {
            skillsGrid.innerHTML = `<p class="empty-state" style="color:var(--error)">${escapeHtml(err.message)}</p>`;
        }
    }

    // ─── Admin ────────────────────────────────────────────────────────────
    async function loadAdmin() {
        if (currentUser.system_role !== "admin") return;
        await Promise.all([loadAdminSettings(), loadAdminHealth(), loadAdminTeams()]);
    }

    async function loadAdminSettings() {
        const container = document.getElementById("admin-provider-form");
        try {
            const settings = await API.getSettings();
            const keys = [
                "llm_provider", "llm_model", "generation_provider", "generation_model",
                "groq_api_key", "groq_model",
                "together_api_key", "together_model",
                "cerebras_api_key", "cerebras_model",
                "openrouter_api_key", "openrouter_model",
                "ollama_host", "embed_provider", "embed_model",
                "openai_api_key", "anthropic_api_key",
            ];

            container.innerHTML = keys
                .map(
                    (k) => `<div class="form-group">
                    <label>${k.replace(/_/g, " ")}</label>
                    <input type="${k.includes("key") || k.includes("password") ? "password" : "text"}"
                           data-key="${k}" value="${escapeHtml(settings[k] || "")}" class="admin-setting">
                </div>`
                )
                .join("");

            container.innerHTML += '<div style="grid-column: 1/-1; margin-top:0.5rem;"><button id="save-settings" class="btn btn-primary btn-sm">Save Settings</button></div>';

            document.getElementById("save-settings").addEventListener("click", async () => {
                const updates = {};
                container.querySelectorAll(".admin-setting").forEach((input) => {
                    updates[input.dataset.key] = input.value;
                });
                try {
                    await API.updateSettings(updates);
                    alert("Settings saved.");
                } catch (err) {
                    alert("Error: " + err.message);
                }
            });
        } catch (err) {
            container.innerHTML = `<p style="color:var(--error)">${escapeHtml(err.message)}</p>`;
        }
    }

    async function loadAdminHealth() {
        const container = document.getElementById("admin-health");
        try {
            const health = await API.getHealth();
            let html = "";

            html += `<div class="health-card"><div class="label">Ollama</div><div class="status ${health.ollama.ok ? "ok" : "fail"}">${health.ollama.ok ? "Connected" : "Offline"}</div></div>`;
            html += `<div class="health-card"><div class="label">OpenAI</div><div class="status ${health.openai.ok ? "ok" : "fail"}">${health.openai.ok ? "Connected" : "Not configured"}</div></div>`;
            html += `<div class="health-card"><div class="label">Claude</div><div class="status ${health.claude.ok ? "ok" : "fail"}">${health.claude.ok ? "Connected" : "Not configured"}</div></div>`;

            if (health.cloud_providers) {
                Object.entries(health.cloud_providers).forEach(([name, info]) => {
                    const label = name.charAt(0).toUpperCase() + name.slice(1);
                    html += `<div class="health-card"><div class="label">${label}</div><div class="status ${info.ok ? "ok" : "fail"}">${info.ok ? "Connected" : info.key_set ? "Key set (unverified)" : "Not configured"}</div></div>`;
                });
            }

            if (health.teams) {
                health.teams.forEach((t) => {
                    html += `<div class="health-card"><div class="label">${escapeHtml(t.team_name)}</div><div class="status">${t.vector_docs} docs indexed</div></div>`;
                });
            }

            container.innerHTML = html;
        } catch (err) {
            container.innerHTML = `<p style="color:var(--error)">${escapeHtml(err.message)}</p>`;
        }
    }

    async function loadAdminTeams() {
        const container = document.getElementById("admin-teams");
        container.innerHTML = teams
            .map((t) => `<div style="padding:0.4rem 0;font-size:0.85rem;border-bottom:1px solid var(--border)"><strong>${escapeHtml(t.name)}</strong> <span style="color:var(--text-muted)">(${t.slug})</span></div>`)
            .join("");
    }

    document.getElementById("admin-create-team").addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("new-team-name").value.trim();
        const desc = document.getElementById("new-team-desc").value.trim();
        if (!name) return;

        try {
            await API.createTeam(name, desc);
            document.getElementById("new-team-name").value = "";
            document.getElementById("new-team-desc").value = "";
            await loadTeams();
            loadAdminTeams();
        } catch (err) {
            alert("Error: " + err.message);
        }
    });

    // ─── Ingestion ────────────────────────────────────────────────────────
    document.getElementById("admin-ingest-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const teamId = document.getElementById("ingest-team-select").value;
        const files = document.getElementById("ingest-file").files;
        const statusEl = document.getElementById("ingest-status");

        if (!teamId || !files.length) {
            statusEl.textContent = "Select a team and at least one file.";
            return;
        }

        statusEl.textContent = "Uploading and processing...";

        try {
            const result = await API.ingest(parseInt(teamId), files);
            statusEl.textContent = `Done! ${result.ingested || result.documents_ingested || 0} document(s) ingested.`;
            statusEl.style.color = "var(--success)";
            document.getElementById("ingest-file").value = "";
        } catch (err) {
            statusEl.textContent = "Error: " + err.message;
            statusEl.style.color = "var(--error)";
        }
    });

    // ─── Helpers ──────────────────────────────────────────────────────────
    function escapeHtml(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function formatDate(iso) {
        if (!iso) return "";
        const d = new Date(iso);
        return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    // ─── Boot ─────────────────────────────────────────────────────────────
    if (API.getToken()) {
        initApp();
    } else {
        showScreen("login");
    }
})();
