/* VerdictBox frontend helpers for form submissions and lightweight counters. */

async function postForm(url, formDataObj) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formDataObj)
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || "Request failed");
    }
    return data;
}

function formatRelativeTime(value) {
    const stamp = new Date(value);
    if (Number.isNaN(stamp.getTime())) return "";
    const diffMs = Date.now() - stamp.getTime();
    const seconds = Math.max(1, Math.floor(diffMs / 1000));
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    if (days > 0) return `${days} day${days === 1 ? "" : "s"} ago`;
    if (hours > 0) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
    if (minutes > 0) return `${minutes} min ago`;
    return `${seconds} sec ago`;
}

function _getToastStack() {
    let stack = document.getElementById("globalToastStack");
    if (stack) return stack;

    stack = document.createElement("div");
    stack.id = "globalToastStack";
    stack.className = "toast-container position-fixed top-0 end-0 p-3 vb-toast-stack";
    stack.setAttribute("aria-live", "polite");
    stack.setAttribute("aria-atomic", "true");
    document.body.appendChild(stack);
    return stack;
}

function _showToast(title, message, variant = "dark") {
    if (typeof bootstrap === "undefined") return;
    const stack = _getToastStack();

    const node = document.createElement("div");
    node.className = `toast align-items-center border-0 vb-toast vb-toast-${variant}`;
    node.setAttribute("role", "alert");
    node.setAttribute("aria-live", "assertive");
    node.setAttribute("aria-atomic", "true");
    node.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <div class="vb-toast-title">${title}</div>
                <div class="vb-toast-text">${message}</div>
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    stack.appendChild(node);
    const toast = new bootstrap.Toast(node, { delay: 3400 });
    node.addEventListener("hidden.bs.toast", () => node.remove());
    toast.show();
}

function _queueBadgeNotifications(unlockedBadges) {
    if (!Array.isArray(unlockedBadges) || !unlockedBadges.length) return;
    const raw = window.sessionStorage.getItem("vb.pending.badges");
    const existing = raw ? JSON.parse(raw) : [];
    const merged = Array.isArray(existing) ? existing.concat(unlockedBadges) : unlockedBadges;
    window.sessionStorage.setItem("vb.pending.badges", JSON.stringify(merged));
}

function showUnlockedBadgeNotifications(unlockedBadges, persistForNextPage = false) {
    if (!Array.isArray(unlockedBadges) || !unlockedBadges.length) return false;

    const seen = new Set();
    const deduped = unlockedBadges.filter((badge) => {
        const name = badge?.name || "Badge";
        if (seen.has(name)) return false;
        seen.add(name);
        return true;
    });

    deduped.forEach((badge, index) => {
        const name = badge?.name || "Badge";
        const description = badge?.description || "New achievement unlocked.";
        window.setTimeout(() => {
            _showToast("Badge Unlocked", `${name} - ${description}`, "badge");
        }, index * 260);
    });

    if (persistForNextPage) {
        _queueBadgeNotifications(deduped);
    }
    return deduped.length > 0;
}

function flushQueuedBadgeNotifications() {
    const raw = window.sessionStorage.getItem("vb.pending.badges");
    if (!raw) return;

    let queued = [];
    try {
        queued = JSON.parse(raw) || [];
    } catch (_err) {
        queued = [];
    }
    window.sessionStorage.removeItem("vb.pending.badges");
    showUnlockedBadgeNotifications(queued, false);
}

function setupDescriptionCounter() {
    const field = document.getElementById("descriptionField");
    const count = document.getElementById("descriptionCount");
    if (!field || !count) return;
    field.addEventListener("input", () => {
        count.textContent = String(field.value.length);
    });
}

function setupStatCounters() {
    const nodes = document.querySelectorAll(".stat-number[data-target]");
    if (!nodes.length) return;

    nodes.forEach((node) => {
        const rawTarget = Number(node.getAttribute("data-target") || 0);
        const target = Number.isFinite(rawTarget) ? rawTarget : 0;
        const durationMs = 900;
        const steps = 30;
        const increment = target / steps;
        let current = 0;
        let tick = 0;

        const interval = window.setInterval(() => {
            tick += 1;
            current += increment;
            if (tick >= steps) {
                node.textContent = String(target);
                window.clearInterval(interval);
                return;
            }
            node.textContent = String(Math.round(current));
        }, durationMs / steps);
    });
}

function setupGeneralCounters() {
    const counters = document.querySelectorAll(".stat-counter[data-target]");
    counters.forEach((node) => {
        const rawTarget = Number(node.getAttribute("data-target") || 0);
        const target = Number.isFinite(rawTarget) ? rawTarget : 0;
        const steps = 28;
        const increment = target / steps;
        let current = 0;
        let tick = 0;
        const timer = window.setInterval(() => {
            tick += 1;
            current += increment;
            if (tick >= steps) {
                node.textContent = String(target);
                window.clearInterval(timer);
                return;
            }
            node.textContent = String(Math.round(current));
        }, 26);
    });
}

function setupDashboardDonut() {
    const canvas = document.getElementById("winLossDonut");
    if (!canvas || typeof Chart === "undefined") return;
    const wins = Number(canvas.getAttribute("data-wins") || 0);
    const losses = Number(canvas.getAttribute("data-losses") || 0);
    const winRate = Number(canvas.getAttribute("data-win-rate") || 0);

    const centerTextPlugin = {
        id: "centerTextPlugin",
        afterDraw(chart) {
            const { ctx } = chart;
            const x = chart.getDatasetMeta(0).data[0]?.x;
            const y = chart.getDatasetMeta(0).data[0]?.y;
            if (!Number.isFinite(x) || !Number.isFinite(y)) return;

            ctx.save();
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillStyle = "#d8e5ff";
            ctx.font = "700 24px Space Grotesk";
            ctx.fillText(`${Math.max(0, Math.min(100, winRate))}%`, x, y - 6);
            ctx.fillStyle = "#8b8fa8";
            ctx.font = "500 11px Inter";
            ctx.fillText("Win Rate", x, y + 14);
            ctx.restore();
        },
    };

    new Chart(canvas, {
        type: "doughnut",
        data: {
            labels: ["Wins", "Losses"],
            datasets: [{
                data: [wins, losses],
                backgroundColor: ["#39ffbc", "#d45a66"],
                borderColor: ["#1a1d27", "#1a1d27"],
                borderWidth: 2,
            }],
        },
        options: {
            plugins: {
                legend: { labels: { color: "#eaeaea" } },
            },
            cutout: "68%",
        },
        plugins: [centerTextPlugin],
    });
}

