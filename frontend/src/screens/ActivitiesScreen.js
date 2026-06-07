import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, FlatList,
  RefreshControl, ActivityIndicator,
  TouchableOpacity, Modal,
} from "react-native";
import { api } from "../services/api";

function MatrixField({ initialRpe, initialFeel, onChange }) {
  const containerRef = React.useRef(null);
  const dimsRef = React.useRef({ w: 300, h: 220 });
  const onChangeRef = React.useRef(onChange);
  onChangeRef.current = onChange;
  const isDragging = React.useRef(false);

  const [cursor, setCursor] = useState(() => ({
    xPct: initialRpe  != null ? (initialRpe  - 1) / 9       : 0.5,
    yPct: initialFeel != null ? 1 - (initialFeel - 1) / 9   : 0.5,
  }));

  const updateFromClient = React.useCallback((clientX, clientY) => {
    const el = containerRef.current;
    if (!el || typeof el.getBoundingClientRect !== "function") return;
    const rect = el.getBoundingClientRect();
    const { w, h } = dimsRef.current;
    const xPct = Math.max(0.02, Math.min(0.98, (clientX - rect.left) / w));
    const yPct = Math.max(0.02, Math.min(0.98, (clientY - rect.top)  / h));
    const rpe  = Math.max(1, Math.min(10, Math.round(xPct * 9 + 1)));
    const feel = Math.max(1, Math.min(10, Math.round((1 - yPct) * 9 + 1)));
    setCursor({ xPct, yPct });
    onChangeRef.current(rpe, feel);
  }, []);

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof el.addEventListener !== "function") return;

    const onMouseDown = (e) => { isDragging.current = true;  updateFromClient(e.clientX, e.clientY); };
    const onMouseMove = (e) => { if (isDragging.current) updateFromClient(e.clientX, e.clientY); };
    const onMouseUp   = ()  => { isDragging.current = false; };

    const onTouchStart = (e) => { const t = e.touches[0]; if (t) updateFromClient(t.clientX, t.clientY); };
    const onTouchMove  = (e) => { e.preventDefault(); const t = e.touches[0]; if (t) updateFromClient(t.clientX, t.clientY); };
    const onTouchEnd   = ()  => {};

    el.addEventListener("mousedown",  onMouseDown);
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup",   onMouseUp);
    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove",  onTouchMove,  { passive: false });
    el.addEventListener("touchend",   onTouchEnd);

    return () => {
      el.removeEventListener("mousedown",  onMouseDown);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup",   onMouseUp);
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove",  onTouchMove);
      el.removeEventListener("touchend",   onTouchEnd);
    };
  }, [updateFromClient]);

  return (
    <View
      ref={containerRef}
      onLayout={(e) => {
        const { width, height } = e.nativeEvent.layout;
        dimsRef.current = { w: width, h: height };
      }}
      style={{
        height: 220,
        borderRadius: 12,
        overflow: "hidden",
        position: "relative",
        cursor: "crosshair",
        backgroundColor: "#1a1a1a",
        backgroundImage: [
          "radial-gradient(ellipse at 100% 0%,   rgba(183,28,28,0.45) 0%, transparent 60%)",  // oben-rechts: Schwer + Schlecht = Rot
          "radial-gradient(ellipse at 0%   0%,   rgba(230,81,0,0.3)   0%, transparent 60%)",  // oben-links:  Einfach + Schlecht = Orange
          "radial-gradient(ellipse at 0%   100%, rgba(27,94,32,0.5)   0%, transparent 60%)",  // unten-links: Einfach + Sehr gut = Grün
          "radial-gradient(ellipse at 100% 100%, rgba(0,131,143,0.3)  0%, transparent 60%)",  // unten-rechts: Schwer + Sehr gut = Teal
        ].join(", "),
      }}
    >
      {/* Hilfslinien */}
      {["25%", "50%", "75%"].map((pct) => (
        <React.Fragment key={pct}>
          <View pointerEvents="none" style={{ position: "absolute", top: pct, left: 0, right: 0, height: 1, backgroundColor: "rgba(255,255,255,0.08)" }} />
          <View pointerEvents="none" style={{ position: "absolute", left: pct, top: 0, bottom: 0, width: 1, backgroundColor: "rgba(255,255,255,0.08)" }} />
        </React.Fragment>
      ))}

      {/* Fadenkreuz */}
      {cursor && (
        <>
          <View pointerEvents="none" style={{ position: "absolute", left: `${cursor.xPct * 100}%`, top: 0, bottom: 0, width: 1.5, backgroundColor: "#00f2ff", opacity: 0.85 }} />
          <View pointerEvents="none" style={{ position: "absolute", top: `${cursor.yPct * 100}%`, left: 0, right: 0, height: 1.5, backgroundColor: "#00f2ff", opacity: 0.85 }} />
          <View pointerEvents="none" style={{
            position: "absolute",
            left: `${cursor.xPct * 100}%`, top: `${cursor.yPct * 100}%`,
            marginLeft: -12, marginTop: -12,
            width: 24, height: 24, borderRadius: 12,
            backgroundColor: "#00f2ff", borderWidth: 2.5, borderColor: "#fff",
          }} />
        </>
      )}
    </View>
  );
}

