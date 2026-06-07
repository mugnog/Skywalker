import React, { useState, useCallback } from "react";
import { useFocusEffect } from "@react-navigation/native";
import { useVisibilityRefresh } from "../hooks/useVisibilityRefresh";
import {
  View, Text, StyleSheet, ScrollView,
  TouchableOpacity, ActivityIndicator, Alert,
} from "react-native";
import { api } from "../services/api";

const FIELDS = [
  { key: "schlaf",     label: "😴 Schlaf"     },
  { key: "energie",    label: "⚡ Energie"     },
  { key: "gesundheit", label: "❤️ Gesundheit" },
  { key: "muskeln",    label: "💪 Muskeln"     },
  { key: "mental",     label: "🧠 Mental"      },
  { key: "ernahrung",  label: "🥗 Ernährung"   },
];

function computeReadiness(vals) {
  const avg = (vals.schlaf + vals.energie + vals.gesundheit + vals.muskeln + vals.mental + vals.ernahrung) / 6;
  const score = Math.round(avg * 10) / 10;
  let label = "REST DAY 🛋️";
  if (score >= 8.5)    label = "RACE READY 🔥";
  else if (score >= 7) label = "SOLID 💪";
  else if (score >= 5.5) label = "OK 🙂";
  else if (score >= 4) label = "TIRED 😴";
  return { score, label };
}

function numColor(v) {
  if (v >= 8) return "#00C853";
  if (v >= 6) return "#FFD600";
  if (v >= 4) return "#FF6D00";
  return "#FF1744";
}