function setupLeaderboardChart() {
    const dataNode = document.getElementById("leaderboardData");
    const canvas = document.getElementById("leaderboardChart");
    if (!dataNode || !canvas || typeof Chart === "undefined") return;

    const rows = JSON.parse(dataNode.textContent || "[]");
    const labels = rows.map((r) => r.username);
    const wins = rows.map((r) => r.wins);
    const maxWins = wins.length ? Math.max(...wins) : 0;

    const valueLabelPlugin = {
        id: "valueLabelPlugin",
        afterDatasetsDraw(chart) {
            const { ctx } = chart;
            const meta = chart.getDatasetMeta(0);
            ctx.save();
            ctx.fillStyle = "#cfd5f3";
            ctx.font = "12px Inter";
            meta.data.forEach((bar, index) => {
                const value = wins[index] || 0;
                const textY = bar.y + 4;
                const textX = bar.x + 8;
                ctx.fillText(`${value} Wins`, textX, textY);
            });
            ctx.restore();
        },
    };

    new Chart(canvas, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "Wins",
                data: wins,
                backgroundColor: "#6c63ff",
                borderRadius: 8,
                barThickness: 12,
                maxBarThickness: 14,
                categoryPercentage: 0.72,
                barPercentage: 0.85,
            }],
        },
        options: {
            indexAxis: "y",
            maintainAspectRatio: false,
            layout: { padding: { right: 64 } },
            scales: {
                x: {
                    ticks: {
                        color: "#8b8fa8",
                        precision: 0,
                        stepSize: 1,
                    },
                    grid: { color: "#2a2d3a" },
                    suggestedMax: maxWins + 1,
                },
                y: { ticks: { color: "#eaeaea" }, grid: { color: "#2a2d3a" } },
            },
            plugins: { legend: { display: false } },
        },
        plugins: [valueLabelPlugin],
    });
}

function setupStatisticsCharts() {
    const dataNode = document.getElementById("statisticsData");
    if (!dataNode || typeof Chart === "undefined") return;
    const stats = JSON.parse(dataNode.textContent || "{}");

    const lineCanvas = document.getElementById("activityLineChart");
    if (lineCanvas) {
        new Chart(lineCanvas, {
            type: "line",
            data: {
                labels: stats.activity_labels || [],
                datasets: [{
                    label: "Disputes",
                    data: stats.activity_counts || [],
                    borderColor: "#00d4aa",
                    backgroundColor: "rgba(0, 212, 170, 0.2)",
                    tension: 0.35,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    pointBackgroundColor: "#7cf4dd",
                    pointBorderColor: "#0f1117",
                    pointBorderWidth: 1,
                    fill: true,
                }],
            },
            options: {
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: "#eaeaea" } } },
                scales: {
                    x: { ticks: { color: "#8b8fa8" }, grid: { color: "#2a2d3a" } },
                    y: { ticks: { color: "#8b8fa8" }, grid: { color: "#2a2d3a" } },
                },
            },
        });
    }

    const barCanvas = document.getElementById("fallacyBarChart");
    if (barCanvas) {
        const fullLabels = stats.fallacy_full_labels || [];
        const rawLabels = stats.fallacy_labels || [];
        const axisLabels = rawLabels.map((label) => {
            const text = String(label || "");
            return text.length > 18 ? `${text.slice(0, 15)}...` : text;
        });

        new Chart(barCanvas, {
            type: "bar",
            data: {
                labels: axisLabels,
                datasets: [{
                    label: "Count",
                    data: stats.fallacy_counts || [],
                    backgroundColor: "#ffb347",
                    borderRadius: 8,
                    barThickness: 14,
                    maxBarThickness: 18,
                    categoryPercentage: 0.68,
                    barPercentage: 0.9,
                }],
            },
            options: {
                indexAxis: "y",
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title(items) {
                                const idx = items[0]?.dataIndex ?? 0;
                                return rawLabels[idx] || axisLabels[idx] || "Fallacy";
                            },
                            label(item) {
                                const idx = item.dataIndex;
                                const detail = fullLabels[idx] || rawLabels[idx] || "No details";
                                const count = item.raw;
                                return [`Count: ${count}`, `Detail: ${detail}`];
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            color: "#8b8fa8",
                            precision: 0,
                            stepSize: 1,
                        },
                        grid: { color: "#2a2d3a" },
                    },
                    y: {
                        ticks: { color: "#8b8fa8" },
                        grid: { color: "#2a2d3a" },
                    },
                },
            },
        });
    }
}

function setupTooltips() {
    if (typeof bootstrap === "undefined") return;
    document.querySelectorAll("[data-bs-toggle='tooltip']").forEach((node) => {
        new bootstrap.Tooltip(node);
    });
}

function setupDataDrivenWidths() {
    document.querySelectorAll("[data-pct]").forEach((node) => {
        const pct = Number(node.getAttribute("data-pct") || 0);
        const clamped = Math.max(0, Math.min(100, pct));
        node.style.width = `${clamped}%`;
    });
}

function setupAgreementCounter() {
    const hero = document.getElementById("agreementHero");
    const value = document.querySelector(".agreement-value[data-target]");
    if (!hero || !value) return;

    let done = false;
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting || done) return;
            done = true;
            const rawTarget = Number(value.getAttribute("data-target") || 0);
            const target = Number.isFinite(rawTarget) ? rawTarget : 0;
            let cur = 0;
            let ticks = 0;
            const maxTicks = 120;
            const timer = window.setInterval(() => {
                ticks += 1;
                cur += 2;
                if (cur >= target || ticks >= maxTicks) {
                    value.textContent = String(target);
                    window.clearInterval(timer);
                    return;
                }
                value.textContent = String(cur);
            }, 24);
        });
    }, { threshold: 0.45 });

    observer.observe(hero);
}

function setupTypewriterSuggestion() {
    const node = document.getElementById("typedSuggestion");
    if (!node) return;

    const text = node.getAttribute("data-text") || "";
    if (!text) return;

    const panel = document.getElementById("couldHaveWonPanel");
    if (!panel) {
        node.textContent = text;
        return;
    }

    panel.addEventListener("shown.bs.collapse", () => {
        if (node.getAttribute("data-typed") === "done") return;
        let idx = 0;
        node.textContent = "";
        const timer = window.setInterval(() => {
            node.textContent += text[idx] || "";
            idx += 1;
            if (idx >= text.length) {
                node.setAttribute("data-typed", "done");
                window.clearInterval(timer);
            }
        }, 18);
    });
}

