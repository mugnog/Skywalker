import React, { useState } from "react";
import {
  View, Text, StyleSheet, TextInput,
  TouchableOpacity, ActivityIndicator, ScrollView,
} from "react-native";
import { api } from "../services/api";

const GOALS = [
  { key: "ftp",       emoji: "⚡", label: "FTP steigern",     desc: "Mehr Watt, Intervalle & Sweet Spot" },
  { key: "endurance", emoji: "🚵", label: "Ausdauer",          desc: "Lange Zone-2-Fahrten, maximales Volumen" },
  { key: "weight",    emoji: "⚖️", label: "Abnehmen",          desc: "FatMax-Training, Fettverbrennung" },
  { key: "race",      emoji: "🏆", label: "Wettkampf",         desc: "Periodisierung & Peaking" },
  { key: "health",    emoji: "❤️", label: "Gesundheit",        desc: "Ausgewogen, Erholung hat Priorität" },
];

const FREQUENCIES = [
  { key: "low",  label: "1–2×",   desc: "pro Woche" },
  { key: "mid",  label: "3–5×",   desc: "pro Woche" },
  { key: "high", label: "Täglich", desc: "jeden Tag" },
];

const DAYS = [
  { key: "mon", label: "Mo" },
  { key: "tue", label: "Di" },
  { key: "wed", label: "Mi" },
  { key: "thu", label: "Do" },
  { key: "fri", label: "Fr" },
  { key: "sat", label: "Sa" },
  { key: "sun", label: "So" },
];

