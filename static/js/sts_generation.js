class STSGenerationApp {
    constructor() {
        this.documentId = null;
        this.sections = [];
        this.units = [];
        this.clusters = [];
        this.reviewStatus = "pending";
        this.init();
    }

    init() {
        document.getElementById("uploadBtn").addEventListener("click", () => this.uploadPdf());
        document.getElementById("useUrlBtn").addEventListener("click", () => this.registerUrl());
        document.getElementById("parseBtn").addEventListener("click", () => this.parsePdf());
        document.getElementById("generateBtn").addEventListener("click", () => this.generateCases());
        document.getElementById("refreshReviewBtn").addEventListener("click", () => this.loadReviewCases());
        document.querySelectorAll(".review-tab").forEach(btn => {
            btn.addEventListener("click", () => {
                this.reviewStatus = btn.dataset.status;
                document.querySelectorAll(".review-tab").forEach(item => item.classList.toggle("active", item === btn));
                this.loadReviewCases();
            });
        });
        this.loadReviewCases();
    }

    log(message) {
        const box = document.getElementById("logBox");
        box.textContent += `${new Date().toLocaleTimeString()}  ${message}\n`;
        box.scrollTop = box.scrollHeight;
    }

    async uploadPdf() {
        const file = document.getElementById("pdfFile").files[0];
        if (!file) {
            this.log("Please select a PDF file first.");
            return;
        }
        const formData = new FormData();
        formData.append("file", file);
        this.log("Uploading PDF...");
        const result = await this.postForm("/api/sts/upload", formData);
        if (!result.success) {
            this.log(`Upload failed: ${result.error}`);
            return;
        }
        this.documentId = result.data.document_id;
        document.getElementById("docStatus").textContent = `Uploaded: ${result.data.filename}`;
        document.getElementById("parseBtn").disabled = false;
        this.log(`Upload complete: ${this.documentId}`);
    }

    async registerUrl() {
        const url = document.getElementById("pdfUrl").value.trim();
        if (!url) {
            this.log("Please enter a PDF URL first.");
            return;
        }
        this.log("Registering PDF URL...");
        const result = await this.postJson("/api/sts/register-url", { url });
        if (!result.success) {
            this.log(`URL registration failed: ${result.error}`);
            return;
        }
        this.documentId = result.data.document_id;
        document.getElementById("docStatus").textContent = `URL registered: ${result.data.filename}`;
        document.getElementById("parseBtn").disabled = false;
        this.log(`URL registered: ${this.documentId}`);
    }

    async parsePdf() {
        if (!this.documentId) return;
        this.log("Calling MinerU to parse and extract sections, requirement units, signals, and topics...");
        const result = await this.postJson(`/api/sts/parse/${this.documentId}`, {});
        if (!result.success) {
            this.log(`Parse failed: ${result.error}`);
            return;
        }
        this.sections = result.data.sections || [];
        this.units = result.data.requirement_units || [];
        this.clusters = result.data.topic_clusters || [];
        document.getElementById("docStatus").textContent = "Parsed";
        document.getElementById("generateBtn").disabled = this.clusters.length === 0 && this.sections.length === 0;
        this.renderSummary(result.data);
        this.renderTopics();
        this.renderEvidence();
        this.log(`Parse complete: ${this.sections.length} sections, ${this.units.length} requirement units, ${this.clusters.length} topics.`);
    }

    renderSummary(data) {
        document.getElementById("sectionCount").textContent = (data.sections || []).length;
        document.getElementById("unitCount").textContent = (data.requirement_units || []).length;
        document.getElementById("signalCount").textContent = (data.signals || []).length;
        document.getElementById("clusterCount").textContent = (data.topic_clusters || []).length;
    }

    renderTopics() {
        const container = document.getElementById("topicsList");
        if (!this.clusters.length) {
            container.innerHTML = '<div class="empty">No topic clusters parsed.</div>';
            return;
        }
        container.innerHTML = this.clusters.map((cluster, index) => {
            const checked = this.shouldSelectCluster(cluster);
            return `
            <label class="topic-card ${index === 0 ? "active" : ""}" data-id="${this.escape(cluster.cluster_id)}">
                <div class="topic-head">
                    <input type="checkbox" class="cluster-check" value="${this.escape(cluster.cluster_id)}" ${checked ? "checked" : ""}>
                    <div>
                        <strong>${this.escape(cluster.topic || "Untitled topic")}</strong>
                        <p>${this.escape(cluster.summary || "")}</p>
                    </div>
                    <span class="quality ${this.escape(cluster.source_quality || "medium")}">${this.qualityLabel(cluster.source_quality)}</span>
                </div>
                <div class="topic-meta">
                    <span>${cluster.unit_count || 0} requirement units</span>
                    <span>${cluster.section_count || 0} sections</span>
                    <span>Pages ${cluster.page_start || "-"} - ${cluster.page_end || "-"}</span>
                </div>
                <div class="keywords">${(cluster.keywords || []).slice(0, 8).map(k => `<span>${this.escape(k)}</span>`).join("")}</div>
            </label>
        `}).join("");
        container.querySelectorAll(".topic-card").forEach(card => {
            card.addEventListener("click", event => {
                if (event.target.tagName.toLowerCase() === "input") return;
                container.querySelectorAll(".topic-card").forEach(item => item.classList.remove("active"));
                card.classList.add("active");
                this.renderEvidence(card.dataset.id);
            });
        });
    }

    renderEvidence(clusterId = null) {
        const cluster = this.clusters.find(item => item.cluster_id === clusterId) || this.clusters[0];
        const container = document.getElementById("evidenceList");
        if (!cluster) {
            container.innerHTML = '<div class="empty">No evidence yet.</div>';
            return;
        }
        const units = cluster.requirement_units || [];
        container.innerHTML = `
            <div class="evidence-header">
                <strong>${this.escape(cluster.topic)}</strong>
                <span>${(cluster.test_intents || []).map(item => this.escape(item)).join(" / ") || "No coverage intent identified"}</span>
            </div>
            <h3>Requirement Units</h3>
            ${units.length ? units.slice(0, 12).map(unit => `
                <article class="evidence-card">
                    <strong>${this.escape(unit.unit_id || "")} ${this.escape(unit.function || "")}</strong>
                    <p><b>Preconditions:</b> ${this.escape(unit.preconditions || "Not specified")}</p>
                    <p><b>Triggers:</b> ${this.escape(unit.triggers || "Not specified")}</p>
                    <p><b>Expected:</b> ${this.escape(unit.expected_results || unit.hmi_display || unit.status_feedback || "Not specified")}</p>
                </article>
            `).join("") : '<div class="empty small">This topic has no structured requirement units; generation will fall back to section summaries.</div>'}
            <h3>Related Sections</h3>
            ${(cluster.sections || []).map(section => `
                <article class="evidence-card section">
                    <strong>${this.escape(section.section_id)} ${this.escape(section.title)}</strong>
                    <p>${this.escape(section.content_preview || "")}</p>
                </article>
            `).join("")}
        `;
    }

    async generateCases() {
        if (!this.documentId) return;
        const clusterIds = Array.from(document.querySelectorAll(".cluster-check:checked")).map(item => item.value);
        if (!clusterIds.length) {
            this.log("Please select at least one topic.");
            return;
        }
        this.log(`Generating test cases from ${clusterIds.length} topics...`);
        const result = await this.postJson(`/api/sts/generate-cases/${this.documentId}`, { cluster_ids: clusterIds });
        if (!result.success) {
            this.log(`Generation failed: ${result.error}`);
            return;
        }
        this.log(`Generation complete: ${result.data.generated_cases.length} cases entered the Pending Review library.`);
        this.reviewStatus = "pending";
        this.loadReviewCases();
    }

    async loadReviewCases() {
        const result = await (await fetch(`/api/review/test-cases?status=${this.reviewStatus}`)).json();
        const cases = result.success ? result.data : [];
        const container = document.getElementById("casesList");
        if (!cases.length) {
            container.innerHTML = '<div class="empty">No cases yet</div>';
            return;
        }
        container.innerHTML = cases.map(item => `
            <article class="case-item">
                <div class="case-title">
                    <strong>${this.escape(item.topic || item.section_title || "STS Test Case")}</strong>
                    <span>${this.escape(item.generation_granularity || "")}</span>
                </div>
                <div class="case-meta">Case ID: ${this.escape(item.case_id)} · Section ${this.escape(item.section_id || "-")} · Pages ${item.page_start || "-"} - ${item.page_end || "-"}</div>
                <pre>${this.escape(item.testcase || "")}</pre>
                ${this.reviewStatus === "pending" ? `
                <div class="case-actions">
                    <button class="accept" data-id="${this.escape(item.case_id)}" data-decision="accepted">Accept</button>
                    <button class="reject" data-id="${this.escape(item.case_id)}" data-decision="rejected">Reject</button>
                </div>` : ""}
            </article>
        `).join("");
        container.querySelectorAll("button[data-decision]").forEach(btn => {
            btn.addEventListener("click", () => this.reviewCase(btn.dataset.id, btn.dataset.decision));
        });
    }

    async reviewCase(caseId, decision) {
        const result = await this.postJson(`/api/review/test-cases/${caseId}`, { decision });
        this.log(result.success ? `${decision === "accepted" ? "Accepted" : "Rejected"}: ${caseId}` : `Review failed: ${result.error}`);
        this.loadReviewCases();
    }

    async postJson(url, payload) {
        const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        return res.json();
    }

    async postForm(url, formData) {
        const res = await fetch(url, { method: "POST", body: formData });
        return res.json();
    }

    qualityLabel(value) {
        return { high: "High quality", medium: "Medium quality", low: "Low quality" }[value] || "Medium quality";
    }

    shouldSelectCluster(cluster) {
        const unitCount = Number(cluster.unit_count || 0);
        return cluster.source_quality === "high" && unitCount > 0 && unitCount <= 12;
    }

    escape(value) {
        return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
    }
}

window.addEventListener("DOMContentLoaded", () => new STSGenerationApp());