function setupWordCounter() {
    const field = document.getElementById("argumentText");
    const count = document.getElementById("wordCount");
    if (!field || !count) return;
    field.addEventListener("input", () => {
        const words = field.value.trim() ? field.value.trim().split(/\s+/).length : 0;
        count.textContent = String(words);
    });
}

function setupAuthForms() {
    const registerForm = document.getElementById("registerForm");
    if (registerForm) {
        registerForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const payload = {
                    username: registerForm.username.value,
                    email: registerForm.email.value,
                    password: registerForm.password.value
                };
                const roleField = registerForm.querySelector("[name='role']");
                if (roleField && roleField.value) {
                    payload.role = roleField.value;
                }
                await postForm("/register", payload);
                alert("Registered successfully. Please login.");
                window.location.href = "/login";
            } catch (err) {
                alert(err.message);
            }
        });
    }

    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const data = await postForm("/login", {
                    username: loginForm.username.value,
                    password: loginForm.password.value
                });
                window.location.href = data.redirect_url || "/disputes";
            } catch (err) {
                alert(err.message);
            }
        });
    }
}

function setupRoleSwitchForms() {
    const forms = Array.from(document.querySelectorAll("[data-role-switch-form]"));
    if (!forms.length) return;

    forms.forEach((form) => {
        const roleField = form.querySelector("input[name='role']");
        const buttons = Array.from(form.querySelectorAll("[data-role-value]"));
        if (!roleField || !buttons.length) return;

        buttons.forEach((button) => {
            button.addEventListener("click", async () => {
                const requestedRole = button.getAttribute("data-role-value") || "";
                const currentRole = roleField.value || "";
                if (!requestedRole || requestedRole === currentRole) return;

                buttons.forEach((node) => {
                    node.disabled = true;
                });

                try {
                    const data = await postForm("/account/switch-role", {
                        role: requestedRole
                    });
                    _showToast("Role Updated", `Current role: ${data.role || requestedRole}`, "badge");
                    window.setTimeout(() => window.location.reload(), 450);
                } catch (err) {
                    alert(err.message);
                    buttons.forEach((node) => {
                        node.disabled = false;
                    });
                }
            });
        });
    });
}

function setupDisputeForms() {
    const createForm = document.getElementById("createDisputeForm");
    if (createForm) {
        createForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const data = await postForm("/dispute/create", {
                    title: createForm.title.value,
                    description: createForm.description.value,
                    opponent_username: createForm.opponent_username.value,
                    moderation_mode: createForm.moderation_mode.value
                });
                const hasBadgeUnlock = showUnlockedBadgeNotifications(data.unlocked_badges || [], true);
                const redirectDelay = hasBadgeUnlock ? 1200 : 100;
                window.setTimeout(() => {
                    window.location.href = "/dashboard";
                }, redirectDelay);
            } catch (err) {
                alert(err.message);
            }
        });
    }

    const submitForm = document.getElementById("submitArgumentForm");
    if (submitForm) {
        const submitCard = document.getElementById("submitArgumentCard");
        const reviewPanel = document.getElementById("caseReviewPanel");
        const reviewMessage = document.getElementById("reviewStatusMessage");
        const stepNodes = reviewPanel ? Array.from(reviewPanel.querySelectorAll(".review-step")) : [];

        const markStepState = (index, state) => {
            if (!stepNodes[index]) return;
            const node = stepNodes[index];
            node.classList.remove("is-pending", "is-active", "is-done");
            node.classList.add(state);
            const icon = node.querySelector(".review-step-icon");
            if (!icon) return;
            if (state === "is-done") icon.textContent = "✅";
            else if (state === "is-active") icon.textContent = "⏳";
            else icon.textContent = "•";
        };

        const runReviewAnimation = () => {
            if (!stepNodes.length) return { stop() {} };
            markStepState(0, "is-done");
            let idx = 1;
            let timer = null;

            const advance = () => {
                for (let i = 1; i < stepNodes.length; i += 1) {
                    if (i === idx) markStepState(i, "is-active");
                    else if (i < idx) markStepState(i, "is-done");
                    else markStepState(i, "is-pending");
                }
                idx += 1;
                if (idx > stepNodes.length) {
                    idx = 1;
                }
            };

            advance();
            timer = window.setInterval(advance, 1300);
            return {
                stop(finalDone = false) {
                    if (timer) window.clearInterval(timer);
                    if (finalDone) {
                        stepNodes.forEach((_, i) => markStepState(i, "is-done"));
                    }
                },
            };
        };

        submitForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (submitForm.getAttribute("data-submitting") === "1") return;
            const disputeId = submitForm.getAttribute("data-dispute-id");
            submitForm.setAttribute("data-submitting", "1");

            const submitBtn = submitForm.querySelector("button[type='submit']");
            if (submitBtn) submitBtn.disabled = true;

            if (submitCard) submitCard.classList.add("d-none");
            if (reviewPanel) reviewPanel.classList.remove("d-none");

            if (reviewMessage) {
                reviewMessage.classList.remove("alert-danger", "alert-success");
                reviewMessage.classList.add("alert-info");
                reviewMessage.textContent = "Processing in progress. Please wait...";
            }

            const reviewAnimator = runReviewAnimation();
            try {
                const data = await postForm(`/dispute/${disputeId}/submit`, {
                    argument_text: submitForm.argument_text.value
                });

                const hasBadgeUnlock = showUnlockedBadgeNotifications(data.unlocked_badges || [], true);

                if (data && data.verdict) {
                    reviewAnimator.stop(true);
                    if (reviewMessage) {
                        reviewMessage.classList.remove("alert-info");
                        reviewMessage.classList.add("alert-success");
                        reviewMessage.textContent = "Judgment complete. Opening verdict...";
                    }
                    window.setTimeout(() => {
                        window.location.href = `/dispute/${disputeId}/verdict`;
                    }, hasBadgeUnlock ? 1300 : 650);
                    return;
                }

                if (data && data.status === "flagged") {
                    reviewAnimator.stop(true);
                    if (reviewMessage) {
                        reviewMessage.classList.remove("alert-info");
                        reviewMessage.classList.add("alert-danger");
                        reviewMessage.textContent = "Case flagged for toxicity review by admin.";
                    }
                    window.setTimeout(() => window.location.reload(), 1400);
                    return;
                }

                reviewAnimator.stop();
                if (reviewMessage) {
                    reviewMessage.classList.remove("alert-danger", "alert-success");
                    reviewMessage.classList.add("alert-info");
                    reviewMessage.textContent = "Submission confirmed. Waiting for the other disputant...";
                }
            } catch (err) {
                reviewAnimator.stop();
                if (reviewPanel) reviewPanel.classList.add("d-none");
                if (submitCard) submitCard.classList.remove("d-none");
                submitForm.setAttribute("data-submitting", "0");
                if (submitBtn) submitBtn.disabled = false;
                alert(err.message);
            }
        });
    }
}