function MatrixModal({ item, initialRpe, initialFeel, onSave, onClose }) {
  const [rpe,  setRpe]  = useState(initialRpe  ?? 5);
  const [feel, setFeel] = useState(initialFeel ?? 5);
  const [saving, setSaving] = useState(false);

  const handleChange = (newRpe, newFeel) => { setRpe(newRpe); setFeel(newFeel); };

  const handleSave = async () => {
    if (rpe == null) return;
    setSaving(true);
    try { await onSave(item.date, item.name, rpe, feel); }
    finally { setSaving(false); }
  };

  const hasSelection = true;

  // Score: Mittelwert aus RPE-Komponente und Feel-Komponente, beide skaliert auf 0.4–3.6
  const calcScore = (r, f) => {
    const rpeComp  = (r - 1) / 9 * 3.2 + 0.4;   // Einfach(1)→0.4, Schwer(10)→3.6
    const feelComp = (10 - f) / 9 * 3.2 + 0.4;   // Sehr gut(10)→0.4, Schlecht(1)→3.6
    return ((rpeComp + feelComp) / 2).toFixed(1);
  };

  const getColor = (score) => {
    const s = parseFloat(score);
    if (s <= 1.5) return "#00C853";
    if (s <= 2.5) return "#FFD600";
    return "#FF1744";
  };

  return (
    <Modal transparent animationType="fade" onRequestClose={onClose}>
      <View style={ms.overlay}>
        <View style={ms.card}>
          <Text style={ms.actName} numberOfLines={1}>{item.name}</Text>
          <Text style={ms.actDate}>{item.date}</Text>

          {/* Y-Achse + interaktives Feld */}
          <View style={ms.fieldRow}>
            <View style={ms.yAxis}>
              <Text style={ms.yLabel}>Schlecht</Text>
              <View style={ms.yBar} />
              <Text style={ms.yLabel}>Sehr{"\n"}gut</Text>
            </View>
            <View style={{ flex: 1 }}>
              <MatrixField
                initialRpe={initialRpe}
                initialFeel={initialFeel}
                onChange={handleChange}
              />
            </View>
          </View>

          {/* X-Achse */}
          <View style={ms.xAxis}>
            <Text style={ms.xLabel}>Einfach</Text>
            <View style={ms.xBar} />
            <Text style={ms.xLabel}>Schwer</Text>
          </View>

          {/* Score-Anzeige */}
          {hasSelection ? (() => {
            const score = calcScore(rpe, feel);
            const color = getColor(score);
            return (
              <View style={ms.selRow}>
                <View style={[ms.scoreCircle, { borderColor: color }]}>
                  <Text style={[ms.scoreNum, { color }]}>{score}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={ms.scoreTitle}>Score</Text>
                  <Text style={[ms.selText, { color: "#888" }]}>
                    Intensität {rpe}/10 · Gefühl {feel}/10
                  </Text>
                </View>
              </View>
            );
          })() : (
            <Text style={ms.selHint}>Auf das Feld tippen</Text>
          )}

          {/* Buttons */}
          <View style={ms.btns}>
            <TouchableOpacity style={ms.cancelBtn} onPress={onClose}>
              <Text style={ms.cancelTxt}>Abbrechen</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[ms.saveBtn, (!hasSelection || saving) && ms.saveBtnDisabled]}
              onPress={handleSave}
              disabled={!hasSelection || saving}
            >
              {saving
                ? <ActivityIndicator size="small" color="#000" />
                : <Text style={ms.saveTxt}>Speichern</Text>
              }
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

export default function ActivitiesScreen() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [modalItem, setModalItem] = useState(null);
  const [savedRatings, setSavedRatings] = useState({});

  const load = async () => {
    try {
      const [d, matrix] = await Promise.all([api.activities(50), api.getMatrix()]);
      setData(d);
      // Matrix is per-date; find the matching activity name for each rated date
      const ratings = {};
      for (const entry of matrix) {
        const act = d.find((a) => a.date === entry.date);
        if (act) {
          ratings[`${entry.date}_${act.name}`] = { rpe: entry.rpe, feel: entry.feel };
        }
      }
      setSavedRatings(ratings);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (item) => {
    const ok = window.confirm(`"${item.name}" vom ${item.date} löschen?`);
    if (!ok) return;
    const key = `${item.date}_${item.name}`;
    setDeleting(key);
    try {
      await api.deleteActivity(item.date, item.name);
      setData((prev) => prev.filter((a) => !(a.date === item.date && a.name === item.name)));
    } catch (e) {
      window.alert("Fehler: " + e.message);
    } finally {
      setDeleting(null);
    }
  };

  const handleSave = async (date, name, rpe, feel) => {
    await api.saveMatrix({ date, rpe, feel });
    const key = `${date}_${name}`;
    setSavedRatings((prev) => ({ ...prev, [key]: { rpe, feel } }));
    setModalItem(null);
  };

  if (loading) {
    return <View style={styles.center}><ActivityIndicator color="#00C853" /></View>;
  }

  const renderItem = ({ item }) => {
    const key = `${item.date}_${item.name}`;
    const isDeleting = deleting === key;
    const saved = savedRatings[`${item.date}_${item.name}`];
    const tss = item.tss ? Math.round(item.tss) : "–";
    const np  = item.norm_power ? `${Math.round(item.norm_power)}W` : "–";
    const hr  = item.avg_hr ? `${Math.round(item.avg_hr)}` : "–";
    const km  = item.distance ? `${item.distance.toFixed(1)}km` : "–";

    return (
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.actName} numberOfLines={1}>{item.name}</Text>
          <View style={styles.headerRight}>
            <Text style={styles.actDate}>{item.date}</Text>
            <TouchableOpacity
              style={[styles.rateBtn, saved && styles.rateBtnSaved]}
              onPress={() => setModalItem(item)}
            >
              <Text style={[styles.rateBtnText, saved && styles.rateBtnTextSaved]}>
                {saved ? "✓" : "★"}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.deleteBtn} onPress={() => handleDelete(item)} disabled={isDeleting}>
              {isDeleting
                ? <ActivityIndicator size="small" color="#FF1744" />
                : <Text style={styles.deleteBtnText}>🗑️</Text>
              }
            </TouchableOpacity>
          </View>
        </View>
        <View style={styles.cardStats}>
          <Stat label="TSS" value={tss} color="#FF6D00" />
          <Stat label="NP"  value={np}  color="#00f2ff" />
          <Stat label="Ø HR" value={hr} color="#FF1744" />
          <Stat label="Dist" value={km} color="#00C853" />
        </View>
      </View>
    );
  };

  return (
    <>
      <FlatList
        data={data}
        keyExtractor={(item, i) => `${item.date}_${item.name}_${i}`}
        renderItem={renderItem}
        style={styles.container}
        contentContainerStyle={{ padding: 15, paddingTop: 60 }}
        ListHeaderComponent={<Text style={styles.title}>🚴 Aktivitäten ({data.length})</Text>}
        ListEmptyComponent={<Text style={styles.empty}>Keine Aktivitäten gefunden.</Text>}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor="#00C853" />
        }
      />
      {modalItem && (
        <MatrixModal
          item={modalItem}
          initialRpe={savedRatings[modalItem.date]?.rpe ?? null}
          initialFeel={savedRatings[modalItem.date]?.feel ?? null}
          onSave={handleSave}
          onClose={() => setModalItem(null)}
        />
      )}
    </>
  );
}

