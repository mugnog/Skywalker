import React, { useState, useRef, useEffect } from "react";
import {
  View, Text, StyleSheet, ScrollView, TextInput,
  TouchableOpacity, ActivityIndicator, KeyboardAvoidingView,
  Alert,
} from "react-native";
import { api } from "../services/api";

// ── Markdown Renderer ─────────────────────────────────────────────────────────

function renderInline(text) {
  // Split on **bold** patterns
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return <Text key={i} style={md.bold}>{p.slice(2, -2)}</Text>;
    }
    return <Text key={i}>{p}</Text>;
  });
}

function MarkdownBlock({ text }) {
  const lines = text.split("\n");
  const elements = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Heading ## or ###
    if (/^#{1,3}\s/.test(line)) {
      const level = (line.match(/^#+/) || [""])[0].length;
      const content = line.replace(/^#+\s*/, "");
      elements.push(
        <Text key={i} style={level === 1 ? md.h1 : level === 2 ? md.h2 : md.h3}>
          {renderInline(content)}
        </Text>
      );
      i++; continue;
    }

    // Blockquote
    if (line.startsWith("> ")) {
      const quoteLines = [];
      while (i < lines.length && lines[i].startsWith("> ")) {
        quoteLines.push(lines[i].slice(2));
        i++;
      }
      elements.push(
        <View key={`bq-${i}`} style={md.blockquote}>
          <Text style={md.blockquoteText}>{quoteLines.map((l, j) => <Text key={j}>{renderInline(l)}{j < quoteLines.length - 1 ? "\n" : ""}</Text>)}</Text>
        </View>
      );
      continue;
    }

    // Table: detect header row
    if (line.trim().startsWith("|") && lines[i + 1]?.includes("---")) {
      const headers = line.split("|").slice(1, -1).map(h => h.trim().replace(/\*\*/g, ""));
      i += 2; // skip separator
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i].split("|").slice(1, -1).map(c => c.trim());
        rows.push(cells);
        i++;
      }
      elements.push(
        <View key={`tbl-${i}`} style={md.table}>
          <View style={md.tableHeaderRow}>
            {headers.map((h, j) => (
              <Text key={j} style={[md.tableHeaderCell, j === 0 && { flex: 0.7 }]}>{h}</Text>
            ))}
          </View>
          {rows.map((row, ri) => (
            <View key={ri} style={[md.tableRow, ri % 2 === 1 && md.tableRowAlt]}>
              {row.map((cell, ci) => {
                const isToday = cell.includes("HEUTE");
                return (
                  <Text key={ci} style={[md.tableCell, ci === 0 && { flex: 0.7, fontWeight: "700" }, isToday && md.tableCellToday]}>
                    {renderInline(cell.replace(/^\*(.*)\*$/, "$1").replace(/^\*(.*)\*$/, "$1"))}
                  </Text>
                );
              })}
            </View>
          ))}
        </View>
      );
      continue;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      elements.push(<View key={i} style={md.hr} />);
      i++; continue;
    }

    // Empty line
    if (line.trim() === "") {
      elements.push(<View key={i} style={{ height: 6 }} />);
      i++; continue;
    }

    // Regular line
    elements.push(
      <Text key={i} style={md.p}>{renderInline(line)}</Text>
    );
    i++;
  }

  return <View>{elements}</View>;
}

const md = StyleSheet.create({
  h1: { color: "#00C853", fontSize: 16, fontWeight: "900", marginBottom: 8, marginTop: 4 },
  h2: { color: "#00C853", fontSize: 15, fontWeight: "800", marginBottom: 6, marginTop: 8 },
  h3: { color: "#aaa", fontSize: 13, fontWeight: "700", marginBottom: 4, marginTop: 6 },
  bold: { fontWeight: "800", color: "#fff" },
  p: { color: "#ddd", fontSize: 13, lineHeight: 19, marginBottom: 2 },
  hr: { height: 1, backgroundColor: "#333", marginVertical: 8 },
  blockquote: { borderLeftWidth: 3, borderLeftColor: "#00C853", paddingLeft: 10, marginVertical: 6, backgroundColor: "#0d2b1a", borderRadius: 6, padding: 8 },
  blockquoteText: { color: "#88d4a8", fontSize: 12, lineHeight: 18 },
  table: { marginVertical: 8, borderRadius: 8, overflow: "hidden", borderWidth: 1, borderColor: "#2a2a2a" },
  tableHeaderRow: { flexDirection: "row", backgroundColor: "#1a2e1a" },
  tableHeaderCell: { flex: 1, color: "#00C853", fontSize: 11, fontWeight: "700", padding: 7, borderRightWidth: 1, borderRightColor: "#2a2a2a" },
  tableRow: { flexDirection: "row", backgroundColor: "#141414" },
  tableRowAlt: { backgroundColor: "#1a1a1a" },
  tableCell: { flex: 1, color: "#ccc", fontSize: 11, padding: 6, borderRightWidth: 1, borderRightColor: "#222", lineHeight: 16 },
  tableCellToday: { color: "#00C853", fontWeight: "700" },
});

