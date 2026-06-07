import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView,
  TouchableOpacity, TextInput, ActivityIndicator,
} from "react-native";
import { BASE_URL, api } from "../services/api";
import { getToken } from "../services/auth";

async function apiAuth(path, options = {}) {
  const token = await getToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Fehler");
  return data;
}

const SERVICES = [
  {
    id: "garmin",
    name: "Garmin Connect",
    icon: "⌚",
    description: "Aktivitäten, HRV, Schlaf, Steps automatisch synchronisieren",
    fields: [
      { key: "garmin_email", label: "Garmin E-Mail", keyboard: "email-address", secure: false },
      { key: "garmin_password", label: "Garmin Passwort", keyboard: "default", secure: true },
    ],
  },
  {
    id: "whoop",
    name: "WHOOP",
    icon: "💪",
    description: "Recovery Score, HRV, Strain direkt aus WHOOP",
    fields: [],
    comingSoon: true,
  },
];

const GOAL_OPTIONS = [
  { value: "ftp",          label: "⚡ FTP steigern" },
  { value: "endurance",    label: "🚵 Ausdauer" },
  { value: "ultracycling", label: "🏔️ Ultracycling" },
  { value: "weight",       label: "⚖️ Abnehmen" },
  { value: "race",         label: "🏆 Wettkampf" },
  { value: "health",       label: "❤️ Gesundheit" },
];

const GENDER_OPTIONS = [
  { value: "male", label: "Männlich" },
  { value: "female", label: "Weiblich" },
  { value: "other", label: "Divers" },
];