function NumberRow({ value, onChange }) {
  return (
    <View style={styles.numRow}>
      {[1,2,3,4,5,6,7,8,9,10].map((n) => {
        const active = value === n;
        const color = numColor(n);
        return (
          <TouchableOpacity
            key={n}
            style={[styles.numBtn, active && { backgroundColor: color, borderColor: color }]}
            onPress={() => onChange(n)}
            activeOpacity={0.7}
          >
            <Text style={[styles.numText, active && styles.numTextActive]}>
              {n}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

export default function CheckinScreen({ onCheckinSaved }) {
  const today = new Date().toISOString().slice(0, 10);
  const [values, setValues] = useState(
    Object.fromEntries(FIELDS.map((f) => [f.key, 7]))
  );
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [readiness, setReadiness] = useState(null);

  // Post-workout matrix
  const [rpe, setRpe] = useState(null);
  const [feel, setFeel] = useState(null);
  const [matrixSaving, setMatrixSaving] = useState(false);
  const [matrixSaved, setMatrixSaved] = useState(false);
  const [coachComment, setCoachComment] = useState(null);
  const [coachLoading, setCoachLoading] = useState(false);

  const loadCheckin = useCallback(() => {
    setLoading(true);
    api.checkinToday().then((d) => {
      if (d.exists) {
        const loaded = {};
        FIELDS.forEach((f) => { loaded[f.key] = d[f.key] ?? 7; });
        setValues(loaded);
        setSaved(true);
        setReadiness(computeReadiness(loaded));
      } else {
        setValues(Object.fromEntries(FIELDS.map((f) => [f.key, 7])));
        setSaved(false);
        setReadiness(null);
      }
      if (d.rpe != null) { setRpe(d.rpe); setMatrixSaved(true); }
      else { setRpe(null); setMatrixSaved(false); }
      if (d.feel != null) setFeel(d.feel);
      else setFeel(null);
      setCoachComment(null);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  useFocusEffect(loadCheckin);
  useVisibilityRefresh(loadCheckin);

  const readinessColor = (score) => {
    if (score >= 8) return "#00C853";
    if (score >= 6) return "#FFD600";
    return "#FF1744";
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.saveCheckin({ date: today, ...values });
      setReadiness(computeReadiness(values));
      setSaved(true);
      onCheckinSaved?.();
      Alert.alert("✅ Gespeichert", "Check-in erfolgreich gespeichert.");
    } catch (e) {
      Alert.alert("Fehler", e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveMatrix = async () => {
    if (rpe === null || feel === null) {
      Alert.alert("Bitte beide Werte auswählen", "RPE und Gefühl werden benötigt.");
      return;
    }
    setMatrixSaving(true);
    setMatrixSaved(false);
    try {
      await api.saveMatrix({ date: today, rpe, feel });
      setMatrixSaved(true);
      // Auto coach comment
      setCoachLoading(true);
      try {
        const result = await api.askCoach(
          `Ich habe gerade ein Training mit RPE ${rpe}/10 und Wohlbefinden ${feel}/10 abgeschlossen. Gib mir ein kurzes Coaching-Feedback (2-3 Sätze, kein XML).`
        );
        setCoachComment(result.briefing);
      } catch (_) {
        setCoachComment("Training gespeichert. Gut gemacht! 💪");
      } finally {
        setCoachLoading(false);
      }
    } catch (e) {
      Alert.alert("Fehler", e.message);
    } finally {
      setMatrixSaving(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#00C853" />
      </View>
    );
  }

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Morgen-Check-in</Text>
      <Text style={styles.date}>{today}</Text>

      {saved && readiness && (
        <View style={[styles.readinessBanner, { borderColor: readinessColor(readiness.score) }]}>
          <Text style={[styles.readinessLabel, { color: readinessColor(readiness.score) }]}>
            {readiness.label}
          </Text>
          <Text style={styles.readinessSub}>Readiness Score: {readiness.score ?? "–"}/10</Text>
        </View>
      )}

      {FIELDS.map((field) => (
        <View key={field.key} style={styles.fieldBlock}>
          <View style={styles.fieldHeader}>
            <Text style={styles.fieldLabel}>{field.label}</Text>
            <Text style={[styles.fieldValue, { color: numColor(values[field.key]) }]}>
              {values[field.key]}
            </Text>
          </View>
          <NumberRow
            value={values[field.key]}
            onChange={(v) => setValues((prev) => ({ ...prev, [field.key]: v }))}
          />
          <View style={styles.fieldHints}>
            <Text style={styles.hint}>Schlecht</Text>
            <Text style={styles.hint}>Gut</Text>
          </View>
        </View>
      ))}

      <TouchableOpacity
        style={[styles.saveBtn, saving && styles.saveBtnDisabled]}
        onPress={handleSave}
        disabled={saving}
      >
        {saving
          ? <ActivityIndicator color="#000" />
          : <Text style={styles.saveBtnText}>💾 Check-in speichern</Text>
        }
      </TouchableOpacity>

      {/* Post-Workout Bewertung */}
      <View style={styles.matrixCard}>
        <Text style={styles.matrixTitle}>🏋️ Post-Workout Bewertung</Text>
        <Text style={styles.matrixSub}>Nach dem Training ausfüllen</Text>

        <Text style={styles.fieldLabel}>💪 Anstrengung (RPE)</Text>
        <NumberRow value={rpe} onChange={setRpe} />

        <Text style={[styles.fieldLabel, { marginTop: 14 }]}>😊 Wohlbefinden nach Training</Text>
        <NumberRow value={feel} onChange={setFeel} />

        <TouchableOpacity
          style={[styles.matrixBtn, (matrixSaving || coachLoading) && styles.saveBtnDisabled]}
          onPress={handleSaveMatrix}
          disabled={matrixSaving || coachLoading}
        >
          {matrixSaving || coachLoading
            ? <ActivityIndicator color="#000" />
            : <Text style={styles.matrixBtnText}>
                {matrixSaved ? "✅ Gespeichert – erneut senden" : "Speichern & Coach-Feedback"}
              </Text>
          }
        </TouchableOpacity>

        {coachComment && (
          <View style={styles.coachBubble}>
            <Text style={styles.coachBubbleName}>⚡ Skywalker</Text>
            <Text style={styles.coachBubbleText}>{coachComment}</Text>
          </View>
        )}
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#111" },
  center: { flex: 1, backgroundColor: "#111", justifyContent: "center", alignItems: "center" },
  title: { color: "#fff", fontSize: 24, fontWeight: "800", margin: 20, marginTop: 60 },
  date: { color: "#555", fontSize: 13, marginLeft: 20, marginBottom: 10 },
  readinessBanner: { marginHorizontal: 15, marginBottom: 15, borderRadius: 12, borderWidth: 2, padding: 14, alignItems: "center", backgroundColor: "#1a1a1a" },
  readinessLabel: { fontSize: 22, fontWeight: "800" },
  readinessSub: { color: "#666", fontSize: 12, marginTop: 4 },
  fieldBlock: { backgroundColor: "#1a1a1a", marginHorizontal: 15, marginBottom: 10, borderRadius: 12, padding: 14 },
  fieldHeader: { flexDirection: "row", justifyContent: "space-between", marginBottom: 10 },
  fieldLabel: { color: "#ccc", fontSize: 15, fontWeight: "600" },
  fieldValue: { fontSize: 18, fontWeight: "800" },
  numRow: { flexDirection: "row", justifyContent: "space-between" },
  numBtn: {
    width: 28, height: 34, borderRadius: 7,
    borderWidth: 1, borderColor: "#333",
    backgroundColor: "#262626",
    justifyContent: "center", alignItems: "center",
  },
  numText: { color: "#555", fontSize: 13, fontWeight: "700" },
  numTextActive: { color: "#000" },
  fieldHints: { flexDirection: "row", justifyContent: "space-between", marginTop: 6 },
  hint: { color: "#444", fontSize: 10 },
  saveBtn: { backgroundColor: "#00C853", marginHorizontal: 15, marginTop: 20, borderRadius: 12, padding: 16, alignItems: "center" },
  saveBtnDisabled: { opacity: 0.5 },
  saveBtnText: { color: "#000", fontWeight: "800", fontSize: 16 },
  matrixCard: { backgroundColor: "#1a1a1a", marginHorizontal: 15, marginTop: 20, borderRadius: 12, padding: 16 },
  matrixTitle: { color: "#fff", fontSize: 17, fontWeight: "800", marginBottom: 2 },
  matrixSub: { color: "#444", fontSize: 12, marginBottom: 16 },
  fieldLabel: { color: "#555", fontSize: 11, fontWeight: "700", letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 8 },
  matrixBtn: { backgroundColor: "#00C853", borderRadius: 10, padding: 14, alignItems: "center", marginTop: 16 },
  matrixBtnText: { color: "#000", fontWeight: "800", fontSize: 14 },
  coachBubble: { backgroundColor: "#111", borderRadius: 10, padding: 12, marginTop: 14, borderWidth: 1, borderColor: "#00C853" },
  coachBubbleName: { color: "#00C853", fontSize: 11, fontWeight: "700", marginBottom: 6, letterSpacing: 0.8 },
  coachBubbleText: { color: "#ccc", fontSize: 13, lineHeight: 20 },
});