function Stat({ label, value, color }) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#111" },
  center: { flex: 1, backgroundColor: "#111", justifyContent: "center", alignItems: "center" },
  title: { color: "#fff", fontSize: 24, fontWeight: "800", marginBottom: 15 },
  empty: { color: "#555", textAlign: "center", marginTop: 40 },
  card: { backgroundColor: "#1a1a1a", borderRadius: 12, padding: 14, marginBottom: 10 },
  cardHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 },
  actName: { color: "#fff", fontWeight: "700", fontSize: 14, flex: 1, marginRight: 10 },
  headerRight: { flexDirection: "row", alignItems: "center", gap: 8 },
  actDate: { color: "#888", fontSize: 14, fontWeight: "600" },
  rateBtn: { backgroundColor: "#1f1f00", borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, borderWidth: 1, borderColor: "#FFD600" },
  rateBtnSaved: { backgroundColor: "#003d1a", borderColor: "#00C853" },
  rateBtnText: { color: "#FFD600", fontSize: 11, fontWeight: "700" },
  rateBtnTextSaved: { color: "#00C853" },
  deleteBtn: { padding: 4 },
  deleteBtnText: { fontSize: 16 },
  cardStats: { flexDirection: "row", justifyContent: "space-around" },
  stat: { alignItems: "center" },
  statValue: { fontSize: 16, fontWeight: "800" },
  statLabel: { color: "#555", fontSize: 10, marginTop: 2, textTransform: "uppercase" },
});