const WOCHENPLAN_MSG = "Erstelle einen vollständigen, periodisierten Wochenplan für meine bevorzugten Trainingstage. Berücksichtige meine Ziele, Frequenz und aktuellen Form (CTL/ATL/TSB). Verteile die Einheiten sinnvoll (Zone 2 Volumen, Sweet Spot, evtl. HIT) und gib für HEUTE ein konkretes XML-Workout aus.";

const QUICK_ACTIONS = [
  { label: "Pro Analyse", display: "Pro Analyse", msg: "Analysiere meine aktuellen Leistungsdaten (CTL, ATL, TSB, HRV, Check-in) und erstelle eine kurze Einschätzung meiner Form. Empfehle dann genau eine passende Trainingseinheit als XML-Workout." },
  { label: "2h Zone 2", display: "2h Zone 2", msg: "Ich will eine 2-stündige Zone-2-Ausfahrt. Erstelle XML-Workout." },
  { label: "Kurze Intervalle", display: "Kurze Intervalle", msg: "Kurze 30/30 Intervalle – erstelle HIT-Workout als XML." },
  { label: "Recovery Tipps", display: "Recovery Tipps", msg: "Gib mir Regenerationsempfehlungen basierend auf meinen aktuellen Daten. Kein XML nötig." },
  { label: "FTP Test", display: "FTP Test", msg: "Erstelle ein 20-Minuten FTP-Test-Protokoll als XML-Workout." },
];

const STORAGE_KEY = "skywalker_wochenplan";