export default function SettingsScreen({ user, onLogout }) {
  const [status, setStatus] = useState({});
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [activeForm, setActiveForm] = useState(null); // service id
  const [formValues, setFormValues] = useState({});
  const [connecting, setConnecting] = useState(false);
  const [mfaNeeded, setMfaNeeded] = useState(false);
  const [mfaCode, setMfaCode] = useState("");

  // Strava
  const [stravaConnected, setStravaConnected] = useState(false);
  const [stravaAthleteId, setStravaAthleteId] = useState(null);
  const [stravaSyncing, setStravaSyncing] = useState(false);

  // Profile state
  const [profile, setProfile] = useState({ ftp_target: "", ftp_override: "", training_goal: [], training_frequency: "", training_days: [], event_name: "", event_date: "", weight_kg: "", height_cm: "", gender: "", intervals_athlete_id: "" });
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);

  const loadStatus = async () => {
    try {
      const s = await apiAuth("/api/services/status");
      setStatus(s);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadProfile = async () => {
    try {
      const p = await api.getProfile();
      setStravaConnected(!!p.strava_connected);
      setStravaAthleteId(p.strava_athlete_id || null);
      setProfile({
        ftp_target: p.ftp_target ? String(p.ftp_target) : "",
        ftp_override: p.ftp_override ? String(p.ftp_override) : "",
        training_goal: p.training_goal ? p.training_goal.split(",").filter(Boolean) : [],
        training_frequency: p.training_frequency || "",
        training_days: p.training_days ? p.training_days.split(",").filter(Boolean) : [],
        event_name: p.event_name || "",
        event_date: p.event_date ? p.event_date.split("-").reverse().join(".") : "",
        weight_kg: p.weight_kg ? String(p.weight_kg) : "",
        height_cm: p.height_cm ? String(p.height_cm) : "",
        gender: p.gender || "",
        intervals_athlete_id: p.intervals_athlete_id || "",
      });
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadStatus();
    loadProfile();
    // Detect redirect back from Strava OAuth
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("strava") === "connected") {
        window.alert("✅ Strava erfolgreich verbunden!");
        window.history.replaceState({}, "", window.location.pathname);
        loadProfile();
      }
    }
  }, []);

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    try {
      await api.saveProfile({
        ftp_target: profile.ftp_target ? parseInt(profile.ftp_target) : null,
        ftp_override: profile.ftp_override ? parseInt(profile.ftp_override) : 0,
        training_goal: profile.training_goal.length ? profile.training_goal.join(",") : null,
        training_frequency: profile.training_frequency || null,
        training_days: profile.training_days.length ? profile.training_days.join(",") : null,
        event_name: profile.event_name || null,
        event_date: profile.event_date ? profile.event_date.split(".").reverse().join("-") : null,
        weight_kg: profile.weight_kg ? parseFloat(profile.weight_kg) : null,
        height_cm: profile.height_cm ? parseInt(profile.height_cm) : null,
        gender: profile.gender || null,
        intervals_athlete_id: profile.intervals_athlete_id || null,
      });
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 2000);
    } catch (e) {
      window.alert("Fehler: " + e.message);
    } finally {
      setProfileSaving(false);
    }
  };

  const handleConnect = async (serviceId) => {
    setConnecting(true);
    try {
      if (serviceId === "garmin") {
        const result = await apiAuth("/api/auth/garmin/login", {
          method: "POST",
          body: JSON.stringify({
            email: formValues.garmin_email || "",
            password: formValues.garmin_password || "",
          }),
        });
        if (result.status === "needs_mfa") {
          setMfaNeeded(true);
          return;
        }
        window.alert("✅ Garmin verbunden!");
        setActiveForm(null);
        setFormValues({});
        setMfaNeeded(false);
        await loadStatus();
      }
    } catch (e) {
      const msg = e.message || "";
      if (msg.includes("429") || msg.includes("Rate Limit") || msg.includes("rate limit")) {
        window.alert("⚠️ Garmin hat zu viele Login-Versuche erkannt.\n\nBitte 15–30 Minuten warten und dann erneut versuchen.");
      } else {
        window.alert("Fehler: " + msg);
      }
    } finally {
      setConnecting(false);
    }
  };

  const handleMfa = async () => {
    setConnecting(true);
    try {
      await apiAuth("/api/auth/garmin/mfa", {
        method: "POST",
        body: JSON.stringify({ code: mfaCode }),
      });
      window.alert("✅ Garmin verbunden!");
      setActiveForm(null);
      setFormValues({});
      setMfaNeeded(false);
      setMfaCode("");
      await loadStatus();
    } catch (e) {
      window.alert("Fehler: " + e.message);
    } finally {
      setConnecting(false);
    }
  };

  const handleStravaConnect = async () => {
    try {
      const { url } = await api.stravaAuthUrl();
      window.location.href = url;
    } catch (e) {
      window.alert("Fehler: " + e.message);
    }
  };

  const handleStravaSync = async () => {
    setStravaSyncing(true);
    try {
      const r = await api.stravaSync();
      window.alert(`✅ Strava Sync: ${r.imported} Aktivitäten importiert`);
      window.location.reload();
    } catch (e) {
      window.alert("Fehler: " + e.message);
    } finally {
      setStravaSyncing(false);
    }
  };

  const handleStravaDisconnect = async () => {
    if (!window.confirm("Strava wirklich trennen?")) return;
    try {
      await api.stravaDisconnect();
      setStravaConnected(false);
      setStravaAthleteId(null);
    } catch (e) {
      window.alert("Fehler: " + e.message);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await apiAuth("/api/services/garmin/sync", { method: "POST" });
      window.alert(`✅ Sync abgeschlossen!\n${result.activities_synced} Aktivitäten\n${result.health_days_synced} Health-Tage`);
      window.location.reload();
    } catch (e) {
      const msg = e.message || "";
      if (msg.includes("abgelaufen") || msg.includes("neu verbinden") || msg.includes("503")) {
        window.alert("⚠️ Garmin-Verbindung abgelaufen.\n\nBitte unter 'Dienste' → Garmin neu verbinden.");
      } else if (msg.includes("401") || msg.includes("nicht autorisiert") || msg.includes("Sitzung")) {
        window.alert("⚠️ Sitzung abgelaufen.\n\nBitte neu einloggen.");
      } else {
        window.alert("Sync fehlgeschlagen: " + msg);
      }
    } finally {
      setSyncing(false);
    }
  };


  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>⚙️ Einstellungen</Text>

      {/* User Info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Account</Text>
        <View style={styles.userCard}>
          <Text style={styles.userName}>{user?.name || "–"}</Text>
          <Text style={styles.userEmail}>{user?.email || "–"}</Text>
        </View>
        <TouchableOpacity style={styles.logoutBtn} onPress={onLogout}>
          <Text style={styles.logoutText}>Ausloggen</Text>
        </TouchableOpacity>
      </View>

      {/* Profil */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Profil & Ziele</Text>

        <Text style={styles.fieldLabel}>FTP-Ziel (W)</Text>
        <TextInput
          style={styles.input}
          placeholder="z.B. 250"
          placeholderTextColor="#555"
          keyboardType="number-pad"
          value={profile.ftp_target}
          onChangeText={(v) => setProfile((p) => ({ ...p, ftp_target: v }))}
        />

        <Text style={styles.fieldLabel}>Trainingsziel (mehrere möglich)</Text>
        <View style={styles.goalGrid}>
          {GOAL_OPTIONS.map((opt) => {
            const active = profile.training_goal.includes(opt.value);
            return (
              <TouchableOpacity
                key={opt.value}
                style={[styles.goalBtn, active && styles.goalBtnActive]}
                onPress={() => setProfile((p) => ({
                  ...p,
                  training_goal: p.training_goal.includes(opt.value)
                    ? p.training_goal.filter((x) => x !== opt.value)
                    : [...p.training_goal, opt.value],
                }))}
              >
                <Text style={[styles.goalText, active && styles.goalTextActive]}>
                  {opt.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <Text style={styles.fieldLabel}>Trainingsfrequenz</Text>
        <View style={styles.genderRow}>
          {[{v:"low",l:"1–2×/Wo"},{v:"mid",l:"3–5×/Wo"},{v:"high",l:"Täglich"}].map((opt) => (
            <TouchableOpacity
              key={opt.v}
              style={[styles.genderBtn, profile.training_frequency === opt.v && styles.genderBtnActive]}
              onPress={() => setProfile((p) => ({ ...p, training_frequency: opt.v }))}
            >
              <Text style={[styles.genderText, profile.training_frequency === opt.v && styles.genderTextActive]}>
                {opt.l}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.fieldLabel}>Bevorzugte Trainingstage</Text>
        <View style={styles.daysRow}>
          {[{k:"mon",l:"Mo"},{k:"tue",l:"Di"},{k:"wed",l:"Mi"},{k:"thu",l:"Do"},{k:"fri",l:"Fr"},{k:"sat",l:"Sa"},{k:"sun",l:"So"}].map((d) => {
            const active = profile.training_days.includes(d.k);
            return (
              <TouchableOpacity
                key={d.k}
                style={[styles.dayBtn, active && styles.dayBtnActive]}
                onPress={() => setProfile((p) => ({
                  ...p,
                  training_days: p.training_days.includes(d.k)
                    ? p.training_days.filter((x) => x !== d.k)
                    : [...p.training_days, d.k],
                }))}
              >
                <Text style={[styles.dayText, active && styles.dayTextActive]}>{d.l}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <Text style={styles.fieldLabel}>Hauptevent</Text>
        {(() => {
          const hsActive = profile.event_name === "Hügel & Stahl 2026";
          return (
            <TouchableOpacity
              style={[styles.eventPresetBtn, hsActive && styles.eventPresetBtnActive]}
              onPress={() => setProfile((p) => {
                if (p.event_name === "Hügel & Stahl 2026") {
                  return { ...p, event_name: "", event_date: "" };
                }
                return {
                  ...p,
                  event_name: "Hügel & Stahl 2026",
                  event_date: "28.08.2026",
                  training_goal: p.training_goal.includes("ultracycling")
                    ? p.training_goal
                    : [...p.training_goal.filter(g => g !== "endurance"), "ultracycling"],
                };
              })}
            >
              <Text style={[styles.eventPresetText, hsActive && styles.eventPresetTextActive]}>
                🏔️⚙️ Hügel & Stahl 2026 — 28. August
              </Text>
            </TouchableOpacity>
          );
        })()}
        <TextInput
          style={styles.input}
          placeholder="z.B. Alpenbrevet, Granfondo…"
          placeholderTextColor="#555"
          value={profile.event_name}
          onChangeText={(v) => setProfile((p) => ({ ...p, event_name: v }))}
        />

        <Text style={styles.fieldLabel}>Event-Datum</Text>
        <TextInput
          style={styles.input}
          placeholder="TT.MM.JJJJ"
          placeholderTextColor="#555"
          keyboardType="numbers-and-punctuation"
          maxLength={10}
          value={profile.event_date}
          onChangeText={(v) => setProfile((p) => ({ ...p, event_date: v }))}
        />

        <Text style={styles.fieldLabel}>Gewicht (kg)</Text>
        <TextInput
          style={styles.input}
          placeholder="z.B. 78"
          placeholderTextColor="#555"
          keyboardType="decimal-pad"
          value={profile.weight_kg}
          onChangeText={(v) => setProfile((p) => ({ ...p, weight_kg: v }))}
        />

        <Text style={styles.fieldLabel}>Größe (cm)</Text>
        <TextInput
          style={styles.input}
          placeholder="z.B. 180"
          placeholderTextColor="#555"
          keyboardType="number-pad"
          value={profile.height_cm}
          onChangeText={(v) => setProfile((p) => ({ ...p, height_cm: v }))}
        />

        <Text style={styles.fieldLabel}>FTP (W)</Text>
        <TextInput
          style={styles.input}
          placeholder="z.B. 230"
          placeholderTextColor="#555"
          keyboardType="number-pad"
          value={profile.ftp_override}
          onChangeText={(v) => setProfile((p) => ({ ...p, ftp_override: v }))}
        />

        <Text style={styles.fieldLabel}>Geschlecht</Text>
        <View style={styles.genderRow}>
          {GENDER_OPTIONS.map((opt) => (
            <TouchableOpacity
              key={opt.value}
              style={[styles.genderBtn, profile.gender === opt.value && styles.genderBtnActive]}
              onPress={() => setProfile((p) => ({ ...p, gender: opt.value }))}
            >
              <Text style={[styles.genderText, profile.gender === opt.value && styles.genderTextActive]}>
                {opt.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.fieldLabel}>intervals.icu Athlete-ID</Text>
        <TextInput
          style={styles.input}
          placeholder="z.B. i545388"
          placeholderTextColor="#666"
          value={profile.intervals_athlete_id}
          onChangeText={(v) => setProfile((p) => ({ ...p, intervals_athlete_id: v }))}
          autoCapitalize="none"
        />

        <TouchableOpacity
          style={[styles.saveBtn, profileSaved && styles.saveBtnDone]}
          onPress={handleSaveProfile}
          disabled={profileSaving}
        >
          {profileSaving
            ? <ActivityIndicator size="small" color="#000" />
            : <Text style={styles.saveBtnText}>{profileSaved ? "✓ Gespeichert" : "Speichern"}</Text>
          }
        </TouchableOpacity>
      </View>

      {/* Services */}
      <Text style={styles.sectionTitle2}>Fitness Services verbinden</Text>

      {loading ? (
        <ActivityIndicator color="#00C853" style={{ margin: 20 }} />
      ) : (
        SERVICES.map((service) => {
          const connected = status[service.id]?.connected;
          const verified = status[service.id]?.verified !== false; // default true für non-garmin
          const isFormOpen = activeForm === service.id;

          return (
            <View key={service.id} style={styles.serviceCard}>
              <View style={styles.serviceHeader}>
                <Text style={styles.serviceIcon}>{service.icon}</Text>
                <View style={styles.serviceInfo}>
                  <View style={styles.serviceNameRow}>
                    <Text style={styles.serviceName}>{service.name}</Text>
                    {service.comingSoon && (
                      <View style={styles.soonBadge}>
                        <Text style={styles.soonText}>Bald</Text>
                      </View>
                    )}
                    {connected && (
                      <View style={[styles.connectedBadge, !verified && styles.connectedBadgeWarn]}>
                        <Text style={[styles.connectedText, !verified && styles.connectedTextWarn]}>
                          {verified ? "✓ Verbunden" : "⚠ Gespeichert"}
                        </Text>
                      </View>
                    )}
                  </View>
                  <Text style={styles.serviceDesc}>{service.description}</Text>
                  {connected && status[service.id]?.email && (
                    <Text style={styles.connectedEmail}>{status[service.id].email}</Text>
                  )}
                </View>
              </View>

              {/* Actions */}
              {!service.comingSoon && (
                <View style={styles.serviceActions}>
                  {!isFormOpen && (
                    <TouchableOpacity
                      style={[styles.actionBtn, connected && styles.actionBtnSecondary]}
                      onPress={() => setActiveForm(service.id)}
                    >
                      <Text style={[styles.actionBtnText, connected && styles.actionBtnTextSecondary]}>
                        {connected ? "Neu verbinden" : "Verbinden"}
                      </Text>
                    </TouchableOpacity>
                  )}
                  {connected && !isFormOpen && (
                    <TouchableOpacity
                      style={[styles.actionBtn, styles.syncBtn]}
                      onPress={handleSync}
                      disabled={syncing}
                    >
                      {syncing
                        ? <ActivityIndicator size="small" color="#000" />
                        : <Text style={styles.actionBtnText}>🔄 Sync</Text>
                      }
                    </TouchableOpacity>
                  )}
                </View>
              )}

              {/* Credential Form */}
              {isFormOpen && !mfaNeeded && (
                <View style={styles.form}>
                  {service.fields.map((field) => (
                    <TextInput
                      key={field.key}
                      style={styles.input}
                      placeholder={field.label}
                      placeholderTextColor="#555"
                      keyboardType={field.keyboard}
                      secureTextEntry={field.secure}
                      autoCapitalize="none"
                      value={formValues[field.key] || ""}
                      onChangeText={(v) => setFormValues((p) => ({ ...p, [field.key]: v }))}
                    />
                  ))}
                  <View style={styles.formActions}>
                    <TouchableOpacity
                      style={styles.cancelBtn}
                      onPress={() => { setActiveForm(null); setFormValues({}); }}
                    >
                      <Text style={styles.cancelText}>Abbrechen</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.connectBtn}
                      onPress={() => handleConnect(service.id)}
                      disabled={connecting}
                    >
                      {connecting
                        ? <ActivityIndicator size="small" color="#000" />
                        : <Text style={styles.connectBtnText}>Verbinden</Text>
                      }
                    </TouchableOpacity>
                  </View>
                </View>
              )}

              {/* MFA Code Form */}
              {isFormOpen && mfaNeeded && (
                <View style={styles.form}>
                  <Text style={styles.mfaHint}>
                    📧 Garmin hat einen Sicherheitscode an deine E-Mail geschickt.{"\n"}Bitte den Code eingeben:
                  </Text>
                  <TextInput
                    style={styles.input}
                    placeholder="6-stelliger Code"
                    placeholderTextColor="#555"
                    keyboardType="number-pad"
                    autoCapitalize="none"
                    value={mfaCode}
                    onChangeText={setMfaCode}
                  />
                  <View style={styles.formActions}>
                    <TouchableOpacity
                      style={styles.cancelBtn}
                      onPress={() => { setActiveForm(null); setFormValues({}); setMfaNeeded(false); setMfaCode(""); }}
                    >
                      <Text style={styles.cancelText}>Abbrechen</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.connectBtn}
                      onPress={handleMfa}
                      disabled={connecting}
                    >
                      {connecting
                        ? <ActivityIndicator size="small" color="#000" />
                        : <Text style={styles.connectBtnText}>Code bestätigen</Text>
                      }
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </View>
          );
        })
      )}

      {/* Strava */}
      <View style={styles.serviceCard}>
        <View style={styles.serviceHeader}>
          <Text style={styles.serviceIcon}>🟠</Text>
          <View style={styles.serviceInfo}>
            <View style={styles.serviceNameRow}>
              <Text style={styles.serviceName}>Strava</Text>
              {stravaConnected
                ? <View style={styles.connectedBadge}><Text style={styles.connectedText}>✓ Verbunden</Text></View>
                : null
              }
            </View>
            <Text style={styles.serviceDesc}>
              {stravaConnected
                ? `Athlete ID: ${stravaAthleteId} · Neue Zwift-Aktivitäten werden automatisch importiert`
                : "Zwift-Workouts automatisch importieren – sofort nach dem Training"
              }
            </Text>
          </View>
        </View>
        <View style={styles.serviceActions}>
          {stravaConnected ? (
            <>
              <TouchableOpacity
                style={[styles.actionBtn, styles.syncBtn]}
                onPress={handleStravaSync}
                disabled={stravaSyncing}
              >
                {stravaSyncing
                  ? <ActivityIndicator size="small" color="#000" />
                  : <Text style={styles.actionBtnText}>🔄 Letzte 30 Tage sync</Text>
                }
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, styles.actionBtnSecondary]}
                onPress={handleStravaDisconnect}
              >
                <Text style={[styles.actionBtnText, styles.actionBtnTextSecondary]}>Trennen</Text>
              </TouchableOpacity>
            </>
          ) : (
            <TouchableOpacity style={styles.actionBtn} onPress={handleStravaConnect}>
              <Text style={styles.actionBtnText}>🔗 Mit Strava verbinden</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#111" },
  title: { color: "#fff", fontSize: 24, fontWeight: "800", margin: 20, marginTop: 60 },
  section: { backgroundColor: "#1a1a1a", marginHorizontal: 15, borderRadius: 12, padding: 14, marginBottom: 20 },
  sectionTitle: { color: "#555", fontSize: 11, fontWeight: "700", letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 10 },
  sectionTitle2: { color: "#555", fontSize: 11, fontWeight: "700", letterSpacing: 1.2, textTransform: "uppercase", marginHorizontal: 20, marginBottom: 10 },
  userCard: { marginBottom: 12 },
  userName: { color: "#fff", fontSize: 18, fontWeight: "700" },
  userEmail: { color: "#555", fontSize: 13, marginTop: 2 },
  logoutBtn: { backgroundColor: "#1f1f1f", borderRadius: 8, padding: 12, alignItems: "center", borderWidth: 1, borderColor: "#333" },
  logoutText: { color: "#FF1744", fontWeight: "700" },
  serviceCard: { backgroundColor: "#1a1a1a", marginHorizontal: 15, borderRadius: 12, padding: 14, marginBottom: 10 },
  serviceHeader: { flexDirection: "row", marginBottom: 10 },
  serviceIcon: { fontSize: 28, marginRight: 12, marginTop: 2 },
  serviceInfo: { flex: 1 },
  serviceNameRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  serviceName: { color: "#fff", fontSize: 16, fontWeight: "700" },
  soonBadge: { backgroundColor: "#333", borderRadius: 6, paddingHorizontal: 7, paddingVertical: 2 },
  soonText: { color: "#888", fontSize: 10, fontWeight: "700" },
  connectedBadge: { backgroundColor: "#003d1a", borderRadius: 6, paddingHorizontal: 7, paddingVertical: 2, borderWidth: 1, borderColor: "#00C853" },
  connectedBadgeWarn: { backgroundColor: "#2e1a00", borderColor: "#cc7700" },
  connectedTextWarn: { color: "#cc7700" },
  connectedText: { color: "#00C853", fontSize: 10, fontWeight: "700" },
  serviceDesc: { color: "#555", fontSize: 12, marginTop: 4, lineHeight: 17 },
  connectedEmail: { color: "#444", fontSize: 11, marginTop: 4 },
  serviceActions: { flexDirection: "row", gap: 8 },
  actionBtn: { flex: 1, backgroundColor: "#00C853", borderRadius: 8, padding: 10, alignItems: "center" },
  actionBtnSecondary: { backgroundColor: "transparent", borderWidth: 1, borderColor: "#333" },
  syncBtn: { backgroundColor: "#00C853" },
  actionBtnText: { color: "#000", fontWeight: "700", fontSize: 13 },
  actionBtnTextSecondary: { color: "#555" },
  form: { marginTop: 10, borderTopWidth: 1, borderTopColor: "#333", paddingTop: 12 },
  input: { backgroundColor: "#262626", borderRadius: 8, padding: 12, color: "#fff", fontSize: 14, marginBottom: 10, borderWidth: 1, borderColor: "#333" },
  formActions: { flexDirection: "row", gap: 8 },
  cancelBtn: { flex: 1, padding: 12, alignItems: "center", borderRadius: 8, borderWidth: 1, borderColor: "#333" },
  cancelText: { color: "#555", fontWeight: "700" },
  connectBtn: { flex: 1, backgroundColor: "#00C853", padding: 12, alignItems: "center", borderRadius: 8 },
  connectBtnText: { color: "#000", fontWeight: "800" },
  mfaHint: { color: "#aaa", fontSize: 13, lineHeight: 20, marginBottom: 12 },
  goalGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 4 },
  goalBtn: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: "#333", backgroundColor: "#262626" },
  goalBtnActive: { borderColor: "#00C853", backgroundColor: "#003d1a" },
  goalText: { color: "#555", fontWeight: "700", fontSize: 12 },
  goalTextActive: { color: "#00C853" },
  fieldLabel: { color: "#555", fontSize: 11, fontWeight: "700", letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 6, marginTop: 12 },
  genderRow: { flexDirection: "row", gap: 8, marginBottom: 4 },
  genderBtn: { flex: 1, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: "#333", alignItems: "center", backgroundColor: "#262626" },
  genderBtnActive: { borderColor: "#00C853", backgroundColor: "#003d1a" },
  genderText: { color: "#555", fontWeight: "700", fontSize: 13 },
  genderTextActive: { color: "#00C853" },
  saveBtn: { backgroundColor: "#00C853", borderRadius: 8, padding: 13, alignItems: "center", marginTop: 16 },
  saveBtnDone: { backgroundColor: "#003d1a", borderWidth: 1, borderColor: "#00C853" },
  saveBtnText: { color: "#000", fontWeight: "800", fontSize: 14 },
  eventPresetBtn: { backgroundColor: "#1a1a1a", borderRadius: 8, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: "#333", alignItems: "center" },
  eventPresetBtnActive: { backgroundColor: "#1a1a2e", borderColor: "#a0a0ff" },
  eventPresetText: { color: "#555", fontWeight: "700", fontSize: 13 },
  eventPresetTextActive: { color: "#a0a0ff" },
  ftpRow: { marginBottom: 4 },
  ftpDisplay: { flexDirection: "row", alignItems: "baseline", gap: 8, marginBottom: 8 },
  ftpValue: { color: "#00C853", fontSize: 28, fontWeight: "800" },
  ftpHint: { color: "#555", fontSize: 11 },
  ftpInput: { marginBottom: 0 },
  daysRow: { flexDirection: "row", gap: 5, marginBottom: 4 },
  dayBtn: { flex: 1, paddingVertical: 9, borderRadius: 7, borderWidth: 1, borderColor: "#333", alignItems: "center", backgroundColor: "#262626" },
  dayBtnActive: { borderColor: "#00C853", backgroundColor: "#003d1a" },
  dayText: { color: "#555", fontWeight: "700", fontSize: 12 },
  dayTextActive: { color: "#00C853" },
});