function setupDisputeLiveState() {
    const node = document.getElementById("disputeLiveState");
    if (!node) return;

    const disputeId = node.getAttribute("data-dispute-id");
    const initialCount = Number(node.getAttribute("data-submissions-count") || 0);
    const initialStatus = (node.getAttribute("data-status") || "").trim().toLowerCase();
    if (!disputeId) return;

    // Poll state so users immediately see side-by-side arguments when opponent submits.
    window.setInterval(async () => {
        try {
            const response = await fetch(`/dispute/${disputeId}/state`);
            if (!response.ok) return;
            const state = await response.json();

            const status = String(state.status || "").toLowerCase();
            const count = Number(state.submissions_count || 0);
            if (status === "resolved" && state.verdict_url) {
                window.location.href = state.verdict_url;
                return;
            }

            const statusChanged = status && status !== initialStatus;
            const newSubmissionArrived = Number.isFinite(count) && count > initialCount;
            if (statusChanged || newSubmissionArrived) {
                window.location.reload();
            }
        } catch (_err) {
            // Keep UX stable if polling fails temporarily.
        }
    }, 3000);
}

function setupVoteAndAppeal() {
    const voteForm = document.getElementById("voteForm");
    if (voteForm) {
        voteForm.querySelectorAll("button[name='voted_for_user_id']").forEach((btn) => {
            btn.addEventListener("click", async (e) => {
                e.preventDefault();
                const disputeId = voteForm.getAttribute("data-dispute-id");
                try {
                        const data = await postForm(`/dispute/${disputeId}/vote`, {
                        voted_for_user_id: btn.value
                    });
                        const hasBadgeUnlock = showUnlockedBadgeNotifications(data.unlocked_badges || [], true);
                        window.setTimeout(() => window.location.reload(), hasBadgeUnlock ? 1100 : 100);
                } catch (err) {
                    alert(err.message);
                }
            });
        });
    }

    const appealForm = document.getElementById("appealForm");
    if (appealForm) {
        appealForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const disputeId = appealForm.getAttribute("data-dispute-id");
            try {
                const data = await postForm(`/dispute/${disputeId}/appeal`, {
                    reason_text: appealForm.reason_text.value
                });
                showUnlockedBadgeNotifications(data.unlocked_badges || [], false);
                alert("Appeal submitted.");
                appealForm.reset();
            } catch (err) {
                alert(err.message);
            }
        });
    }
}

function setupCommentForm() {
    const form = document.getElementById("commentForm");
    if (!form) return;

    const textarea = document.getElementById("commentText");
    const list = document.getElementById("commentList");
    const countBadge = document.getElementById("commentCountBadge");
    if (!textarea || !list) return;

    const escapeHtml = (value) =>
        String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");

    const toLocalTime = (isoValue) => {
        if (!isoValue) return "";
        const stamp = new Date(isoValue);
        if (Number.isNaN(stamp.getTime())) return "";
        return stamp.toLocaleString();
    };

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const disputeId = form.getAttribute("data-dispute-id");
        const body = textarea.value.trim();
        if (!body) {
            alert("Comment text is required");
            return;
        }

        const submitBtn = form.querySelector("button[type='submit']");
        if (submitBtn) submitBtn.disabled = true;

        try {
            const data = await postForm(`/dispute/${disputeId}/comments`, { body });
            const row = data.comment || {};

            const emptyState = document.getElementById("commentEmptyState");
            if (emptyState) emptyState.remove();

            const node = document.createElement("div");
            node.className = "comment-item";
            node.setAttribute("data-comment-id", String(row.id || ""));
            node.innerHTML = `
                <div class="comment-meta">
                    <strong>@${escapeHtml(row.username || "Unknown")}</strong>
                    <span class="text-muted small">${escapeHtml(toLocalTime(row.created_at))}</span>
                </div>
                <div class="comment-body">${escapeHtml(row.body || "")}</div>
            `;
            list.prepend(node);

            if (countBadge) {
                const currentCount = Number(countBadge.textContent || 0);
                const nextCount = Number.isFinite(currentCount) ? currentCount + 1 : 1;
                countBadge.textContent = String(nextCount);
            }

            textarea.value = "";
            _showToast("Comment Posted", "Your comment is now public.", "badge");
        } catch (err) {
            alert(err.message);
        } finally {
            if (submitBtn) submitBtn.disabled = false;
        }
    });
}

function setupDisputeFeedVoting() {
    const voteGroups = Array.from(document.querySelectorAll("[data-feed-vote-form]"));
    if (!voteGroups.length) return;

    voteGroups.forEach((group) => {
        const disputeId = group.getAttribute("data-dispute-id");
        if (!disputeId) return;

        const buttons = Array.from(group.querySelectorAll(".feed-vote-btn[data-value]"));
        buttons.forEach((btn) => {
            btn.addEventListener("click", async () => {
                const value = Number(btn.getAttribute("data-value") || 0);
                if (![1, -1].includes(value)) return;

                buttons.forEach((node) => {
                    node.disabled = true;
                });

                try {
                    const data = await postForm(`/dispute/${disputeId}/engagement-vote`, { value });
                    const upNode = document.getElementById(`feedUp${disputeId}`);
                    const downNode = document.getElementById(`feedDown${disputeId}`);
                    const scoreNode = document.getElementById(`feedScore${disputeId}`);
                    if (upNode) upNode.textContent = String(data.upvotes || 0);
                    if (downNode) downNode.textContent = String(data.downvotes || 0);
                    if (scoreNode) scoreNode.textContent = String(data.score || 0);

                    buttons.forEach((node) => {
                        const nodeValue = Number(node.getAttribute("data-value") || 0);
                        node.classList.remove("btn-success", "btn-outline-success", "btn-danger", "btn-outline-danger");
                        if (nodeValue === 1) {
                            node.classList.add(data.user_vote === 1 ? "btn-success" : "btn-outline-success");
                        } else if (nodeValue === -1) {
                            node.classList.add(data.user_vote === -1 ? "btn-danger" : "btn-outline-danger");
                        }
                    });
                } catch (err) {
                    alert(err.message);
                } finally {
                    buttons.forEach((node) => {
                        node.disabled = false;
                    });
                }
            });
        });
    });
}