export default function CoachScreen() {
  const [messages, setMessages] = useState([
    { role: "coach", text: "Hallo! Ich bin Skywalker, dein persönlicher Radsport-Coach. Wie kann ich dir heute helfen?" }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [planLoading, setPlanLoading] = useState(false);
  const [wochenplan, setWochenplan] = useState(() => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || null; } catch { return null; }
  });
  const [planCollapsed, setPlanCollapsed] = useState(true);
  const [intervalsWorkouts, setIntervalsWorkouts] = useState(null);
  const [intervalsCollapsed, setIntervalsCollapsed] = useState(true);
  const scrollRef = useRef(null);

  useEffect(() => {
    api.intervalsplan()
      .then(data => setIntervalsWorkouts(data.workouts || []))
      .catch(() => setIntervalsWorkouts(null)); // silently hide if not configured
  }, []);

  const fetchWochenplan = async () => {
    if (planLoading) return;
    setPlanLoading(true);
    try {
      const result = await api.askCoach(WOCHENPLAN_MSG);
      const plan = { text: result.briefing, xml: result.xml, xml_valid: result.xml_valid, date: new Date().toLocaleDateString("de-DE") };
      setWochenplan(plan);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(plan));
      setPlanCollapsed(false);
    } catch (e) {
      Alert.alert("Fehler", e.message);
    } finally {
      setPlanLoading(false);
    }
  };

  const send = async (msg, displayMsg) => {
    if (!msg.trim() || loading) return;
    const userMsg = msg.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: displayMsg || userMsg }]);
    setLoading(true);

    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);

    try {
      const result = await api.askCoach(userMsg);
      const coachMsg = {
        role: "coach",
        text: result.briefing,
        xml: result.xml,
        xml_valid: result.xml_valid,
      };
      setMessages((prev) => [...prev, coachMsg]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: "coach", text: `Fehler: ${e.message}` }]);
    } finally {
      setLoading(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 200);
    }
  };

  const getFilename = (xml) => {
    // Direkt den <name>-Tag auslesen den der Coach setzt
    const nameMatch = xml && xml.match(/<name>(.*?)<\/name>/i);
    if (nameMatch) {
      return nameMatch[1].trim().replace(/\s+/g, "_").replace(/[^a-zA-Z0-9_äöüÄÖÜß]/g, "") || "skywalker_workout";
    }
    return "skywalker_workout";
  };

  const shareXML = (xml, briefing) => {
    try {
      const filename = getFilename(xml);
      const blob = new Blob([xml], { type: "application/xml" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${filename}.zwo`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      Alert.alert("Fehler", e.message);
    }
  };

  const downloadFormat = async (xml, format) => {
    try {
      const content = await api.downloadWorkout(xml, format);
      const ext = format === "tcx" ? "tcx" : format === "erg" ? "erg" : "txt";
      const mime = format === "tcx" ? "application/xml" : "text/plain";
      const filename = getFilename(xml);
      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${filename}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      Alert.alert("Fehler", e.message);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      {/* Wochenplan Karte */}
      <View style={styles.planCard}>
        <TouchableOpacity style={styles.planHeader} onPress={() => setPlanCollapsed(!planCollapsed)}>
          <Text style={styles.planTitle}>Wochenplan</Text>
          <View style={styles.planHeaderRight}>
            {wochenplan && <Text style={styles.planDate}>{wochenplan.date}</Text>}
            <TouchableOpacity
              style={[styles.planRefreshBtn, planLoading && { opacity: 0.5 }]}
              onPress={fetchWochenplan}
              disabled={planLoading}
            >
              {planLoading
                ? <ActivityIndicator color="#000" size="small" />
                : <Text style={styles.planRefreshText}>Neu laden</Text>
              }
            </TouchableOpacity>
            <Text style={styles.planChevron}>{planCollapsed ? "▼" : "▲"}</Text>
          </View>
        </TouchableOpacity>
        {!planCollapsed && (
          <ScrollView style={styles.planBody} nestedScrollEnabled>
            {wochenplan
              ? <>
                  <MarkdownBlock text={wochenplan.text} />
                  {wochenplan.xml && (
                    <View style={styles.downloadRow}>
                      <TouchableOpacity style={styles.xmlBtn} onPress={() => shareXML(wochenplan.xml)}>
                        <Text style={styles.xmlBtnText}>{wochenplan.xml_valid ? "Zwift (.zwo)" : "XML teilen"}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.xmlBtnAlt} onPress={() => shareXML(wochenplan.xml)}>
                        <Text style={styles.xmlBtnAltText}>Wahoo (.zwo)</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.xmlBtnAlt} onPress={() => downloadFormat(wochenplan.xml, "tcx")}>
                        <Text style={styles.xmlBtnAltText}>Garmin (.tcx)</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                </>
              : <Text style={styles.planEmpty}>Noch kein Wochenplan – auf "Neu laden" tippen.</Text>
            }
          </ScrollView>
        )}
      </View>

      {/* intervals.icu Wochenplan */}
      {intervalsWorkouts && intervalsWorkouts.length > 0 && (
        <View style={styles.intervalsCard}>
          <TouchableOpacity style={styles.intervalsHeader} onPress={() => setIntervalsCollapsed(!intervalsCollapsed)}>
            <Text style={styles.intervalsTitle}>Trainingsplan (intervals.icu)</Text>
            <Text style={[styles.planChevron, { color: "#ff4422" }]}>{intervalsCollapsed ? "▼" : "▲"}</Text>
          </TouchableOpacity>
          {!intervalsCollapsed && (
            <ScrollView style={styles.intervalsList} nestedScrollEnabled>
              {(() => {
                const today = new Date();
                const todayStr = today.toISOString().slice(0, 10);
                // Find Monday of current week
                const monday = new Date(today);
                monday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
                // Build 14-day grid (Mon this week + Mon next week)
                const byDate = {};
                intervalsWorkouts.forEach(w => {
                  if (!byDate[w.date]) byDate[w.date] = [];
                  byDate[w.date].push(w);
                });
                const rows = [];
                for (let week = 0; week < 2; week++) {
                  if (week === 1) rows.push({ divider: true });
                  for (let d = 0; d < 7; d++) {
                    const day = new Date(monday);
                    day.setDate(monday.getDate() + week * 7 + d);
                    const dateStr = day.toISOString().slice(0, 10);
                    const workouts = byDate[dateStr] || [];
                    rows.push({ dateStr, day, workouts });
                  }
                }
                return rows.map((row, i) => {
                  if (row.divider) return <View key={`div-${i}`} style={styles.intervalsDivider} />;
                  const { dateStr, day, workouts } = row;
                  const isToday = dateStr === todayStr;
                  const dayName = day.toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "numeric" });
                  if (workouts.length === 0) return (
                    <View key={dateStr} style={[styles.intervalsRow, isToday && styles.intervalsTodayRow]}>
                      <Text style={[styles.intervalsDay, isToday && styles.intervalsDayToday]}>{dayName}</Text>
                      <Text style={styles.intervalsSport}>  </Text>
                      <View style={styles.intervalsInfo}>
                        <Text style={styles.intervalsRest}>Ruhe</Text>
                      </View>
                    </View>
                  );
                  return workouts.map((w, wi) => {
                    const sportIcon = w.sport?.toLowerCase().includes("ride") || w.sport?.toLowerCase().includes("cycling") ? "🚴"
                      : w.sport?.toLowerCase().includes("run") ? "🏃"
                      : w.sport?.toLowerCase().includes("swim") ? "🏊"
                      : w.category === "NOTE" ? "📝" : "📋";
                    return (
                      <View key={`${dateStr}-${wi}`} style={[styles.intervalsRow, isToday && styles.intervalsTodayRow]}>
                        <Text style={[styles.intervalsDay, isToday && styles.intervalsDayToday]}>{wi === 0 ? dayName : ""}</Text>
                        <Text style={styles.intervalsSport}>{sportIcon}</Text>
                        <View style={styles.intervalsInfo}>
                          <Text style={[styles.intervalsName, isToday && styles.intervalsNameToday]} numberOfLines={1}>{w.name || "—"}</Text>
                          {w.duration_mins && <Text style={styles.intervalsDur}>{w.duration_mins} min</Text>}
                        </View>
                        {w.load && <Text style={styles.intervalsLoad}>{w.load} TSS</Text>}
                      </View>
                    );
                  });
                });
              })()}
            </ScrollView>
          )}
        </View>
      )}

      {/* Quick Action Buttons */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.quickBar}
        contentContainerStyle={{ paddingHorizontal: 10 }}
      >
        {QUICK_ACTIONS.map((a) => (
          <TouchableOpacity key={a.label} style={styles.quickBtn} onPress={() => send(a.msg, a.display)}>
            <Text style={styles.quickBtnText}>{a.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Chat */}
      <ScrollView
        ref={scrollRef}
        style={styles.chat}
        contentContainerStyle={{ padding: 15 }}
      >
        {messages.map((m, i) => (
          <View key={i} style={[styles.bubble, m.role === "user" ? styles.bubbleUser : styles.bubbleCoach]}>
            {m.role === "coach" && (
              <Text style={styles.bubbleName}>⚡ Skywalker</Text>
            )}
            {m.role === "coach" ? (
              <MarkdownBlock text={m.text} />
            ) : (
              <Text style={styles.bubbleTextUser}>{m.text}</Text>
            )}
            {m.xml && (
              <View style={styles.downloadRow}>
                <TouchableOpacity style={styles.xmlBtn} onPress={() => shareXML(m.xml, m.text)}>
                  <Text style={styles.xmlBtnText}>
                    {m.xml_valid ? "📥 Zwift (.zwo)" : "⚠️ XML teilen"}
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.xmlBtnAlt} onPress={() => shareXML(m.xml, m.text)}>
                  <Text style={styles.xmlBtnAltText}>🚴 Wahoo (.zwo)</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.xmlBtnAlt} onPress={() => downloadFormat(m.xml, "tcx")}>
                  <Text style={styles.xmlBtnAltText}>⌚ Garmin (.tcx)</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        ))}
        {loading && (
          <View style={styles.bubbleCoach}>
            <Text style={styles.bubbleName}>⚡ Skywalker</Text>
            <ActivityIndicator color="#00C853" size="small" />
            <Text style={styles.thinkingText}>Analysiere deine Daten…</Text>
          </View>
        )}
      </ScrollView>

      {/* Input */}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          placeholder="Frag deinen Coach…"
          placeholderTextColor="#555"
          value={input}
          onChangeText={setInput}
          onSubmitEditing={() => send(input)}
          returnKeyType="send"
          multiline
        />
        <TouchableOpacity
          style={[styles.sendBtn, (!input.trim() || loading) && styles.sendBtnDisabled]}
          onPress={() => send(input)}
          disabled={!input.trim() || loading}
        >
          <Text style={styles.sendBtnText}>↑</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#111" },
  planCard: { margin: 10, marginBottom: 4, backgroundColor: "#1a1a1a", borderRadius: 12, borderWidth: 1, borderColor: "#00C853", overflow: "hidden", maxHeight: 420 },
  planHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 12, backgroundColor: "#0d2b1a" },
  planTitle: { color: "#00C853", fontSize: 14, fontWeight: "900", letterSpacing: 0.5 },
  planHeaderRight: { flexDirection: "row", alignItems: "center", gap: 8 },
  planDate: { color: "#557a60", fontSize: 11 },
  planRefreshBtn: { backgroundColor: "#00C853", borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  planRefreshText: { color: "#000", fontSize: 11, fontWeight: "700" },
  planChevron: { color: "#00C853", fontSize: 12, marginLeft: 4 },
  planBody: { padding: 12, maxHeight: 340 },
  planEmpty: { color: "#555", fontSize: 13, textAlign: "center", paddingVertical: 20 },
  intervalsCard: { marginHorizontal: 10, marginBottom: 4, backgroundColor: "#1a1a1a", borderRadius: 12, borderWidth: 1, borderColor: "#cc2200", overflow: "hidden", maxHeight: 280 },
  intervalsHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 12, paddingVertical: 9, backgroundColor: "#2e0d0d" },
  intervalsTitle: { color: "#ff4422", fontSize: 13, fontWeight: "800" },
  intervalsList: { maxHeight: 210 },
  intervalsRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: "#222", gap: 8 },
  intervalsTodayRow: { backgroundColor: "#2e0d0d" },
  intervalsDay: { color: "#888", fontSize: 11, fontWeight: "600", width: 62 },
  intervalsDayToday: { color: "#ff4422", fontWeight: "800" },
  intervalsSport: { fontSize: 14, width: 20 },
  intervalsInfo: { flex: 1 },
  intervalsName: { color: "#ccc", fontSize: 12, fontWeight: "600" },
  intervalsNameToday: { color: "#fff", fontWeight: "700" },
  intervalsDur: { color: "#666", fontSize: 11, marginTop: 1 },
  intervalsLoad: { color: "#aa6655", fontSize: 11, fontWeight: "600", minWidth: 48, textAlign: "right" },
  intervalsRest: { color: "#444", fontSize: 12, fontStyle: "italic" },
  intervalsDivider: { height: 1, backgroundColor: "#2a0a0a", marginVertical: 2 },
  quickBar: { maxHeight: 56, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: "#222" },
  quickBtn: { backgroundColor: "#1a1a1a", borderRadius: 20, paddingHorizontal: 14, paddingVertical: 7, marginHorizontal: 4, borderWidth: 1, borderColor: "#00C853" },
  quickBtnText: { color: "#00C853", fontSize: 13, fontWeight: "600" },
  chat: { flex: 1 },
  bubble: { borderRadius: 14, padding: 12, marginBottom: 10, maxWidth: "88%" },
  bubbleCoach: { backgroundColor: "#1a1a1a", alignSelf: "flex-start" },
  bubbleUser: { backgroundColor: "#00C853", alignSelf: "flex-end" },
  bubbleName: { color: "#00C853", fontSize: 11, fontWeight: "700", marginBottom: 5, letterSpacing: 0.8 },
  bubbleText: { color: "#ddd", fontSize: 14, lineHeight: 20 },
  bubbleTextUser: { color: "#000" },
  thinkingText: { color: "#555", fontSize: 12, marginTop: 6 },
  downloadRow: { marginTop: 10, flexDirection: "row", gap: 6, flexWrap: "wrap" },
  xmlBtn: { flex: 1, minWidth: 120, backgroundColor: "#003d1a", borderRadius: 8, padding: 10, borderWidth: 1, borderColor: "#00C853" },
  xmlBtnText: { color: "#00C853", fontSize: 12, fontWeight: "700", textAlign: "center" },
  xmlBtnAlt: { flex: 1, minWidth: 100, backgroundColor: "#1a1a2e", borderRadius: 8, padding: 10, borderWidth: 1, borderColor: "#4a4a8a" },
  xmlBtnAltText: { color: "#a0a0ff", fontSize: 12, fontWeight: "700", textAlign: "center" },
  inputRow: { flexDirection: "row", padding: 10, borderTopWidth: 1, borderTopColor: "#222", backgroundColor: "#111" },
  input: { flex: 1, backgroundColor: "#1a1a1a", borderRadius: 20, paddingHorizontal: 16, paddingVertical: 10, color: "#fff", fontSize: 14, maxHeight: 100 },
  sendBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#00C853", justifyContent: "center", alignItems: "center", marginLeft: 8, alignSelf: "flex-end" },
  sendBtnDisabled: { backgroundColor: "#1a3d22" },
  sendBtnText: { color: "#000", fontSize: 20, fontWeight: "800" },
});
