/**
 * Kronos · The 3R Rule Structural Trading System Interactive Frontend Controller
 * Handles:
 * - Multi-timeframe (1D + 5M) structural analysis + Kronos forecast execution (`/api/3r/analyze`)
 * - Guided 3R Scenario Presets (`live_market`, `topside_short`, `bullish_dip_long`, `chased_breakout_trap`)
 * - Interactive Plotly chart rendering with responsive ResizeObserver & Structural Stop line updates
 * - Real-time Structural Risk Position Sizing & "The Wall Street Raise" 10% Scaling Engine (`/api/3r/calculate-sizing`)
 */
(function () {
    "use strict";

    let currentScenario = "live_market";
    let lastEvaluation = null;

    const el = (id) => document.getElementById(id);

    function formatMoney(val, decimals = 2) {
        const num = Number(val);
        if (!Number.isFinite(num)) return "$0.00";
        const sign = num < 0 ? "-" : "";
        return `${sign}$${Math.abs(num).toLocaleString("en-US", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        })}`;
    }

    function countGreenDays() {
        const boxes = document.querySelectorAll(".green-day-cb");
        let count = 0;
        boxes.forEach((cb) => {
            if (cb.checked) count += 1;
        });
        return count;
    }

    function renderPlotlyChart(containerId, figSpec) {
        const node = el(containerId);
        if (!node || !figSpec || typeof Plotly === "undefined") return;
        const data = figSpec.data || [];
        const layout = Object.assign({}, figSpec.layout || {}, {
            autosize: true,
        });
        const config = {
            responsive: true,
            displaylogo: false,
            scrollZoom: true,
            modeBarButtonsToRemove: ["lasso2d", "select2d"],
        };
        Plotly.react(node, data, layout, config);
    }

    function updatePanel1Banner(structure) {
        const isBull = structure.trend_regime === "BULLISH";
        const badge = el("regime-main-badge");
        if (badge) {
            badge.className = `regime-badge ${isBull ? "bullish" : "bearish"}`;
            badge.textContent = isBull
                ? "BULLISH BIAS (Above 50 SMA)"
                : "BEARISH BIAS (Below 50 SMA)";
        }

        const diffSign = structure.sma_distance >= 0 ? "+" : "";
        if (el("regime-price-vs-sma")) {
            el("regime-price-vs-sma").textContent = `${diffSign}${formatMoney(structure.sma_distance)} (${diffSign}${Number(structure.sma_distance_pct).toFixed(2)}%)`;
        }
        if (el("metric-spot-price")) el("metric-spot-price").textContent = formatMoney(structure.current_price);
        if (el("metric-sma50")) el("metric-sma50").textContent = formatMoney(structure.sma_50);
        if (el("metric-session-date")) el("metric-session-date").textContent = structure.session_date || "-";
        if (el("regime-contrarian-note")) el("regime-contrarian-note").textContent = structure.contrarian_rule;

        // Quota Meter
        if (el("quota-directive-text")) {
            el("quota-directive-text").textContent = isBull
                ? "80%–90% TRADES ON LONG / BUY SIDE"
                : "80%–90% TRADES ON SHORT / SELL SIDE";
        }
        const primaryBar = el("quota-primary-bar");
        if (primaryBar) {
            primaryBar.className = `quota-primary-fill ${isBull ? "bullish" : "bearish"}`;
        }
        if (el("quota-primary-label")) {
            el("quota-primary-label").textContent = isBull
                ? "85% Long Execution (3:1 – 6:1 R:R)"
                : "85% Short Execution (3:1 – 4:1+ R:R)";
        }
        if (el("quota-archetypes-text")) {
            el("quota-archetypes-text").textContent = `Optimal Setups: ${(structure.optimal_archetypes || []).join(" · ")}`;
        }

        // ATR Capacity Gauge
        const pct = Number(structure.atr_consumed_pct) || 0;
        if (el("atr-consumed-pct")) el("atr-consumed-pct").textContent = `${pct.toFixed(1)}%`;
        const fill = el("atr-gauge-fill");
        if (fill) {
            fill.style.width = `${Math.min(100, Math.max(2, pct))}%`;
        }
        const atrBadge = el("atr-state-badge");
        if (atrBadge) {
            if (pct >= 100 || structure.is_overextended) {
                atrBadge.className = "atr-badge exhausted";
                atrBadge.textContent = pct >= 100 ? "OVEREXTENDED (>100% ATR)" : "ATR EXHAUSTION (>=85%)";
            } else if (pct >= 60) {
                atrBadge.className = "atr-badge elevated";
                atrBadge.textContent = "REVERSAL ZONE (60%–85% ATR)";
            } else {
                atrBadge.className = "atr-badge normal";
                atrBadge.textContent = "FRESH ATR CAPACITY";
            }
        }
        if (el("metric-atr14")) el("metric-atr14").textContent = formatMoney(structure.atr_14);
        if (el("metric-intraday-exp")) el("metric-intraday-exp").textContent = formatMoney(structure.intraday_expansion);
        if (el("metric-remaining-atr")) el("metric-remaining-atr").textContent = formatMoney(structure.remaining_atr);

        // 4 Liquidity Levels Strip
        if (el("lvl-swing-high")) el("lvl-swing-high").textContent = formatMoney(structure.swing_high);
        if (el("lvl-range-high")) el("lvl-range-high").textContent = formatMoney(structure.range_high);
        if (el("lvl-range-low")) el("lvl-range-low").textContent = formatMoney(structure.range_low);
        if (el("lvl-swing-low")) el("lvl-swing-low").textContent = formatMoney(structure.swing_low);

        // Update Morning Routine Workflow Ribbon
        if (el("step-1-desc")) {
            el("step-1-desc").textContent = `${structure.trend_regime}: Spot ${formatMoney(structure.current_price)} vs 50-SMA ${formatMoney(structure.sma_50)}`;
        }
        if (el("step-2-desc")) {
            el("step-2-desc").textContent = `14D ATR ${formatMoney(structure.atr_14)} · Consumed ${pct.toFixed(1)}% · Rem ${formatMoney(structure.remaining_atr)}`;
        }
        if (el("step-3-desc")) {
            el("step-3-desc").textContent = `SH ${formatMoney(structure.swing_high)} | RH ${formatMoney(structure.range_high)} | RL ${formatMoney(structure.range_low)} | SL ${formatMoney(structure.swing_low)}`;
        }
        if (el("view1-regime-tag")) {
            el("view1-regime-tag").textContent = `1D ${structure.trend_regime}`;
        }
        if (el("view2-zone-tag")) {
            const zText = structure.in_sell_zone
                ? "IN SELL ZONE (RH–SH)"
                : structure.in_buy_zone
                ? "IN BUY ZONE (SL–RL)"
                : "MID-RANGE";
            el("view2-zone-tag").textContent = zText;
        }
    }

    function updatePanel3Confluence(confluence, structure) {
        const titleEl = el("setup-archetype-title");
        if (titleEl) {
            const sideClass =
                confluence.setup_side === "SHORT"
                    ? "short"
                    : confluence.setup_side === "LONG"
                    ? "long"
                    : "neutral";
            titleEl.className = `setup-archetype-banner ${sideClass}`;
            titleEl.textContent = confluence.setup_archetype;
        }

        const score = Number(confluence.confluence_score) || 0;
        if (el("confluence-score-val")) el("confluence-score-val").textContent = `${score} / 100`;
        if (el("confluence-score-fill")) el("confluence-score-fill").style.width = `${Math.min(100, Math.max(0, score))}%`;

        const bd = confluence.score_breakdown || {};
        if (el("pts-trend")) el("pts-trend").textContent = `${bd.trend_alignment ?? 0} / 30`;
        if (el("pts-liquidity")) el("pts-liquidity").textContent = `${bd.liquidity_boundary ?? 0} / 30`;
        if (el("pts-feasibility")) el("pts-feasibility").textContent = `${bd.range_feasibility ?? 0} / 20`;
        if (el("pts-compression")) el("pts-compression").textContent = `${bd.price_compression ?? 0} / 20`;

        // Feasibility Gate
        const gateBox = el("feasibility-gate-box");
        if (gateBox) {
            gateBox.className = `feasibility-gate ${confluence.is_target_feasible ? "feasible" : "infeasible"}`;
        }
        if (el("feasibility-badge")) el("feasibility-badge").textContent = confluence.feasibility_status;
        if (el("kronos-pred-delta")) el("kronos-pred-delta").textContent = formatMoney(confluence.predicted_delta);
        if (el("kronos-pred-dir")) el("kronos-pred-dir").textContent = confluence.predicted_direction;
        if (el("kronos-pred-target")) el("kronos-pred-target").textContent = formatMoney(confluence.predicted_target);
        if (el("gate-rem-atr")) el("gate-rem-atr").textContent = formatMoney(structure.remaining_atr);

        // Structural Execution Parameters
        const sideBadge = el("exec-side-badge");
        if (sideBadge) {
            const s = (confluence.setup_side || "NEUTRAL").toLowerCase();
            sideBadge.className = `side-pill ${s}`;
            sideBadge.textContent =
                confluence.setup_side === "SHORT"
                    ? "SHORT / SELL AT RESISTANCE"
                    : confluence.setup_side === "LONG"
                    ? "LONG / BUY AT SUPPORT"
                    : "NO TRADE / WAIT";
        }
        if (el("exec-entry-price")) el("exec-entry-price").textContent = formatMoney(confluence.structural_entry);
        if (el("exec-stop-price")) el("exec-stop-price").textContent = formatMoney(confluence.structural_stop);
        if (el("exec-target-price")) el("exec-target-price").textContent = formatMoney(confluence.structural_target);
        if (el("exec-rr-ratio")) el("exec-rr-ratio").textContent = `${Number(confluence.estimated_rr).toFixed(2)} : 1`;

        if (el("step-4-desc")) {
            el("step-4-desc").textContent = `${confluence.setup_archetype} · Score ${score}/100 · R:R ${Number(confluence.estimated_rr).toFixed(2)}:1`;
        }

        // Warnings Banner
        const warnBanner = el("3r-warning-banner");
        const warnings = confluence.warnings || [];
        if (warnBanner) {
            if (warnings.length > 0 || confluence.chased_breakout_trap || confluence.atr_exhaustion_warning) {
                warnBanner.style.display = "flex";
                if (el("3r-warning-title")) {
                    el("3r-warning-title").textContent = warnings[0] || "⚠️ 3R STRUCTURAL RISK ALERT";
                }
                if (el("3r-warning-detail")) {
                    el("3r-warning-detail").textContent =
                        warnings.slice(1).join(" | ") ||
                        (confluence.rationale && confluence.rationale[0]) ||
                        "Verify structural stop distance and remaining Daily ATR before executing.";
                }
            } else {
                warnBanner.style.display = "none";
            }
        }

        // Rationale List
        const rList = el("confluence-rationale-list");
        if (rList) {
            rList.innerHTML = "";
            const items = [...(confluence.rationale || []), ...(confluence.warnings || [])];
            if (items.length === 0) {
                items.push("All 3R structural checks evaluated.");
            }
            items.forEach((txt) => {
                const li = document.createElement("li");
                li.textContent = txt;
                rList.appendChild(li);
            });
        }

        // Populate Panel 4 Calculator inputs with live structural entry, stop, and target
        if (el("calc-entry-price")) el("calc-entry-price").value = Number(confluence.structural_entry).toFixed(2);
        if (el("calc-stop-price")) el("calc-stop-price").value = Number(confluence.structural_stop).toFixed(2);
        if (el("calc-target-price")) el("calc-target-price").value = Number(confluence.structural_target).toFixed(2);
    }

    function updatePanel4And5(sizing, scaling) {
        if (sizing && !sizing.error) {
            if (el("res-position-size")) {
                el("res-position-size").textContent = `${sizing.position_size} shares/contracts (${sizing.trade_direction})`;
            }
            if (el("res-stop-distance")) {
                el("res-stop-distance").textContent = `${formatMoney(sizing.stop_distance)} / unit`;
            }
            if (el("res-total-risk")) {
                el("res-total-risk").textContent = `${formatMoney(sizing.total_risk_exposure)} (${Number(sizing.account_risk_pct).toFixed(2)}% acct)`;
            }
            if (el("res-projected-profit")) {
                el("res-projected-profit").textContent = `+${formatMoney(sizing.projected_profit)}`;
            }
            if (el("res-rr-ratio")) {
                el("res-rr-ratio").textContent = `${Number(sizing.risk_reward_ratio).toFixed(2)} : 1 ${sizing.meets_3r_minimum ? "✓ (3R+)" : "(Below 3R)"}`;
            }
        } else if (sizing && sizing.error) {
            if (el("res-position-size")) el("res-position-size").textContent = sizing.error;
        }

        if (scaling) {
            const greenDays = scaling.profitable_days_this_week;
            const pill = el("consistency-status-pill");
            if (pill) {
                pill.className = `consistency-pill ${scaling.consistency_met ? "pass" : "hold"}`;
                pill.textContent = scaling.consistency_met
                    ? `${greenDays}/5 Green Days ✓ (Eligible to Scale)`
                    : `${greenDays}/5 Green Days (Hold Base Size)`;
            }
            if (el("scale-tier-unlocked")) {
                el("scale-tier-unlocked").textContent = `Tier ${scaling.effective_steps} · ${scaling.recommended_shares} shares (${scaling.recommended_risk_range})`;
            }
            if (el("scale-guidance-note")) {
                el("scale-guidance-note").textContent = scaling.scaling_note;
            }

            const tbody = el("scaling-ladder-tbody");
            if (tbody && Array.isArray(scaling.ladder)) {
                tbody.innerHTML = "";
                scaling.ladder.forEach((row) => {
                    const tr = document.createElement("tr");
                    if (row.unlocked) tr.className = "tier-unlocked";
                    tr.innerHTML = `
                        <td><strong>${row.label}</strong></td>
                        <td>${formatMoney(row.account_balance, 0)}</td>
                        <td>+${Number(row.growth_from_base_pct).toFixed(1)}%</td>
                        <td><strong>${row.position_sizing_shares}</strong></td>
                        <td>${row.risk_per_trade}</td>
                        <td>
                            <span class="tier-status-badge ${row.unlocked ? "unlocked" : "locked"}">
                                ${row.unlocked ? "UNLOCKED ✓" : "LOCKED"}
                            </span>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        }
    }

    async function runFull3RAnalysis() {
        const statusEl = el("3r-status-line");
        const runBtn = el("3r-run-btn");
        const ticker = (el("3r-ticker")?.value || "SPY").trim().toUpperCase();
        const dataSource = el("3r-data-source")?.value || "local";
        const predLen = parseInt(el("3r-pred-len")?.value || "24", 10);
        const lookback = parseInt(el("3r-lookback")?.value || "256", 10);
        const sessionOffset = parseInt(el("3r-session-offset")?.value || "0", 10);
        const useModel = el("3r-use-model")?.value === "true";
        const accountBalance = parseFloat(el("calc-account-balance")?.value || "5000");
        const baseBalance = parseFloat(el("scale-base-balance")?.value || "5000");
        const maxRisk = parseFloat(el("calc-max-risk")?.value || "50");
        const consecutiveWeeks = parseInt(el("scale-consecutive-weeks")?.value || "2", 10);

        if (statusEl) {
            statusEl.textContent = `Running 3R Multi-Timeframe Analysis for ${ticker} (${currentScenario})...`;
        }
        if (runBtn) runBtn.disabled = true;

        try {
            const response = await axios.post("/api/3r/analyze", {
                ticker,
                data_source: dataSource,
                pred_len: predLen,
                lookback,
                session_offset: sessionOffset,
                use_kronos_model: useModel,
                scenario_preset: currentScenario,
                account_balance: accountBalance,
                base_balance: baseBalance,
                max_risk_dollars: maxRisk,
                profitable_days_this_week: countGreenDays(),
                consecutive_consistent_weeks: consecutiveWeeks,
            });

            const data = response.data;
            if (!data || !data.success) {
                throw new Error(data?.error || "3R analysis failed");
            }
            lastEvaluation = data;

            updatePanel1Banner(data.structure);
            updatePanel3Confluence(data.confluence, data.structure);
            updatePanel4And5(data.sizing, data.scaling);

            if (data.charts) {
                renderPlotlyChart("chart-daily-macro", data.charts.daily_macro_chart);
                renderPlotlyChart("chart-intraday-5m", data.charts.intraday_execution_chart);
            }

            if (statusEl) {
                statusEl.textContent = `✅ ${data.ticker} Evaluated (${data.provenance}) via ${data.inference_engine} in ${data.latency_ms} ms · Confluence Score: ${data.confluence_score}/100`;
            }
        } catch (err) {
            const msg = err?.response?.data?.error || err.message || "Unknown error";
            if (statusEl) statusEl.textContent = `❌ Error: ${msg}`;
        } finally {
            if (runBtn) runBtn.disabled = false;
        }
    }

    async function recalculateSizingLive() {
        const accountBalance = parseFloat(el("calc-account-balance")?.value || "5000");
        const baseBalance = parseFloat(el("scale-base-balance")?.value || "5000");
        const maxRisk = parseFloat(el("calc-max-risk")?.value || "50");
        const entryPrice = parseFloat(el("calc-entry-price")?.value || "580");
        const stopPrice = parseFloat(el("calc-stop-price")?.value || "579");
        const targetPrice = parseFloat(el("calc-target-price")?.value || "583.5");
        const pointMult = parseFloat(el("calc-point-mult")?.value || "1.0");
        const consecutiveWeeks = parseInt(el("scale-consecutive-weeks")?.value || "2", 10);

        if (el("calc-risk-slider-val")) {
            el("calc-risk-slider-val").textContent = `$${maxRisk}`;
        }

        try {
            const response = await axios.post("/api/3r/calculate-sizing", {
                account_balance: accountBalance,
                base_balance: baseBalance,
                max_risk_dollars: maxRisk,
                entry_price: entryPrice,
                structural_stop_price: stopPrice,
                target_price: targetPrice,
                point_multiplier: pointMult,
                profitable_days_this_week: countGreenDays(),
                consecutive_consistent_weeks: consecutiveWeeks,
            });
            if (response.data && response.data.success) {
                updatePanel4And5(response.data.sizing, response.data.scaling);
            }
        } catch (err) {
            console.warn("Sizing calculation error:", err);
        }
    }

    function bindEvents() {
        // Asset Quick Pills
        document.querySelectorAll(".asset-pill").forEach((btn) => {
            btn.addEventListener("click", () => {
                document.querySelectorAll(".asset-pill").forEach((b) => b.classList.remove("active"));
                btn.classList.add("active");
                const sym = btn.getAttribute("data-ticker") || "SPY";
                if (el("3r-ticker")) el("3r-ticker").value = sym;
                runFull3RAnalysis();
            });
        });

        // Scenario Quick Buttons
        document.querySelectorAll(".scenario-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                document.querySelectorAll(".scenario-btn").forEach((b) => b.classList.remove("active"));
                btn.classList.add("active");
                currentScenario = btn.getAttribute("data-scenario") || "live_market";
                runFull3RAnalysis();
            });
        });

        // Main Run Button
        if (el("3r-run-btn")) {
            el("3r-run-btn").addEventListener("click", runFull3RAnalysis);
        }

        // Sync Risk Slider and Number Input
        const riskSlider = el("calc-max-risk-slider");
        const riskNum = el("calc-max-risk");
        if (riskSlider && riskNum) {
            riskSlider.addEventListener("input", () => {
                riskNum.value = riskSlider.value;
                recalculateSizingLive();
            });
            riskNum.addEventListener("input", () => {
                riskSlider.value = Math.min(250, Math.max(10, Number(riskNum.value) || 50));
                recalculateSizingLive();
            });
        }

        // Bind all calculator & scaling inputs
        [
            "calc-account-balance",
            "calc-entry-price",
            "calc-stop-price",
            "calc-target-price",
            "calc-point-mult",
            "scale-base-balance",
            "scale-consecutive-weeks",
        ].forEach((inputId) => {
            const node = el(inputId);
            if (node) {
                node.addEventListener("input", recalculateSizingLive);
                node.addEventListener("change", recalculateSizingLive);
            }
        });

        document.querySelectorAll(".green-day-cb").forEach((cb) => {
            cb.addEventListener("change", recalculateSizingLive);
        });

        // Responsive Plotly resize
        if (typeof ResizeObserver !== "undefined") {
            const ro = new ResizeObserver(() => {
                ["chart-daily-macro", "chart-intraday-5m"].forEach((cid) => {
                    const cNode = el(cid);
                    if (cNode && cNode.data && typeof Plotly !== "undefined") {
                        Plotly.Plots.resize(cNode);
                    }
                });
            });
            const chartsCol = el("panel-2-charts");
            if (chartsCol) ro.observe(chartsCol);
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        bindEvents();
        runFull3RAnalysis();
    });
})();