export default function GoalsScreen({ onDone }) {
  const [ftpTarget, setFtpTarget] = useState("250");
  const [selectedGoals, setSelectedGoals] = useState(["ftp"]);
  const [selectedFreq, setSelectedFreq] = useState("mid");
  const [selectedDays, setSelectedDays] = useState(["tue", "wed", "fri", "sat"]);
  const [eventName, setEventName] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Parse DD.MM.YYYY → YYYY-MM-DD
  const parseDate = (s) => {
    const m = s.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
    return m ? `${m[3]}-${m[2]}-${m[1]}` : null;
  };

  const handleSave = async () => {
    const val = parseInt(ftpTarget, 10);
    if (isNaN(val) || val < 100 || val > 600) {
      setError("Bitte einen realistischen Wert zwischen 100 und 600 W eingeben.");
      return;
    }
    if (selectedGoals.length === 0) {
      setError("Bitte mindestens ein Ziel auswählen.");
      return;
    }
    if (eventDate && !parseDate(eventDate)) {
      setError("Datum bitte im Format TT.MM.JJJJ eingeben.");
      return;
    }
    setSaving(true);
    try {
      await api.saveGoals(val);
      await api.saveProfile({
        training_goal: selectedGoals.join(","),
        training_frequency: selectedFreq,
        training_days: selectedDays.join(","),
        event_name: eventName || null,
        event_date: eventDate ? parseDate(eventDate) : null,
      });
      onDone(val, selectedGoals[0] || "ftp");
    } catch (e) {
      setError("Fehler: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <Text style={styles.emoji}>🎯</Text>
      <Text style={styles.title}>Dein Trainingsziel</Text>
      <Text style={styles.subtitle}>
        Skywalker passt deinen Trainingsplan und Coach-Empfehlungen an dein Ziel an.
      </Text>

      {/* Ziel-Auswahl */}
      <View style={styles.card}>
        <Text style={styles.label}>Was ist dein Hauptziel?</Text>
        {GOALS.map((g) => {
          const active = selectedGoals.includes(g.key);
          return (
            <TouchableOpacity
              key={g.key}
              style={[styles.goalBtn, active && styles.goalBtnActive]}
              onPress={() => setSelectedGoals((prev) =>
                prev.includes(g.key) ? prev.filter((x) => x !== g.key) : [...prev, g.key]
              )}
            >
              <Text style={styles.goalEmoji}>{g.emoji}</Text>
              <View style={styles.goalText}>
                <Text style={[styles.goalLabel, active && styles.goalLabelActive]}>
                  {g.label}
                </Text>
                <Text style={styles.goalDesc}>{g.desc}</Text>
              </View>
              {active && <Text style={styles.checkmark}>✓</Text>}
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Trainingsfrequenz */}
      <View style={styles.card}>
        <Text style={styles.label}>Wie oft trainierst du?</Text>
        <View style={styles.freqRow}>
          {FREQUENCIES.map((f) => (
            <TouchableOpacity
              key={f.key}
              style={[styles.freqBtn, selectedFreq === f.key && styles.freqBtnActive]}
              onPress={() => setSelectedFreq(f.key)}
            >
              <Text style={[styles.freqLabel, selectedFreq === f.key && styles.freqLabelActive]}>
                {f.label}
              </Text>
              <Text style={styles.freqDesc}>{f.desc}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Trainingstage */}
      <View style={styles.card}>
        <Text style={styles.label}>An welchen Tagen trainierst du?</Text>
        <View style={styles.daysRow}>
          {DAYS.map((d) => {
            const active = selectedDays.includes(d.key);
            return (
              <TouchableOpacity
                key={d.key}
                style={[styles.dayBtn, active && styles.dayBtnActive]}
                onPress={() => {
                  setSelectedDays((prev) =>
                    prev.includes(d.key) ? prev.filter((x) => x !== d.key) : [...prev, d.key]
                  );
                }}
              >
                <Text style={[styles.dayText, active && styles.dayTextActive]}>{d.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {/* FTP-Ziel */}
      <View style={styles.card}>
        <Text style={styles.label}>FTP-Ziel</Text>
        <Text style={styles.hint}>
          Functional Threshold Power – die Wattzahl, die du eine Stunde halten kannst. Wo willst du hin?
        </Text>
        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={ftpTarget}
            onChangeText={(v) => { setFtpTarget(v.replace(/[^0-9]/g, "")); setError(null); }}
            keyboardType="number-pad"
            placeholder="z.B. 250"
            placeholderTextColor="#444"
            maxLength={4}
          />
          <Text style={styles.unit}>W</Text>
        </View>
        <View style={styles.presets}>
          {[200, 250, 300, 350].map((w) => (
            <TouchableOpacity
              key={w}
              style={[styles.preset, ftpTarget === String(w) && styles.presetActive]}
              onPress={() => { setFtpTarget(String(w)); setError(null); }}
            >
              <Text style={[styles.presetText, ftpTarget === String(w) && styles.presetTextActive]}>
                {w} W
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Hauptevent */}
      <View style={styles.card}>
        <Text style={styles.label}>Hauptevent <Text style={styles.optional}>(optional)</Text></Text>
        <Text style={styles.hint}>Auf welches Event bereitest du dich vor? Der Coach plant dann gezielt darauf hin.</Text>
        <TextInput
          style={styles.inputText}
          value={eventName}
          onChangeText={setEventName}
          placeholder="z.B. Alpenbrevet, Granfondo München…"
          placeholderTextColor="#444"
        />
        <TextInput
          style={[styles.inputText, { marginTop: 10 }]}
          value={eventDate}
          onChangeText={(v) => { setEventDate(v); setError(null); }}
          placeholder="Datum: TT.MM.JJJJ"
          placeholderTextColor="#444"
          keyboardType="numbers-and-punctuation"
          maxLength={10}
        />
        {error && <Text style={styles.error}>{error}</Text>}
      </View>

      <TouchableOpacity style={styles.saveBtn} onPress={handleSave} disabled={saving}>
        {saving
          ? <ActivityIndicator color="#000" />
          : <Text style={styles.saveBtnText}>Ziele speichern →</Text>
        }
      </TouchableOpacity>

      <TouchableOpacity onPress={() => onDone(null, null)} style={styles.skipBtn}>
        <Text style={styles.skipText}>Später festlegen</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: "#111", padding: 24, paddingTop: 70, paddingBottom: 40 },
  emoji: { fontSize: 52, textAlign: "center", marginBottom: 12 },
  title: { color: "#fff", fontSize: 28, fontWeight: "900", textAlign: "center", marginBottom: 8 },
  subtitle: { color: "#555", fontSize: 14, textAlign: "center", lineHeight: 20, marginBottom: 24 },
  card: { backgroundColor: "#1a1a1a", borderRadius: 16, padding: 20, marginBottom: 16 },
  label: { color: "#00C853", fontSize: 11, fontWeight: "700", letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 12 },
  hint: { color: "#555", fontSize: 13, lineHeight: 18, marginBottom: 16 },
  goalBtn: { flexDirection: "row", alignItems: "center", padding: 12, borderRadius: 10, borderWidth: 1, borderColor: "#2a2a2a", marginBottom: 8, backgroundColor: "#262626" },
  goalBtnActive: { borderColor: "#00C853", backgroundColor: "#0a2e16" },
  goalEmoji: { fontSize: 22, marginRight: 12, width: 30, textAlign: "center" },
  goalText: { flex: 1 },
  goalLabel: { color: "#888", fontSize: 14, fontWeight: "700" },
  goalLabelActive: { color: "#00C853" },
  goalDesc: { color: "#444", fontSize: 11, marginTop: 2 },
  checkmark: { color: "#00C853", fontSize: 16, fontWeight: "900" },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 16 },
  input: { flex: 1, backgroundColor: "#262626", borderRadius: 12, padding: 16, color: "#fff", fontSize: 32, fontWeight: "800", textAlign: "center", borderWidth: 2, borderColor: "#00C853" },
  unit: { color: "#00C853", fontSize: 24, fontWeight: "800" },
  presets: { flexDirection: "row", gap: 8 },
  preset: { flex: 1, backgroundColor: "#262626", borderRadius: 8, padding: 10, alignItems: "center", borderWidth: 1, borderColor: "#333" },
  presetActive: { backgroundColor: "#003d1a", borderColor: "#00C853" },
  presetText: { color: "#555", fontSize: 13, fontWeight: "700" },
  presetTextActive: { color: "#00C853" },
  error: { color: "#FF1744", fontSize: 12, marginTop: 12 },
  saveBtn: { backgroundColor: "#00C853", borderRadius: 12, padding: 16, alignItems: "center" },
  saveBtnText: { color: "#000", fontSize: 16, fontWeight: "900" },
  skipBtn: { alignItems: "center", marginTop: 16, padding: 10 },
  skipText: { color: "#333", fontSize: 13 },
  freqRow: { flexDirection: "row", gap: 10 },
  freqBtn: { flex: 1, backgroundColor: "#262626", borderRadius: 10, borderWidth: 1, borderColor: "#333", padding: 14, alignItems: "center" },
  freqBtnActive: { borderColor: "#00C853", backgroundColor: "#0a2e16" },
  freqLabel: { color: "#888", fontSize: 18, fontWeight: "900" },
  freqLabelActive: { color: "#00C853" },
  freqDesc: { color: "#444", fontSize: 11, marginTop: 4 },
  optional: { color: "#444", fontWeight: "400", textTransform: "none" },
  inputText: { backgroundColor: "#262626", borderRadius: 10, padding: 14, color: "#fff", fontSize: 15, borderWidth: 1, borderColor: "#333" },
  daysRow: { flexDirection: "row", justifyContent: "space-between", gap: 6 },
  dayBtn: { flex: 1, backgroundColor: "#262626", borderRadius: 8, borderWidth: 1, borderColor: "#333", paddingVertical: 10, alignItems: "center" },
  dayBtnActive: { backgroundColor: "#0a2e16", borderColor: "#00C853" },
  dayText: { color: "#555", fontSize: 13, fontWeight: "700" },
  dayTextActive: { color: "#00C853" },
});
