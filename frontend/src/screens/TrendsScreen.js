import React, { useEffect, useState, useRef } from "react";
import {
  View, Text, StyleSheet, ScrollView,
  ActivityIndicator, RefreshControl,
} from "react-native";
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Filler, Tooltip, Legend,
} from "chart.js";
import { Line, Bar, Doughnut } from "react-chartjs-2";
import { api } from "../services/api";

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Filler, Tooltip, Legend
);

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
};

const GRID = { color: "#1e1e1e" };
const TICK = { color: "#555", font: { size: 10 } };

function fmt(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return `${d.getDate()}.${d.getMonth() + 1}.`;
}

// Wöchentliche TSS aus PMC ableiten: TSS ≈ ATL*7 - prev_ATL*6
function weeklyTSS(pmc) {
  const weeks = {};
  for (let i = 1; i < pmc.length; i++) {
    const tss = Math.max(0, pmc[i].atl * 7 - pmc[i - 1].atl * 6);
    const d = new Date(pmc[i].date);
    const mon = new Date(d); mon.setDate(d.getDate() - d.getDay() + 1);
    const key = mon.toISOString().slice(0, 10);
    weeks[key] = (weeks[key] || 0) + tss;
  }
  return Object.entries(weeks)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-12)
    .map(([date, tss]) => {
      const d = new Date(date);
      const kw = Math.ceil((((d - new Date(d.getFullYear(), 0, 1)) / 86400000) + 1) / 7);
      return { label: `KW${kw}`, tss: Math.round(tss) };
    });
}