const ms = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.88)", justifyContent: "center", alignItems: "center", padding: 20 },
  card: { backgroundColor: "#111", borderRadius: 16, padding: 20, width: "100%", maxWidth: 400 },
  actName: { color: "#fff", fontSize: 16, fontWeight: "800", marginBottom: 2 },
  actDate: { color: "#555", fontSize: 12, marginBottom: 16 },
  fieldRow: { flexDirection: "row", alignItems: "stretch", gap: 10 },
  yAxis: { width: 44, justifyContent: "space-between", alignItems: "center" },
  yLabel: { color: "#555", fontSize: 10, fontWeight: "600", textAlign: "center" },
  yBar: { flex: 1, width: 2, backgroundColor: "#2a2a2a", borderRadius: 1, marginVertical: 4 },
  xAxis: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 8, marginLeft: 54 },
  xLabel: { color: "#555", fontSize: 10, fontWeight: "600" },
  xBar: { flex: 1, height: 2, backgroundColor: "#2a2a2a", borderRadius: 1 },
  selRow: { flexDirection: "row", alignItems: "center", gap: 14, marginTop: 14 },
  scoreCircle: { width: 54, height: 54, borderRadius: 27, borderWidth: 2.5, justifyContent: "center", alignItems: "center", backgroundColor: "#1a1a1a" },
  scoreNum: { fontSize: 18, fontWeight: "900" },
  scoreTitle: { color: "#555", fontSize: 10, fontWeight: "700", textTransform: "uppercase", letterSpacing: 1, marginBottom: 3 },
  selText: { fontSize: 13, color: "#888" },
  selHint: { color: "#444", fontSize: 12, textAlign: "center", marginTop: 14 },
  btns: { flexDirection: "row", gap: 10, marginTop: 18 },
  cancelBtn: { flex: 1, padding: 13, alignItems: "center", borderRadius: 10, borderWidth: 1, borderColor: "#333" },
  cancelTxt: { color: "#555", fontWeight: "700" },
  saveBtn: { flex: 1, backgroundColor: "#00C853", padding: 13, alignItems: "center", borderRadius: 10 },
  saveBtnDisabled: { backgroundColor: "#1a3d22" },
  saveTxt: { color: "#000", fontWeight: "800" },
});