function setupAdminForms() {
    document.querySelectorAll(".adminReviewForm").forEach((form) => {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const disputeId = form.getAttribute("data-dispute-id");
            const formData = new FormData(form);
            const notes = String(formData.get("notes") || "");
            try {
                await postForm(`/admin/dispute/${disputeId}/review`, { notes });
                alert("Dispute reviewed.");
                window.location.reload();
            } catch (err) {
                alert(err.message);
            }
        });
    });

    document.querySelectorAll(".adminModerationForm").forEach((form) => {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const disputeId = form.getAttribute("data-dispute-id");
            const formData = new FormData(form);
            const decision = String(formData.get("decision") || "").trim();
            const notes = String(formData.get("notes") || "").trim();
            const targetUserId = String(formData.get("target_user_id") || "").trim();
            const button = form.querySelector("button[type='submit']");
            if (button) button.disabled = true;
            try {
                await postForm(`/admin/dispute/${disputeId}/moderate`, {
                    decision,
                    notes,
                    target_user_id: targetUserId,
                });
                alert("Moderation action saved.");
                window.location.reload();
            } catch (err) {
                alert(err.message);
                if (button) button.disabled = false;
            }
        });
    });

    document.querySelectorAll(".adminToggleUserForm").forEach((form) => {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const userId = form.getAttribute("data-user-id");
            const button = form.querySelector("button[type='submit']");
            if (button) button.disabled = true;
            try {
                await postForm(`/admin/users/${userId}/toggle`, {});
                alert("User status updated.");
                window.location.reload();
            } catch (err) {
                alert(err.message);
                if (button) button.disabled = false;
            }
        });
    });

}

function setupAppealModal() {
    const modal = document.getElementById("appealDecisionModal");
    if (!modal) return;

    const titleNode = document.getElementById("appealModalTitle");
    const reasonNode = document.getElementById("appealModalReason");
    const winnerNode = document.getElementById("appealModalWinner");
    const responseField = document.getElementById("appealModalResponse");
    const saveButton = document.getElementById("appealModalSave");
    const counter = modal.querySelector(".appeal-response-counter");
    const max = counter ? Number(counter.getAttribute("data-max") || 0) : 0;
    const toggleButtons = Array.from(modal.querySelectorAll(".appeal-toggle-btn"));
    let activeDecision = "approved";
    let activeAppealId = null;

    const setDecision = (value) => {
        activeDecision = value;
        toggleButtons.forEach((btn) => {
            btn.classList.toggle("is-active", btn.getAttribute("data-value") === value);
        });
    };

    const adjustHeight = () => {
        if (!responseField) return;
        responseField.style.height = "auto";
        const maxHeight = 8 * 22;
        responseField.style.height = `${Math.min(responseField.scrollHeight, maxHeight)}px`;
    };

    const updateCounter = () => {
        if (!counter || !responseField) return;
        const count = responseField.value.length;
        counter.textContent = max ? `${count}/${max}` : String(count);
    };

    const closeModal = () => {
        modal.classList.remove("is-active");
        document.body.classList.remove("admin-focus-dim");
        activeAppealId = null;
    };

    modal.querySelectorAll(".appeal-modal-close, .appeal-modal-backdrop").forEach((node) => {
        node.addEventListener("click", closeModal);
    });

    toggleButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const value = btn.getAttribute("data-value") || "approved";
            setDecision(value);
        });
    });

    if (responseField) {
        responseField.addEventListener("input", () => {
            adjustHeight();
            updateCounter();
        });
    }

    document.querySelectorAll(".appeal-modal-trigger").forEach((button) => {
        button.addEventListener("click", () => {
            activeAppealId = button.getAttribute("data-appeal-id");
            const disputeId = button.getAttribute("data-dispute-id") || "--";
            const disputeTitle = button.getAttribute("data-dispute-title") || "Unknown dispute";
            const reason = button.getAttribute("data-reason") || "";
            const winner = button.getAttribute("data-winner") || "Unknown";
            if (titleNode) titleNode.textContent = `#${disputeId} - ${disputeTitle}`;
            if (reasonNode) reasonNode.textContent = reason;
            if (winnerNode) winnerNode.textContent = winner;
            if (responseField) responseField.value = "";
            setDecision("approved");
            adjustHeight();
            updateCounter();
            modal.classList.add("is-active");
            document.body.classList.add("admin-focus-dim");
        });
    });

    if (saveButton) {
        saveButton.addEventListener("click", async () => {
            if (!activeAppealId) return;
            saveButton.disabled = true;
            try {
                await postForm(`/admin/appeal/${activeAppealId}/decide`, {
                    decision: activeDecision,
                    admin_response: responseField ? responseField.value.trim() : "",
                });
                alert("Appeal decision saved.");
                window.location.reload();
            } catch (err) {
                alert(err.message);
                saveButton.disabled = false;
            }
        });
    }
}

