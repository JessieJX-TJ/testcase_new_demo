class FaultDiagnosisApp {
    constructor() {
        this.form = document.getElementById("diagnosisForm");
        this.input = document.getElementById("problemInput");
        this.submit = document.getElementById("submitBtn");
        this.evidence = [];
        this.bind();
        if (window.lucide) window.lucide.createIcons();
    }

    bind() {
        this.form.addEventListener("submit", event => {
            event.preventDefault();
            this.diagnose();
        });
        this.input.addEventListener("input", () => {
            document.getElementById("characterCount").textContent = `${this.input.value.length} / 2000`;
        });
    }

    reset() {
        this.evidence = [];
        document.getElementById("resultSection").hidden = true;
        document.getElementById("errorSection").hidden = true;
        document.getElementById("progressSection").hidden = false;
        document.getElementById("progressLog").innerHTML = "";
        document.getElementById("progressCurrent").textContent = "Preparing analysis";
        this.submit.disabled = true;
        this.submit.querySelector("span").textContent = "Analyzing";
    }

    addProgress(message) {
        const text = String(message || "").trim();
        if (!text) return;
        document.getElementById("progressCurrent").textContent = text;
        const item = document.createElement("li");
        item.textContent = text;
        document.getElementById("progressLog").appendChild(item);
    }

    async diagnose() {
        const problem = this.input.value.trim();
        if (!problem) {
            this.showError("Please enter a fault symptom.");
            this.input.focus();
            return;
        }
        this.reset();
        try {
            const response = await fetch("/api/fault-diagnosis/stream", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ problem }),
            });
            if (!response.ok || !response.body) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.error || "Fault diagnosis API returned an unexpected response");
            }
            await this.readEvents(response.body);
        } catch (error) {
            this.showError(error.message || "Fault diagnosis failed");
        } finally {
            document.getElementById("progressSection").hidden = true;
            this.submit.disabled = false;
            this.submit.querySelector("span").textContent = "Start Analysis";
        }
    }

    async readEvents(body) {
        const reader = body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) this.handleEvent(line);
        }
        if (buffer.trim()) this.handleEvent(buffer);
    }

    handleEvent(line) {
        if (!line.trim()) return;
        const event = JSON.parse(line);
        if (event.type === "thought") this.addProgress(event.message);
        if (event.type === "evidence") {
            this.evidence = event.data || [];
            this.renderEvidence(this.evidence);
        }
        if (event.type === "result") this.renderResult(event.data || {});
        if (event.type === "error") throw new Error(event.message || "Fault diagnosis failed");
    }

    renderResult(data) {
        this.evidence = data.evidence || this.evidence;
        document.getElementById("summaryText").textContent = data.summary || "Fault cause analysis completed";
        document.getElementById("causeCount").textContent = (data.causes || []).length;
        document.getElementById("evidenceCount").textContent = this.evidence.length;
        document.getElementById("elapsedTime").textContent = Number(data.elapsed_time || 0).toFixed(1);
        document.getElementById("evidenceWarning").hidden = !data.insufficient_evidence;
        this.renderCauses(data.causes || []);
        this.renderEvidence(this.evidence);
        this.renderNextSteps(data.next_steps || []);
        document.getElementById("resultSection").hidden = false;
        document.getElementById("resultSection").scrollIntoView({ behavior: "smooth", block: "start" });
        if (window.lucide) window.lucide.createIcons();
    }

    renderCauses(causes) {
        const labels = { high: "High", medium: "Medium", low: "Low" };
        document.getElementById("causeList").innerHTML = causes.map((cause, index) => {
            const likelihood = ["high", "medium", "low"].includes(cause.likelihood) ? cause.likelihood : "low";
            const checks = (cause.checks || []).map(item => `<li>${this.escape(item)}</li>`).join("");
            const refs = (cause.evidence_ids || []).map(id =>
                `<button class="evidence-ref" type="button" data-evidence-id="${this.escape(id)}">${this.escape(id)}</button>`
            ).join("");
            return `<article class="cause-card">
                <header class="cause-head">
                    <span class="cause-index">${String(index + 1).padStart(2, "0")}</span>
                    <h3>${this.escape(cause.title)}</h3>
                    <span class="likelihood ${likelihood}">${labels[likelihood]}</span>
                </header>
                <div class="cause-body">
                    <p>${this.escape(cause.reasoning)}</p>
                    ${checks ? `<ol class="checks">${checks}</ol>` : ""}
                    ${refs ? `<div class="evidence-refs">${refs}</div>` : '<span class="hypothesis">Hypothesis to verify</span>'}
                </div>
            </article>`;
        }).join("");
        document.querySelectorAll(".evidence-ref").forEach(button => {
            button.addEventListener("click", () => this.focusEvidence(button.dataset.evidenceId));
        });
    }

    renderEvidence(evidence) {
        const pdfCount = evidence.filter(item => item.source_type === "pdf_kg").length;
        const caseCount = evidence.length - pdfCount;
        document.getElementById("evidenceSourceSummary").textContent = `${caseCount} cases · ${pdfCount} specs`;
        const list = document.getElementById("evidenceList");
        if (!evidence.length) {
            list.innerHTML = '<div class="empty-evidence">No citable evidence found</div>';
            return;
        }
        list.innerHTML = evidence.map(item => {
            const type = item.source_type === "pdf_kg" ? "PDF Spec" : "Test Case";
            const row = item.source_row !== undefined ? `<span>Row ${this.escape(item.source_row)}</span>` : "";
            const score = item.score !== undefined ? `<span>Relevance ${this.escape(item.score)}</span>` : "";
            return `<article class="evidence-item" id="evidence-${this.escape(item.id)}">
                <div class="evidence-item-head"><span class="evidence-id">${this.escape(item.id)}</span><span class="evidence-type">${type}</span></div>
                <p class="evidence-statement">${this.escape(item.statement)}</p>
                <div class="evidence-meta"><span>${this.escape(item.source_name || "Current product line")}</span>${row}${score}</div>
            </article>`;
        }).join("");
    }

    renderNextSteps(steps) {
        document.getElementById("nextStepsSection").hidden = !steps.length;
        document.getElementById("nextStepsList").innerHTML = steps.map(item => `<li>${this.escape(item)}</li>`).join("");
    }

    focusEvidence(id) {
        const target = document.getElementById(`evidence-${id}`);
        if (!target) return;
        document.querySelectorAll(".evidence-item.is-target").forEach(item => item.classList.remove("is-target"));
        target.classList.add("is-target");
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        window.setTimeout(() => target.classList.remove("is-target"), 1800);
    }

    showError(message) {
        document.getElementById("errorMessage").textContent = message;
        document.getElementById("errorSection").hidden = false;
        if (window.lucide) window.lucide.createIcons();
    }

    escape(value) {
        return String(value ?? "").replace(/[&<>"']/g, character => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        })[character]);
    }
}

window.addEventListener("DOMContentLoaded", () => new FaultDiagnosisApp());
