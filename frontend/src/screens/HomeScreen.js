import React, { useEffect, useState, useCallback } from "react";
import {
  View, Text, StyleSheet, ScrollView,
  RefreshControl, ActivityIndicator, TouchableOpacity,
} from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import MetricCard from "../components/MetricCard";
import { api } from "../services/api";
import { useVisibilityRefresh } from "../hooks/useVisibilityRefresh";

function DonutChart({ dist }) {
  const z2 = dist?.Zone2 || 0;
  const ss = dist?.SweetSpot || 0;
  const hi = dist?.HighIntensity || 0;
  const total = z2 + ss + hi || 1;
  const a1 = (z2 / total) * 360;
  const a2 = a1 + (ss / total) * 360;
  return (
    <View style={{ alignItems: "center", paddingVertical: 10 }}>
      <View style={{
        width: 140, height: 140, borderRadius: 70,
        backgroundImage: `conic-gradient(#00C853 0deg ${a1}deg, #FFD600 ${a1}deg ${a2}deg, #FF1744 ${a2}deg 360deg)`,
        justifyContent: "center", alignItems: "center",
      }}>
        <View style={{ width: 80, height: 80, borderRadius: 40, backgroundColor: "#1a1a1a", justifyContent: "center", alignItems: "center" }}>
          <Text style={{ color: "#fff", fontSize: 14, fontWeight: "800" }}>{z2}%</Text>
          <Text style={{ color: "#555", fontSize: 10 }}>Zone 2</Text>
        </View>
      </View>
      <View style={{ flexDirection: "row", gap: 12, marginTop: 10 }}>
        {[["#00C853", `Z2 ${z2}%`], ["#FFD600", `SS ${ss}%`], ["#FF1744", `HIT ${hi}%`]].map(([color, label]) => (
          <View key={label} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />
            <Text style={{ color: "#888", fontSize: 11 }}>{label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

export default function HomeScreen({ user, onLogout }) {
  const [data, setData] = useState(null);
  const [dist, setDist] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const [d, t] = await Promise.all([api.dashboard(), api.trends(90)]);
      setData(d);
      setDist(t.training_distribution || null);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(useCallback(() => { load(); }, []));
  useVisibilityRefresh(load);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#00C853" />
        <Text style={styles.loadingText}>Lade Dashboard…</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>⚠️ {error}</Text>
        <Text style={styles.hint}>Ist der Backend-Server gestartet?{"\n"}python3 -m uvicorn backend.main:app</Text>
      </View>
    );
  }

  const tsbColor = data.tsb > 5 ? "#00C853" : data.tsb > -10 ? "#FFD600" : "#FF1744";
  const st = data.status;

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor="#00C853" />}
    >
      {/* Header */}
      <View style={styles.header}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
          <Text style={styles.title}>⚡ SKYWALKER</Text>
          {onLogout && (
            <TouchableOpacity onPress={onLogout}>
              <Text style={styles.logoutBtn}>Logout</Text>
            </TouchableOpacity>
          )}
        </View>
        <Text style={styles.subtitle}>{user?.name ? `Hallo, ${user.name}` : "Fitness Dashboard"}</Text>
      </View>

      {/* Kombinierter Status */}
      {st && (
        <View style={[styles.hrvBanner, { borderColor: st.color }]}>
          <Text style={[styles.hrvLabel, { color: st.color }]}>{st.label}</Text>
          <Text style={styles.hrvSub}>Readiness Score: {st.score}/10</Text>
          <View style={styles.componentRow}>
            {Object.entries(st.components).map(([key, val]) => (
              <View key={key} style={styles.componentChip}>
                <Text style={styles.componentKey}>{key}</Text>
                <Text style={[styles.componentVal, { color: val >= 7 ? "#00C853" : val >= 5 ? "#FFD600" : "#FF1744" }]}>
                  {val}
                </Text>
              </View>
            ))}
          </View>
          <Text style={styles.hrvSub}>
            HRV {data.hrv?.current} ms · TSB {data.tsb}
            {st.components["Check-in"] ? " · Check-in ✓" : " · Kein Check-in"}
          </Text>
        </View>
      )}

      {/* Trainingsverteilung */}
      {dist && (
        <View style={styles.distBox}>
          <Text style={styles.sectionTitle}>Trainingsverteilung</Text>
          <DonutChart dist={dist} />
        </View>
      )}

      {/* PMC Metriken */}
      <Text style={styles.sectionTitle}>Performance</Text>
      <View style={styles.row}>
        <MetricCard label="CTL (Fitness)" value={data.ctl} color="#00C853" />
        <MetricCard label="ATL (Fatigue)" value={data.atl} color="#FF6D00" />
        <MetricCard label="TSB (Form)" value={data.tsb} color={tsbColor} />
      </View>

      {/* FTP + Weekly Load */}
      <View style={styles.row}>
        <MetricCard label="FTP" value={data.ftp} unit="W" color="#00f2ff" size="large" />
        <MetricCard label="Wochenlast" value={Math.round(data.weekly_load)} unit="TSS" color="#FF6D00" size="large" />
      </View>

      {/* FTP Fortschritt */}
      <View style={styles.progressBox}>
        <View style={styles.progressHeader}>
          <Text style={styles.progressLabel}>FTP Ziel: {data.ftp_target}W</Text>
          <Text style={styles.progressPct}>
            {Math.round(((data.ftp - 150) / (data.ftp_target - 150)) * 100)}%
          </Text>
        </View>
        <View style={styles.progressTrack}>
          <View style={[
            styles.progressFill,
            { width: `${Math.min(100, Math.round(((data.ftp - 150) / (data.ftp_target - 150)) * 100))}%` }
          ]} />
        </View>
        <View style={styles.progressMinMax}>
          <Text style={styles.progressHint}>150W</Text>
          <Text style={styles.progressHint}>{data.ftp_target}W</Text>
        </View>
      </View>

      {/* Health */}
      <Text style={styles.sectionTitle}>Health</Text>
      <View style={styles.row}>
        <MetricCard label="Schlaf" value={data.latest_sleep} unit="%" color="#9C27B0" />
        <MetricCard label="RHR" value={data.latest_rhr} unit="bpm" color="#2196F3" />
        <MetricCard label="VO2 Max" value={data.latest_vo2max} color="#FF5722" />
      </View>

      <View style={{ height: 30 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#111" },
  center: { flex: 1, backgroundColor: "#111", justifyContent: "center", alignItems: "center", padding: 20 },
  loadingText: { color: "#888", marginTop: 12 },
  errorText: { color: "#FF1744", fontSize: 16, textAlign: "center", marginBottom: 10 },
  hint: { color: "#555", fontSize: 12, textAlign: "center", fontFamily: "monospace" },
  header: { padding: 20, paddingTop: 60, alignItems: "center", width: "100%" },
  logoutBtn: { color: "#555", fontSize: 13 },
  title: { color: "#00C853", fontSize: 28, fontWeight: "900", letterSpacing: 2 },
  subtitle: { color: "#555", fontSize: 13, marginTop: 2 },
  sectionTitle: { color: "#555", fontSize: 12, fontWeight: "700", letterSpacing: 1.5, marginLeft: 15, marginTop: 20, marginBottom: 4, textTransform: "uppercase" },
  row: { flexDirection: "row", paddingHorizontal: 10 },
  hrvBanner: { marginHorizontal: 15, marginTop: 10, borderRadius: 12, borderWidth: 2, padding: 14, alignItems: "center", backgroundColor: "#1a1a1a" },
  hrvLabel: { fontSize: 22, fontWeight: "800" },
  hrvSub: { color: "#666", fontSize: 12, marginTop: 6 },
  componentRow: { flexDirection: "row", gap: 8, marginTop: 10, marginBottom: 4 },
  componentChip: { alignItems: "center", backgroundColor: "#262626", borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 },
  componentKey: { color: "#555", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 },
  componentVal: { fontSize: 16, fontWeight: "800", marginTop: 2 },
  progressBox: { marginHorizontal: 15, marginTop: 12, backgroundColor: "#1a1a1a", borderRadius: 12, padding: 14 },
  progressHeader: { flexDirection: "row", justifyContent: "space-between", marginBottom: 8 },
  progressLabel: { color: "#888", fontSize: 12, textTransform: "uppercase", letterSpacing: 0.8 },
  progressPct: { color: "#00C853", fontWeight: "700" },
  progressTrack: { height: 18, backgroundColor: "#262626", borderRadius: 9, overflow: "hidden" },
  progressFill: { height: "100%", borderRadius: 9, backgroundColor: "#00C853" },
  progressMinMax: { flexDirection: "row", justifyContent: "space-between", marginTop: 4 },
  progressHint: { color: "#444", fontSize: 10 },
  distBox: { marginHorizontal: 15, marginTop: 10, backgroundColor: "#1a1a1a", borderRadius: 12, paddingBottom: 4 },
});