function setupModerationModal() {
    const modal = document.getElementById("moderationDecisionModal");
    if (!modal) return;

    const titleNode = document.getElementById("moderationModalTitle");
    const descNode = document.getElementById("moderationModalDescription");
    const reasonsNode = document.getElementById("moderationModalReasons");
    const notesField = document.getElementById("moderationNotes");
    const saveButton = document.getElementById("moderationModalSave");
    const counter = modal.querySelector(".moderation-notes-counter");
    const max = counter ? Number(counter.getAttribute("data-max") || 0) : 0;
    const toggleButtons = Array.from(modal.querySelectorAll(".moderation-toggle-btn"));
    const secondaryButtons = Array.from(modal.querySelectorAll(".moderation-secondary-btn"));
    const targetWrap = document.getElementById("moderationTargetWrap");
    const targetSelect = document.getElementById("moderationTargetSelect");
    let activeDecision = "clear";
    let activeDisputeId = null;

    const setDecision = (value) => {
        activeDecision = value;
        toggleButtons.forEach((btn) => {
            btn.classList.toggle("is-active", btn.getAttribute("data-value") === value);
        });
        secondaryButtons.forEach((btn) => {
            btn.classList.toggle("is-active", btn.getAttribute("data-value") === value);
        });
        if (targetWrap) {
            targetWrap.classList.toggle("is-visible", value === "restrict");
        }
    };

    const adjustHeight = () => {
        if (!notesField) return;
        notesField.style.height = "auto";
        const maxHeight = 9 * 22;
        notesField.style.height = `${Math.min(notesField.scrollHeight, maxHeight)}px`;
    };

    const updateCounter = () => {
        if (!counter || !notesField) return;
        const count = notesField.value.length;
        counter.textContent = max ? `${count}/${max}` : String(count);
    };

    const closeModal = () => {
        modal.classList.remove("is-active");
        document.body.classList.remove("admin-focus-dim");
        activeDisputeId = null;
    };

    modal.querySelectorAll(".moderation-modal-close, .moderation-modal-backdrop").forEach((node) => {
        node.addEventListener("click", closeModal);
    });

    toggleButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const value = btn.getAttribute("data-value") || "clear";
            setDecision(value);
        });
    });

    secondaryButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const value = btn.getAttribute("data-value") || "investigate";
            setDecision(value);
        });
    });

    modal.querySelectorAll(".admin-reason-chips .chip").forEach((chip) => {
        chip.addEventListener("click", () => {
            if (!notesField) return;
            const value = chip.getAttribute("data-fill") || "";
            const current = notesField.value.trim();
            notesField.value = current ? `${current} ${value}` : value;
            notesField.dispatchEvent(new Event("input"));
        });
    });

    if (notesField) {
        notesField.addEventListener("input", () => {
            adjustHeight();
            updateCounter();
        });
    }

    document.querySelectorAll(".moderation-modal-trigger").forEach((button) => {
        button.addEventListener("click", () => {
            activeDisputeId = button.getAttribute("data-dispute-id");
            const title = button.getAttribute("data-title") || "Unknown dispute";
            const description = button.getAttribute("data-description") || "";
            const reasons = button.getAttribute("data-report-reasons") || "";
            if (titleNode) titleNode.textContent = `#${activeDisputeId} - ${title}`;
            if (descNode) descNode.textContent = description;
            if (reasonsNode) {
                reasonsNode.innerHTML = "";
                const list = reasons.split(",").map((r) => r.trim()).filter((r) => r);
                if (list.length === 0) {
                    const empty = document.createElement("span");
                    empty.className = "tag";
                    empty.textContent = "No reports";
                    reasonsNode.appendChild(empty);
                } else {
                    list.forEach((reason) => {
                        const tag = document.createElement("span");
                        tag.className = "tag";
                        tag.textContent = reason.replace(/_/g, " ");
                        reasonsNode.appendChild(tag);
                    });
                }
            }

            if (targetSelect) {
                targetSelect.innerHTML = "";
                const defaultOpt = document.createElement("option");
                defaultOpt.value = "";
                defaultOpt.textContent = "Restrict creator by default";
                targetSelect.appendChild(defaultOpt);
                const creatorId = button.getAttribute("data-creator-id") || "";
                const creatorName = button.getAttribute("data-creator-name") || "";
                const invitedId = button.getAttribute("data-invited-id") || "";
                const invitedName = button.getAttribute("data-invited-name") || "";
                if (creatorId && creatorName) {
                    const opt = document.createElement("option");
                    opt.value = creatorId;
                    opt.textContent = `${creatorName} (creator)`;
                    targetSelect.appendChild(opt);
                }
                if (invitedId && invitedName) {
                    const opt = document.createElement("option");
                    opt.value = invitedId;
                    opt.textContent = `${invitedName} (invited)`;
                    targetSelect.appendChild(opt);
                }
            }

            if (notesField) notesField.value = "";
            setDecision("clear");
            adjustHeight();
            updateCounter();
            modal.classList.add("is-active");
            document.body.classList.add("admin-focus-dim");
        });
    });

    if (saveButton) {
        saveButton.addEventListener("click", async () => {
            if (!activeDisputeId) return;
            saveButton.disabled = true;
            try {
                await postForm(`/admin/dispute/${activeDisputeId}/moderate`, {
                    decision: activeDecision,
                    notes: notesField ? notesField.value.trim() : "",
                    target_user_id: targetSelect ? targetSelect.value : "",
                });
                alert("Moderation decision saved.");
                window.location.reload();
            } catch (err) {
                alert(err.message);
                saveButton.disabled = false;
            }
        });
    }
}

function setupAdminEnhancements() {
    document.querySelectorAll(".admin-quick-action").forEach((button) => {
        button.addEventListener("click", () => {
            const form = button.closest("form");
            if (!form) return;
            const decision = button.getAttribute("data-decision");
            const select = form.querySelector("select[name='decision']");
            if (select && decision) select.value = decision;
            const submitBtn = form.querySelector("button[type='submit']");
            if (submitBtn) submitBtn.click();
        });
    });

    document.querySelectorAll(".admin-reason-chips .chip").forEach((chip) => {
        chip.addEventListener("click", () => {
            const form = chip.closest("form");
            if (!form) return;
            const textarea = form.querySelector(".admin-notes-text");
            if (!textarea) return;
            const value = chip.getAttribute("data-fill") || "";
            const current = textarea.value.trim();
            textarea.value = current ? `${current} ${value}` : value;
            textarea.dispatchEvent(new Event("input"));
        });
    });

    document.querySelectorAll(".admin-notes-text").forEach((textarea) => {
        const form = textarea.closest("form");
        const fieldWrap = textarea.closest(".admin-notes-field");
        const overlayWrap = textarea.closest(".admin-notes-overlay") || fieldWrap;
        const counter = form ? form.querySelector(".admin-notes-counter") : null;
        const max = counter ? Number(counter.getAttribute("data-max") || 0) : 0;
        const adjustHeight = () => {
            textarea.style.height = "auto";
            const maxHeight = 6 * 22;
            const nextHeight = Math.min(textarea.scrollHeight, maxHeight);
            textarea.style.height = `${nextHeight}px`;
        };
        const update = () => {
            if (!counter) return;
            const count = textarea.value.length;
            counter.textContent = max ? `${count}/${max}` : String(count);
        };
        textarea.addEventListener("input", () => {
            adjustHeight();
            update();
        });
        textarea.addEventListener("focus", () => {
            if (fieldWrap) fieldWrap.classList.add("is-active");
            if (overlayWrap) {
                overlayWrap.classList.add("is-active");
                overlayWrap.classList.add("is-center");
            }
            document.body.classList.add("admin-focus-dim");
        });
        textarea.addEventListener("blur", () => {
            window.setTimeout(() => {
                const isStillFocused = overlayWrap && overlayWrap.contains(document.activeElement);
                if (isStillFocused) return;
                if (fieldWrap) fieldWrap.classList.remove("is-active");
                if (overlayWrap) {
                    overlayWrap.classList.remove("is-active");
                    overlayWrap.classList.remove("is-center");
                }
                document.body.classList.remove("admin-focus-dim");
            }, 80);
        });
        adjustHeight();
        update();
    });

    document.querySelectorAll(".report-toggle").forEach((button) => {
        button.addEventListener("click", () => {
            const targetId = button.getAttribute("data-target");
            if (!targetId) return;
            const list = document.getElementById(targetId);
            if (!list) return;
            const hiddenRows = list.querySelectorAll(".report-row-hidden");
            const isExpanded = button.getAttribute("data-expanded") === "true";
            const showRows = !isExpanded;
            hiddenRows.forEach((row) => {
                row.style.display = showRows ? "block" : "none";
            });
            button.setAttribute("data-expanded", showRows ? "true" : "false");
            button.textContent = showRows ? "Hide extra reports" : `View all ${hiddenRows.length + 3} reports`;
        });
    });

    const userSearch = document.getElementById("adminUserSearch");
    if (userSearch) {
        userSearch.addEventListener("input", () => {
            const query = userSearch.value.trim().toLowerCase();
            document.querySelectorAll("#adminUsersTable tbody tr").forEach((row) => {
                const nameCell = row.querySelector("td");
                const name = nameCell ? nameCell.textContent.trim().toLowerCase() : "";
                row.style.display = !query || name.includes(query) ? "" : "none";
            });
        });
    }

    document.querySelectorAll(".admin-log-time[data-created-at]").forEach((node) => {
        const value = node.getAttribute("data-created-at");
        if (!value) return;
        const relative = formatRelativeTime(value);
        if (relative) node.textContent = relative;
    });

    const hashSeed = (text) => {
        let hash = 0;
        for (let i = 0; i < text.length; i += 1) {
            hash = (hash * 31 + text.charCodeAt(i)) % 360;
        }
        return hash;
    };

    document.querySelectorAll(".report-avatar[data-seed]").forEach((node) => {
        const seed = node.getAttribute("data-seed") || "user";
        const hue = hashSeed(seed);
        node.style.background = `linear-gradient(135deg, hsla(${hue}, 70%, 55%, 0.6), hsla(${(hue + 40) % 360}, 70%, 45%, 0.4))`;
    });

    document.querySelectorAll(".admin-avatar[data-seed]").forEach((node) => {
        const seed = node.getAttribute("data-seed") || "user";
        const hue = hashSeed(seed);
        node.style.background = `linear-gradient(135deg, hsla(${hue}, 70%, 55%, 0.6), hsla(${(hue + 30) % 360}, 70%, 45%, 0.4))`;
    });
}