export default function TrendsScreen() {
  const [trends, setTrends] = useState(null);
  const [sleep, setSleep] = useState([]);
  const [steps, setSteps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const [t, sl, st] = await Promise.all([api.trends(90), api.sleep(30), api.steps(30)]);
      setTrends(t);
      setSleep(sl);
      setSteps(Array.isArray(st) ? st : []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return <View style={s.center}><ActivityIndicator color="#00C853" size="large" /></View>;
  }

  const pmc     = trends?.pmc ?? [];
  const dist    = trends?.training_distribution ?? {};
  const ftp     = trends?.ftp ?? 0;
  const ftpTarget = trends?.ftp_target ?? 250;
  const vo2last = (trends?.vo2max ?? []).slice(-1)[0]?.vo2max ?? null;

  const ctlLast = pmc.slice(-1)[0]?.ctl ?? 0;
  const atlLast = pmc.slice(-1)[0]?.atl ?? 0;
  const tsbLast = pmc.slice(-1)[0]?.tsb ?? 0;

  // PMC labels (jeden 7. Tag beschriften)
  const pmcLabels = pmc.map((p, i) => (i % 7 === 0 ? fmt(p.date) : ""));
  const ctlData   = pmc.map((p) => +p.ctl.toFixed(1));
  const atlData   = pmc.map((p) => +p.atl.toFixed(1));
  const tsbData   = pmc.map((p) => +p.tsb.toFixed(1));

  // Schlaf
  const sleepLabels = sleep.map((d) => fmt(d.date));
  const sleepScores = sleep.map((d) => d.score ?? null);

  // Wöchentliches Volumen
  const weekly = weeklyTSS(pmc);

  // Trainingsverteilung
  const z2  = dist.Zone2 ?? 0;
  const ss  = dist.SweetSpot ?? 0;
  const hit = dist.HighIntensity ?? 0;
  const seilerOk = z2 >= 65 && ss <= 25 && hit <= 15;

  return (
    <ScrollView
      style={s.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor="#00C853" />
      }
    >
      <Text style={s.title}>📈 Trends</Text>

      {/* KPIs */}
      <View style={s.kpiRow}>
        <View style={s.kpi}>
          <Text style={[s.kpiVal, { color: "#00C853" }]}>{ftp}W</Text>
          <Text style={s.kpiLabel}>FTP</Text>
          <Text style={s.kpiSub}>→ Ziel {ftpTarget}W</Text>
        </View>
        {vo2last && (
          <View style={s.kpi}>
            <Text style={[s.kpiVal, { color: "#00f2ff" }]}>{vo2last.toFixed(1)}</Text>
            <Text style={s.kpiLabel}>VO2 Max</Text>
          </View>
        )}
        <View style={s.kpi}>
          <Text style={[s.kpiVal, { color: tsbLast >= 0 ? "#00C853" : "#FF6D00" }]}>
            {tsbLast >= 0 ? "+" : ""}{tsbLast.toFixed(0)}
          </Text>
          <Text style={s.kpiLabel}>TSB Form</Text>
          <Text style={s.kpiSub}>{tsbLast >= 0 ? "frisch" : "müde"}</Text>
        </View>
      </View>

      {/* PMC */}
      {pmc.length > 1 && (
        <View style={s.section}>
          <Text style={s.sectionTitle}>Performance Management (90 Tage)</Text>
          <View style={{ height: 180 }}>
            <Line
              data={{
                labels: pmcLabels,
                datasets: [
                  {
                    label: "ATL",
                    data: atlData,
                    borderColor: "#FF6D00",
                    borderWidth: 2,
                    backgroundColor: "rgba(255,109,0,0.15)",
                    fill: true,
                    tension: 0,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                  },
                  {
                    label: "CTL",
                    data: ctlData,
                    borderColor: "#00C853",
                    borderWidth: 2.5,
                    backgroundColor: "rgba(0,200,83,0.2)",
                    fill: true,
                    tension: 0,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                  },
                ],
              }}
              options={{
                ...CHART_DEFAULTS,
                interaction: { mode: "index", intersect: false },
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    backgroundColor: "#222", borderColor: "#333", borderWidth: 1,
                    callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y}` },
                  },
                },
                scales: {
                  x: { grid: GRID, ticks: TICK },
                  y: { grid: GRID, ticks: TICK },
                },
              }}
            />
          </View>

          {/* Legende CTL/ATL */}
          <View style={s.legend}>
            <View style={s.legendItem}>
              <View style={[s.legendDot, { backgroundColor: "#00C853" }]} />
              <Text style={s.legendText}>CTL {ctlLast.toFixed(0)} – Fitness</Text>
            </View>
            <View style={s.legendItem}>
              <View style={[s.legendDot, { backgroundColor: "#FF6D00" }]} />
              <Text style={s.legendText}>ATL {atlLast.toFixed(0)} – Müdigkeit</Text>
            </View>
          </View>

          {/* Divider */}
          <View style={s.divider} />

          {/* TSB Label */}
          <View style={s.tsbHeader}>
            <Text style={s.tsbTitle}>TSB – Form</Text>
            <View style={s.tsbBadges}>
              <View style={s.tsbBadge}>
                <View style={[s.tsbDot, { backgroundColor: "#00C853" }]} />
                <Text style={[s.tsbBadgeText, { color: "#00C853" }]}>frisch</Text>
              </View>
              <View style={s.tsbBadge}>
                <View style={[s.tsbDot, { backgroundColor: "#FF1744" }]} />
                <Text style={[s.tsbBadgeText, { color: "#FF1744" }]}>müde</Text>
              </View>
            </View>
          </View>

          <View style={{ height: 80 }}>
            <Bar
              data={{
                labels: pmcLabels,
                datasets: [{
                  data: tsbData,
                  backgroundColor: tsbData.map((v) =>
                    v >= 0 ? "rgba(0,200,83,0.75)" : "rgba(255,23,68,0.7)"
                  ),
                  borderRadius: 2,
                  borderSkipped: false,
                }],
              }}
              options={{
                ...CHART_DEFAULTS,
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    backgroundColor: "#222", borderColor: "#333", borderWidth: 1,
                    callbacks: {
                      title: (ctx) => ctx[0].label || "",
                      label: (ctx) => ` TSB: ${ctx.parsed.y > 0 ? "+" : ""}${ctx.parsed.y}`,
                    },
                  },
                },
                scales: {
                  x: { display: false },
                  y: { grid: GRID, ticks: TICK },
                },
              }}
            />
          </View>
        </View>
      )}

      {/* Schlaf */}
      {sleepScores.some((v) => v !== null) && (
        <View style={s.section}>
          <Text style={s.sectionTitle}>Schlafqualität (30 Tage)</Text>
          <View style={{ height: 140 }}>
            <Line
              data={{
                labels: sleepLabels,
                datasets: [{
                  data: sleepScores,
                  borderColor: "#9C27B0",
                  borderWidth: 2.5,
                  backgroundColor: "rgba(156,39,176,0.2)",
                  fill: true,
                  tension: 0.3,
                  pointRadius: 0,
                  pointHoverRadius: 6,
                  pointHoverBackgroundColor: "#9C27B0",
                  pointHoverBorderColor: "#fff",
                  pointHoverBorderWidth: 2,
                  spanGaps: true,
                }],
              }}
              options={{
                ...CHART_DEFAULTS,
                interaction: { mode: "index", intersect: false },
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    backgroundColor: "#222", borderColor: "#9C27B0", borderWidth: 1,
                    padding: 10,
                    callbacks: {
                      title: (ctx) => `📅 ${ctx[0].label}`,
                      label: (ctx) => {
                        const v = ctx.parsed.y;
                        if (v === null) return "";
                        const emoji = v >= 75 ? "😴 Gut" : v >= 50 ? "😐 OK" : "😟 Schlecht";
                        return `  Sleep Score: ${v}  ${emoji}`;
                      },
                    },
                  },
                },
                scales: {
                  x: {
                    grid: GRID,
                    ticks: { ...TICK, maxRotation: 0, callback: (_, i) => i % 5 === 0 ? sleepLabels[i] : "" },
                  },
                  y: { min: 0, max: 100, grid: GRID, ticks: TICK },
                },
              }}
            />
          </View>
        </View>
      )}

      {/* Wöchentliches Volumen */}
      {weekly.length > 0 && (
        <View style={s.section}>
          <Text style={s.sectionTitle}>Wöchentliches Volumen (TSS)</Text>
          <View style={{ height: 160 }}>
            <Bar
              data={{
                labels: weekly.map((w) => w.label),
                datasets: [{
                  data: weekly.map((w) => w.tss),
                  backgroundColor: weekly.map((w, i) =>
                    i === weekly.length - 1 ? "#00C853" : "rgba(0,200,83,0.5)"
                  ),
                  borderRadius: 5,
                }],
              }}
              options={{
                ...CHART_DEFAULTS,
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    backgroundColor: "#222", borderColor: "#333", borderWidth: 1,
                    callbacks: { label: (ctx) => ` TSS: ${ctx.parsed.y}` },
                  },
                },
                scales: {
                  x: { grid: { display: false }, ticks: TICK },
                  y: { grid: GRID, ticks: TICK },
                },
              }}
            />
          </View>
        </View>
      )}

      {/* Trainingsverteilung */}
      {(z2 + ss + hit) > 0 && (
        <View style={s.section}>
          <Text style={s.sectionTitle}>Trainingsverteilung – letzte 4 Wochen</Text>
          <View style={s.distRow}>
            <View style={{ width: 140, height: 140 }}>
              <Doughnut
                data={{
                  datasets: [{
                    data: [z2, ss, hit],
                    backgroundColor: ["#00C853", "#FFD600", "#FF1744"],
                    borderWidth: 0,
                    hoverOffset: 4,
                  }],
                }}
                options={{
                  ...CHART_DEFAULTS,
                  cutout: "68%",
                  plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (ctx) => ` ${ctx.parsed}%` } },
                  },
                }}
                plugins={[{
                  id: "centerText",
                  afterDraw(chart) {
                    const { ctx, chartArea: { width, height, left, top } } = chart;
                    ctx.save();
                    ctx.font = "bold 22px -apple-system, sans-serif";
                    ctx.fillStyle = "#fff";
                    ctx.textAlign = "center";
                    ctx.fillText(`${z2}%`, left + width / 2, top + height / 2 - 6);
                    ctx.font = "11px -apple-system, sans-serif";
                    ctx.fillStyle = "#555";
                    ctx.fillText("Zone 2", left + width / 2, top + height / 2 + 14);
                    ctx.restore();
                  },
                }]}
              />
            </View>
            <View style={s.distBars}>
              {[
                { label: "Zone 2", pct: z2, color: "#00C853" },
                { label: "Sweet Spot", pct: ss, color: "#FFD600" },
                { label: "High Intensity", pct: hit, color: "#FF1744" },
              ].map(({ label, pct, color }) => (
                <View key={label} style={s.distBarRow}>
                  <View style={s.distBarHeader}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <View style={[s.distBarDot, { backgroundColor: color }]} />
                      <Text style={s.distBarLabel}>{label}</Text>
                    </View>
                    <Text style={[s.distBarPct, { color }]}>{pct}%</Text>
                  </View>
                  <View style={s.distTrack}>
                    <View style={[s.distFill, { width: `${pct}%`, backgroundColor: color }]} />
                  </View>
                </View>
              ))}
            </View>
          </View>
          <View style={s.seilerBadge}>
            <Text style={s.seilerText}>Ziel: 70 / 20 / 10 (Seiler)</Text>
            <Text style={[s.seilerStatus, { color: seilerOk ? "#00C853" : "#FF9800" }]}>
              {seilerOk ? "✓ Fast perfekt" : "⚠ Anpassen"}
            </Text>
          </View>
        </View>
      )}

      {/* Tägliche Schritte */}
      {steps.length > 0 && (
        <View style={s.section}>
          <Text style={s.sectionTitle}>Tägliche Schritte (30 Tage)</Text>
          <View style={{ height: 160 }}>
            <Bar
              data={{
                labels: steps.map((d) => fmt(d.date)),
                datasets: [{
                  data: steps.map((d) => d.steps ?? 0),
                  backgroundColor: steps.map((d) =>
                    (d.steps ?? 0) >= 8000 ? "rgba(0,200,83,0.7)" : "rgba(255,109,0,0.6)"
                  ),
                  borderRadius: 4,
                }],
              }}
              options={{
                ...CHART_DEFAULTS,
                plugins: {
                  legend: { display: false },
                  tooltip: {
                    backgroundColor: "#222", borderColor: "#333", borderWidth: 1,
                    callbacks: {
                      title: (ctx) => `📅 ${steps[ctx[0].dataIndex]?.date ?? ""}`,
                      label: (ctx) => ` ${ctx.parsed.y.toLocaleString()} Schritte`,
                    },
                  },
                },
                scales: {
                  x: {
                    grid: { display: false },
                    ticks: { ...TICK, maxRotation: 0, callback: (_, i) => i % 5 === 0 ? fmt(steps[i]?.date) : "" },
                  },
                  y: {
                    grid: GRID, ticks: {
                      ...TICK,
                      callback: (v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v,
                    },
                  },
                },
              }}
            />
          </View>
          <View style={s.legend}>
            <View style={s.legendItem}>
              <View style={[s.legendDot, { backgroundColor: "#00C853" }]} />
              <Text style={s.legendText}>≥ 8.000 Schritte</Text>
            </View>
            <View style={s.legendItem}>
              <View style={[s.legendDot, { backgroundColor: "#FF6D00" }]} />
              <Text style={s.legendText}>{"< 8.000 Schritte"}</Text>
            </View>
          </View>
        </View>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#111" },
  center: { flex: 1, backgroundColor: "#111", justifyContent: "center", alignItems: "center" },
  title: { color: "#fff", fontSize: 24, fontWeight: "800", margin: 20, marginTop: 60 },

  kpiRow: { flexDirection: "row", gap: 10, marginHorizontal: 15, marginBottom: 12 },
  kpi: { flex: 1, backgroundColor: "#1a1a1a", borderRadius: 14, padding: 14, alignItems: "center", borderWidth: 1, borderColor: "#222" },
  kpiVal: { fontSize: 28, fontWeight: "800" },
  kpiLabel: { fontSize: 11, color: "#555", marginTop: 3 },
  kpiSub: { fontSize: 11, color: "#444", marginTop: 2 },

  section: { backgroundColor: "#1a1a1a", marginHorizontal: 15, marginBottom: 12, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: "#222" },
  sectionTitle: { color: "#555", fontSize: 11, fontWeight: "700", letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 12 },

  legend: { flexDirection: "row", gap: 16, marginTop: 10, marginBottom: 4 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { color: "#888", fontSize: 12 },

  divider: { height: 1, backgroundColor: "#2a2a2a", marginVertical: 12 },

  tsbHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  tsbTitle: { fontSize: 11, color: "#555", textTransform: "uppercase", letterSpacing: 1 },
  tsbBadges: { flexDirection: "row", gap: 10 },
  tsbBadge: { flexDirection: "row", alignItems: "center", gap: 4 },
  tsbDot: { width: 8, height: 8, borderRadius: 2 },
  tsbBadgeText: { fontSize: 12 },

  distRow: { flexDirection: "row", alignItems: "center", gap: 20 },
  distBars: { flex: 1, gap: 14 },
  distBarRow: { gap: 5 },
  distBarHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  distBarDot: { width: 10, height: 10, borderRadius: 2 },
  distBarLabel: { fontSize: 13, color: "#ccc" },
  distBarPct: { fontSize: 16, fontWeight: "800" },
  distTrack: { backgroundColor: "#252525", borderRadius: 6, height: 8 },
  distFill: { height: "100%", borderRadius: 6 },

  seilerBadge: { marginTop: 14, padding: 10, backgroundColor: "#222", borderRadius: 10, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  seilerText: { fontSize: 12, color: "#555" },
  seilerStatus: { fontSize: 13, fontWeight: "700" },
});
