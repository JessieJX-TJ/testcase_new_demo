class SkillsPlatform {
    constructor() {
        this.skills = [];
        this.marketplace = [];
        this.selected = null;
        this.init();
    }

    init() {
        document.getElementById("reloadBtn").addEventListener("click", () => this.loadSkills(true));
        document.getElementById("skillFilter").addEventListener("input", () => this.renderSkills());
        document.getElementById("skillForm").addEventListener("submit", event => this.createSkill(event));
        document.getElementById("fillTemplateBtn").addEventListener("click", () => this.fillTemplate());
        document.getElementById("searchBtn").addEventListener("click", () => this.searchMarketplace());
        document.getElementById("marketQuery").addEventListener("keydown", event => {
            if (event.key === "Enter") this.searchMarketplace();
        });
        document.getElementById("runSkillBtn").addEventListener("click", () => this.runSelectedSkill());
        this.loadSkills(false);
        this.searchMarketplace();
    }

    async loadSkills(reload) {
        if (reload) await fetch("/api/skills/reload", { method: "POST" });
        const result = await (await fetch("/api/skills")).json();
        this.skills = result.success ? result.data : [];
        this.renderMetrics();
        this.renderSkills();
        if (this.selected && !this.skills.some(skill => skill.name === this.selected.name)) {
            this.selected = null;
            this.renderSelection();
        }
    }

    renderMetrics() {
        const isCustom = skill => String(skill.source_dir || "").includes("\\custom\\") || String(skill.source_dir || "").includes("/custom/");
        document.getElementById("skillTotal").textContent = this.skills.length;
        document.getElementById("builtinTotal").textContent = this.skills.filter(skill => !isCustom(skill)).length;
        document.getElementById("customTotal").textContent = this.skills.filter(isCustom).length;
    }

    renderSkills() {
        const query = document.getElementById("skillFilter").value.toLowerCase();
        const list = this.skills.filter(skill => !query || skill.name.toLowerCase().includes(query) || (skill.description || "").toLowerCase().includes(query));
        document.getElementById("skillList").innerHTML = list.map(skill => `
            <button class="skill-card ${this.selected?.name === skill.name ? "active" : ""}" data-name="${this.escape(skill.name)}">
                <strong>${this.escape(skill.name)}</strong>
                <span>${this.escape(skill.description || "No description")}</span>
                <em>${this.escape(skill.type)} · ${skill.enabled ? "enabled" : "disabled"} · ${this.escape(skill.source || "builtin")}</em>
            </button>
        `).join("");
        document.querySelectorAll(".skill-card").forEach(card => {
            card.addEventListener("click", () => this.selectSkill(card.dataset.name));
        });
    }

    selectSkill(name) {
        this.selected = this.skills.find(skill => skill.name === name);
        this.renderSelection();
        this.renderSkills();
    }

    renderSelection() {
        document.getElementById("selectedName").textContent = this.selected ? this.selected.name : "None selected";
        document.getElementById("skillDetail").textContent = this.selected ? JSON.stringify(this.selected, null, 2) : "Select a skill on the left to view details.";
        document.getElementById("runSkillBtn").disabled = !this.selected;
    }

    async createSkill(event) {
        event.preventDefault();
        const payload = {
            name: document.getElementById("skillName").value,
            description: document.getElementById("skillDescription").value,
            prompt: document.getElementById("skillPrompt").value,
            model: "Qwen3-4B"
        };
        const result = await (await fetch("/api/skills", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })).json();
        if (!result.success) {
            alert(`Save failed: ${result.error}`);
            return;
        }
        event.target.reset();
        await this.loadSkills(false);
        this.selectSkill(result.data.name);
    }

    fillTemplate() {
        document.getElementById("skillName").value = "custom.requirement_boundary_cases";
        document.getElementById("skillDescription").value = "Generate boundary-value and exception-scenario test cases from a requirement";
        document.getElementById("skillPrompt").value = `You are an automotive test engineer.
Generate boundary-value and exception-scenario test cases from the following requirement:
{{ requirement }}

Output format:
Test Item:
Preconditions:
Actions:
Expected Behavior:
Pass Criteria:

Output only the test cases, with no explanation.`;
    }

    async searchMarketplace() {
        const query = document.getElementById("marketQuery").value;
        const list = document.getElementById("marketList");
        list.innerHTML = '<div class="empty">Connecting to external skill sources...</div>';
        const result = await (await fetch("/api/skills/search-online", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query })
        })).json();
        if (!result.success) {
            list.innerHTML = `<div class="empty">Search failed: ${this.escape(result.error)}</div>`;
            return;
        }
        this.marketplace = result.data || [];
        if (!this.marketplace.length) {
            list.innerHTML = '<div class="empty">No importable skills found.</div>';
            return;
        }
        list.innerHTML = this.marketplace.map((item, index) => `
            <article class="market-card">
                <strong>${this.escape(item.name)}</strong>
                <p>${this.escape(item.description || "No description")}</p>
                <span>Source: ${this.escape(item.source || "marketplace")} · ${this.escape(item.model || "Qwen3-4B")}</span>
                <div class="market-actions">
                    <button type="button" data-market-index="${index}" ${item.importable ? "" : "disabled"}>Import locally</button>
                    ${item.url ? `<a href="${this.escape(item.url)}" target="_blank" rel="noreferrer">Open source</a>` : ""}
                </div>
            </article>
        `).join("");
        document.querySelectorAll("[data-market-index]").forEach(button => {
            button.addEventListener("click", () => this.importMarketplace(Number(button.dataset.marketIndex)));
        });
    }

    async importMarketplace(index) {
        const item = this.marketplace[index];
        if (!item) return;
        const result = await (await fetch("/api/skills/import-online", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(item)
        })).json();
        if (!result.success) {
            alert(`Import failed: ${result.error}`);
            return;
        }
        await this.loadSkills(false);
        this.selectSkill(result.data.name);
    }

    async runSelectedSkill() {
        if (!this.selected) return;
        const output = document.getElementById("runOutput");
        let payload;
        try {
            payload = JSON.parse(document.getElementById("runInput").value || "{}");
        } catch (error) {
            output.textContent = `Invalid input JSON: ${error.message}`;
            return;
        }
        output.textContent = "Running skill...";
        const result = await (await fetch(`/api/skills/${encodeURIComponent(this.selected.name)}/run`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })).json();
        output.textContent = result.success ? JSON.stringify(result.data, null, 2) : `Run failed: ${result.error}`;
    }

    escape(value) {
        return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
    }
}

window.addEventListener("DOMContentLoaded", () => new SkillsPlatform());