function setupNotificationDropdown() {
    document.querySelectorAll(".nav-note-time[data-created-at]").forEach((node) => {
        const value = node.getAttribute("data-created-at");
        if (!value) return;
        const relative = formatRelativeTime(value);
        if (relative) node.textContent = relative;
    });

    const clearButton = document.querySelector(".nav-note-clear");
    if (clearButton) {
        clearButton.addEventListener("click", async () => {
            try {
                await postForm("/notifications/read", {});
                window.location.reload();
            } catch (err) {
                alert(err.message);
            }
        });
    }
}

function setupAdminLogLinks() {
    const userTabButton = document.querySelector("[data-bs-target='#users']");
    const userSearch = document.getElementById("adminUserSearch");
    if (!userTabButton || !userSearch) return;

    document.querySelectorAll(".admin-log-link[data-user-id]").forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            const userId = link.getAttribute("data-user-id") || "";
            if (typeof bootstrap !== "undefined") {
                const tab = new bootstrap.Tab(userTabButton);
                tab.show();
            }
            userSearch.value = userId;
            userSearch.dispatchEvent(new Event("input"));
        });
    });
}

function setupReportForms() {
    document.querySelectorAll("#reportDisputeForm").forEach((form) => {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const disputeId = form.getAttribute("data-dispute-id");
            const formData = new FormData(form);
            const reason = String(formData.get("reason") || "").trim();
            const details = String(formData.get("details") || "").trim();
            const button = form.querySelector("button[type='submit']");
            if (button) button.disabled = true;
            try {
                await postForm(`/dispute/${disputeId}/report`, {
                    reason,
                    details,
                });
                alert("Report submitted.");
                window.location.reload();
            } catch (err) {
                alert(err.message);
                if (button) button.disabled = false;
            }
        });
    });
}

function setupVerdictVisuals() {
    const speedometer = document.querySelector(".vb-speedometer");
    if (speedometer) {
        const pct = Number(speedometer.getAttribute("data-confidence") || 0);
        const clampedPct = Math.max(0, Math.min(100, pct));
        const angle = -90 + (clampedPct * 1.8);
        speedometer.style.setProperty("--pct", String(clampedPct));
        requestAnimationFrame(() => {
            speedometer.style.setProperty("--angle", `${angle}deg`);
        });
    }

    const reasoningNode = document.getElementById("verdictReasoningText");
    if (reasoningNode) {
        const fullText = reasoningNode.getAttribute("data-text") || "";
        if (fullText && reasoningNode.getAttribute("data-rendered") !== "done") {
            const userAName = (reasoningNode.getAttribute("data-user-a") || "").trim();
            const userBName = (reasoningNode.getAttribute("data-user-b") || "").trim();
            const winnerName = (reasoningNode.getAttribute("data-winner-name") || "").trim();
            const hasAppeal = (reasoningNode.getAttribute("data-has-appeal") || "").trim() === "true";

            const normalizeDisplayNames = (value) => {
                let text = String(value || "");
                if (!text) return text;

                if (!hasAppeal) {
                    text = text
                        .replace(/Moderator Review Acknowledg(?:e)?ment[^.]*\.?\s*/gi, "")
                        .replace(/RE-EVALUATION VERDICT:[^.]*\.?\s*/gi, "")
                        .replace(/After an approved moderator appeal[^.]*\.?\s*/gi, "");
                }

                const replaceSideRefs = (replacementA, replacementB) => {
                    text = text.replace(/\b(?:argument|arguments|arugment|arugments|side|sides|user|users)\s*a\b/gi, replacementA);
                    text = text.replace(/\b(?:argument|arguments|arugment|arugments|side|sides|user|users)\s*b\b/gi, replacementB);
                };

                if (userAName) replaceSideRefs(userAName, userBName || "B");
                if (userBName) replaceSideRefs(userAName || "A", userBName);

                if (winnerName) {
                    text = text.replace(/\bWinner\s*:\s*[AB]\b/gi, `Winner: ${winnerName}`);
                }

                // Remove legacy slogan from older stored verdicts.
                text = text
                    .replace(/\s*Practicality\s*vs\.?\s*Aggression[^.]*\.?/gi, "")
                    .replace(/\s{2,}/g, " ")
                    .trim();

                return text;
            };

            const escapeHtml = (value) =>
                String(value || "")
                    .replace(/&#39;|&apos;/gi, "'")
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/\"/g, "&quot;")
                    .replace(/'/g, "&#39;");

            const escapeRegExp = (value) => String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

            const emphasizeTerms = (value) => {
                const escaped = escapeHtml(value);
                let output = escaped;

                // Convert markdown-style bold markers to HTML strong tags.
                output = output.replace(/\*\*([^*]+)\*\*/g, '<strong class="vb-emphasis">$1</strong>');

                // Bold short quoted evidence phrases.
                output = output.replace(/&quot;([^&]{2,90}?)&quot;/g, '<strong class="vb-emphasis">$1</strong>');

                // Bold percentages and common numeric score forms.
                output = output.replace(/(^|[^A-Za-z0-9])(-?\d+(?:\.\d+)?%)(?=[^A-Za-z0-9]|$)/g, "$1<strong class=\"vb-emphasis\">$2</strong>");
                output = output.replace(/(^|[^A-Za-z0-9])(-?\d+(?:\.\d+)?)(?=\s*(?:points?|score|toxicity|sarcasm|confidence)\b)/gi, "$1<strong class=\"vb-emphasis\">$2</strong>");

                // Bold winner label and winner name.
                output = output.replace(/\bWinner\b(?=\s*:)/gi, "<strong class=\"vb-emphasis\">Winner</strong>");

                const names = [userAName, userBName, winnerName].filter(Boolean);
                names.forEach((name) => {
                    const escapedName = escapeRegExp(escapeHtml(name));
                    if (!escapedName) return;
                    const pattern = new RegExp(`\\b${escapedName}\\b`, "gi");
                    output = output.replace(pattern, (m) => `<strong class="vb-emphasis">${m}</strong>`);
                });

                // Guarantee at least one emphasis for readability when model returns plain text.
                if (output.indexOf("vb-emphasis") === -1) {
                    output = output.replace(/(^|\s)([A-Z][a-z]{2,})(?=\s)/, '$1<strong class="vb-emphasis">$2</strong>');
                }

                return output;
            };

            const labelGroups = [
                { title: "Behavior", aliases: ["Behavior", "Behavioral Evidence"] },
                { title: "Where it failed", aliases: ["Where it failed", "The Logical Autopsy"] },
                { title: "Better plan", aliases: ["Better plan", "The Path to Victory"] },
                { title: "Final decision", aliases: ["Final decision", "Final Ruling"] },
            ];

            const extractSections = (text) => {
                const normalized = String(text || "").replace(/\s+/g, " ").trim();
                const sections = [];

                labelGroups.forEach((group) => {
                    let chosen = null;
                    group.aliases.forEach((alias) => {
                        if (chosen) return;
                        const escaped = alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
                        const pattern = new RegExp(`${escaped}\\s*:`, "i");
                        const match = pattern.exec(normalized);
                        if (match) {
                            chosen = {
                                label: group.title,
                                start: match.index,
                                markerLength: match[0].length,
                            };
                        }
                    });
                    if (chosen) sections.push(chosen);
                });

                if (!sections.length) return [];
                sections.sort((a, b) => a.start - b.start);

                return sections.map((item, idx) => {
                    const contentStart = item.start + item.markerLength;
                    const contentEnd = idx + 1 < sections.length ? sections[idx + 1].start : normalized.length;
                    const body = normalized.slice(contentStart, contentEnd).trim();
                    return { label: item.label, body };
                });
            };

            const normalizedText = normalizeDisplayNames(fullText);
            const sections = extractSections(normalizedText);
            if (sections.length) {
                const defaultSectionBody = (label) => {
                    if (!label) return "No details provided.";
                    const key = label.toLowerCase();
                    if (key === "behavior") {
                        return "Tone and intent signals were reviewed for both sides.";
                    }
                    if (key === "where it failed") {
                        return "No major failures were detected in the argument structure.";
                    }
                    if (key === "better plan") {
                        return "Both sides provided viable next steps without a clear advantage.";
                    }
                    if (key === "final decision") {
                        return "The decision reflects overall clarity and implementation strength.";
                    }
                    return "No details provided.";
                };
                reasoningNode.innerHTML = sections
                    .map(
                        (section) => `
                        <div class="judgment-section">
                            <h6 class="judgment-section-title">${escapeHtml(section.label)}</h6>
                            <p class="judgment-section-body mb-0">${emphasizeTerms(section.body || defaultSectionBody(section.label))}</p>
                        </div>
                    `,
                    )
                    .join("");
            } else {
                // Fallback for old verdict strings that do not follow labeled format.
                reasoningNode.innerHTML = emphasizeTerms(normalizedText);
            }

            reasoningNode.setAttribute("data-rendered", "done");
        }
    }

    const voteContainer = document.getElementById("voteDistribution");
    if (!voteContainer) return;

    const disputeId = voteContainer.getAttribute("data-dispute-id");
    if (!disputeId) return;

    const updateVoteBars = async () => {
        try {
            const response = await fetch(`/dispute/${disputeId}/votes`);
            if (!response.ok) return;
            const voteData = await response.json();

            let totalVotes = 0;
            Object.values(voteData).forEach((value) => {
                totalVotes += Number(value || 0);
            });

            voteContainer.querySelectorAll(".vote-row").forEach((row) => {
                const userId = row.getAttribute("data-user-id");
                const count = Number(voteData[userId] || 0);
                const percentage = totalVotes > 0 ? (count / totalVotes) * 100 : 0;

                const countNode = row.querySelector(".vote-count");
                const barNode = row.querySelector(".vote-bar-fill");
                if (countNode) countNode.textContent = String(count);
                if (barNode) barNode.style.width = `${percentage.toFixed(1)}%`;
            });
        } catch (_err) {
            // Keep UI stable if polling fails temporarily.
        }
    };

    updateVoteBars();
    window.setInterval(updateVoteBars, 8000);
}

document.addEventListener("DOMContentLoaded", () => {
    flushQueuedBadgeNotifications();
    setupStatCounters();
    setupGeneralCounters();
    setupDescriptionCounter();
    setupWordCounter();
    setupAuthForms();
    setupRoleSwitchForms();
    setupDisputeForms();
    setupDisputeLiveState();
    setupVoteAndAppeal();
    setupCommentForm();
    setupReportForms();
    setupDisputeFeedVoting();
    setupAdminForms();
    setupAdminEnhancements();
    setupAppealModal();
    setupModerationModal();
    setupNotificationDropdown();
    setupAdminLogLinks();
    setupVerdictVisuals();
    setupDashboardDonut();
    setupLeaderboardChart();
    setupStatisticsCharts();
    setupAgreementCounter();
    setupTypewriterSuggestion();
    setupTooltips();
    setupDataDrivenWidths();
});
